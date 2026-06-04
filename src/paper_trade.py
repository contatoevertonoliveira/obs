#!/usr/bin/env python3
"""
HERMES QUANT V2 — PAPER TRADE SYSTEM v2.0
===========================================
Apenas setups vencedores: BTC M1 + ETH M5
Martingale real com níveis 1.0x → 2.5x → 6.0x

Uso:
  python3 src/paper_trade.py scan      → Escaneia e executa trades
  python3 src/paper_trade.py status    → Status da conta
  python3 src/paper_trade.py history   → Últimos trades
  python3 src/paper_trade.py reset     → Reseta conta
"""
import os, sys, json, time
from datetime import datetime, timezone
import warnings
warnings.filterwarnings("ignore")

os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ".")
from config.settings import MODEL_DIR, PAYOUT_RATE
from src.signal_engine import generate_signals

# ═══════════════════════════════════════════════════════
# CONFIG
# ═══════════════════════════════════════════════════════
CONFIG_FILE = "config/active_setups.json"
PAPER_FILE = os.path.join(MODEL_DIR, "paper_trade.json")

def load_config():
    with open(CONFIG_FILE) as f:
        return json.load(f)

def get_cycle_name(cycle):
    return {1: "Seed", 2: "Growth", 3: "Scale", 4: "Legacy"}.get(cycle, f"Ciclo {cycle}")

# ═══════════════════════════════════════════════════════
# ESTADO DA CONTA
# ═══════════════════════════════════════════════════════

def load_account():
    """Carrega estado da conta com tracking de martingale por setup."""
    config = load_config()
    default = {
        "balance": config["cycles"][0]["from"],
        "initial_balance": config["cycles"][0]["from"],
        "currency": "BRL",
        "trades": [],
        "daily_trades": 0,
        "daily_wins": 0,
        "daily_losses": 0,
        "current_streak": 0,
        "best_streak": 0,
        "worst_streak": 0,
        "cycle": 1,
        "cycle_target": config["cycles"][0]["to"],
        "martingale": {},  # per-setup: { "BTC_1m": {"active": false, "level": 0, "consecutive_losses": 0} }
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    if os.path.exists(PAPER_FILE):
        try:
            with open(PAPER_FILE) as f:
                data = json.load(f)
            # Ensure martingale state exists for all active setups
            for setup in config["active_setups"]:
                key = f"{setup['symbol'].split('/')[0]}_{setup['tf']}"
                if "martingale" not in data or key not in data.get("martingale", {}):
                    if "martingale" not in data:
                        data["martingale"] = {}
                    data["martingale"][key] = {"active": False, "level": 0, "consecutive_losses": 0}
            return data
        except:
            pass
    return default

def save_account(account):
    account["updated_at"] = datetime.now(timezone.utc).isoformat()
    os.makedirs(os.path.dirname(PAPER_FILE), exist_ok=True)
    with open(PAPER_FILE, "w") as f:
        json.dump(account, f, indent=2)

def get_stake(balance, risk_pct):
    return round(balance * risk_pct, 2)

def determine_cycle(balance, config):
    for i, cycle in enumerate(config["cycles"]):
        if balance >= cycle["to"] and i < len(config["cycles"]) - 1:
            continue
        return i + 1
    return len(config["cycles"])

# ═══════════════════════════════════════════════════════
# MARTINGALE ENGINE
# ═══════════════════════════════════════════════════════

def compute_mg_stake(balance, base_stake_pct, mg_mult, mg_active, mg_level):
    """Calcula stake considerando nível de martingale."""
    if mg_active:
        mult = mg_mult[min(mg_level, len(mg_mult) - 1)]
    else:
        mult = 1.0
    stake = round(balance * base_stake_pct * mult, 2)
    stake = min(stake, balance * 0.5)   # Cap em 50% do saldo
    stake = max(stake, 0.50)            # Mínimo R$ 0,50
    return min(stake, balance)

def update_mg_state(account, setup_key, won, max_consecutive):
    """Atualiza estado do martingale após resultado do trade."""
    mg = account["martingale"].setdefault(setup_key, {
        "active": False, "level": 0, "consecutive_losses": 0
    })
    
    if mg["active"] and won:
        # Martingale bem-sucedido — reset
        mg["active"] = False
        mg["level"] = 0
        mg["consecutive_losses"] = 0
    elif mg["active"] and not won:
        mg["consecutive_losses"] += 1
        if mg["consecutive_losses"] >= max_consecutive:
            # Máximo de recuperações — desiste
            mg["active"] = False
            mg["level"] = 0
            mg["consecutive_losses"] = 0
        else:
            mg["level"] = mg["consecutive_losses"]
    elif not mg["active"] and not won:
        # Primeira perda — entra em martingale
        mg["active"] = True
        mg["level"] = 1
        mg["consecutive_losses"] = 1
    else:
        mg["active"] = False
        mg["level"] = 0
        mg["consecutive_losses"] = 0

# ═══════════════════════════════════════════════════════
# SIMULAÇÃO DE RESULTADO (baseada na confiança)
# ═══════════════════════════════════════════════════════

def simulate_result(confidence, actual_result=None):
    """
    Simula resultado baseado na confiança calibrada (backtest BTC M1 + ETH M5).
    
    Calibração:
      Conf >= 0.88 → 62-76% WR (backtest)
      Conf >= 0.85 → 57-62% WR
      Conf >= 0.80 → 55-57% WR
      Conf >= 0.75 → 53-55% WR
      Conf >= 0.70 → 51-53% WR
      Conf < 0.70  → 50% WR (aleatório)
    """
    if actual_result is not None:
        return actual_result
    
    if confidence >= 0.88:
        win_prob = 0.65
    elif confidence >= 0.85:
        win_prob = 0.60
    elif confidence >= 0.80:
        win_prob = 0.56
    elif confidence >= 0.75:
        win_prob = 0.54
    elif confidence >= 0.70:
        win_prob = 0.52
    else:
        win_prob = 0.50
    
    return random.random() < win_prob

# ═══════════════════════════════════════════════════════
# SCAN DE SINAIS
# ═══════════════════════════════════════════════════════

def scan_trades(account):
    """Escaneia sinais com martingale real."""
    config = load_config()
    
    print("─" * 60)
    print(f"  📡 HERMES QUANT V2 — SCAN OTIMIZADO")
    print(f"  {datetime.now(timezone.utc).strftime('%d/%m/%Y %H:%M')} UTC")
    print(f"  Saldo: R$ {account['balance']:.2f} | Ciclo {account['cycle']}: {get_cycle_name(account['cycle'])}")
    print("─" * 60)
    
    total_trades = 0
    total_profit = 0.0
    
    for setup in config["active_setups"]:
        if not setup["enabled"]:
            continue
        
        symbol = setup["symbol"]
        tf = setup["tf"]
        threshold = setup["threshold"]
        stake_pct = setup["stake_pct"]
        mg_mult = setup["martingale_mult"]
        max_mg = setup["max_mg_consecutive"]
        setup_key = f"{symbol.split('/')[0]}_{tf}"
        
        # Garantir estado martingale
        if setup_key not in account["martingale"]:
            account["martingale"][setup_key] = {
                "active": False, "level": 0, "consecutive_losses": 0
            }
        
        mg_state = account["martingale"][setup_key]
        
        # Gerar sinais
        signals, msg = generate_signals(symbol, tf, min_prob=threshold)
        
        if not signals:
            continue
        
        # Filter by model_type if specified (e.g., "call_5" for M3/M15)
        allowed_type = setup.get("model_type", None)
        if allowed_type:
            _, period = allowed_type.split("_")
            signals = [s for s in signals if s.get("period") == period]
        
        for sig in signals:
            if not sig.get("tradable", False):
                print(f"  ⛔ {symbol.split('/')[0]:6s} {tf:4s} {sig['type']:4s} "
                      f"Conf: {sig['confidence']:.1%} | Bloqueado pelo filtro MRD")
                continue
            
            # Calcular stake com martingale
            stake = compute_mg_stake(
                account["balance"], stake_pct,
                mg_mult, mg_state["active"], mg_state["level"]
            )
            
            # Salvar estado ANTES de executar (para registro)
            mg_level_before = mg_state["level"] if mg_state["active"] else 0
            mg_active_before = mg_state["active"]
            
            # Simular resultado
            won = simulate_result(sig["confidence"])
            
            profit = round(stake * PAYOUT_RATE, 2) if won else -stake
            account["balance"] = round(account["balance"] + profit, 2)
            account["daily_trades"] += 1
            
            if won:
                account["daily_wins"] += 1
                account["current_streak"] = max(0, account["current_streak"]) + 1
                account["best_streak"] = max(account["best_streak"], account["current_streak"])
            else:
                account["daily_losses"] += 1
                account["current_streak"] = min(0, account["current_streak"]) - 1
                account["worst_streak"] = min(account["worst_streak"], account["current_streak"])
            
            # Atualizar martingale para PRÓXIMO trade
            update_mg_state(account, setup_key, won, max_mg)
            
            # Registrar trade
            trade = {
                "id": len(account["trades"]) + 1,
                "timestamp": int(time.time() * 1000),
                "datetime": datetime.now(timezone.utc).isoformat(),
                "symbol": symbol,
                "timeframe": tf,
                "type": sig["type"],
                "confidence": round(sig["confidence"], 4),
                "regime": sig.get("regime", "?"),
                "stake": stake,
                "payout": round(stake * PAYOUT_RATE, 2),
                "mg_active": mg_active_before,
                "mg_level": mg_level_before,
                "won": won,
                "profit": round(profit, 2),
                "balance": account["balance"],
            }
            account["trades"].append(trade)
            
            icon = "✅" if won else "❌"
            mg_icon = "⚡" if mg_active_before else "  "
            conf_str = f"{sig['confidence']:.1%}"
            
            print(f"  {icon}{mg_icon} {symbol.split('/')[0]:6s} {tf:4s} "
                  f"{sig['type']:4s} {conf_str} "
                  f"R$ {stake:>5.2f} {'+R$' + str(round(profit,2)) if won else '-R$' + str(round(-profit,2)):>8s} "
                  f"R$ {account['balance']:.2f}",
                  end="")
            if mg_active_before:
                print(f" [MG nível {mg_level_before}]")
            else:
                print()
            
            total_trades += 1
            total_profit += profit
    
    if total_trades == 0:
        print("  ⏳ Nenhum sinal com confiança suficiente no momento")
    
    # Atualizar ciclo
    account["cycle"] = determine_cycle(account["balance"], config)
    account["cycle_target"] = config["cycles"][min(account["cycle"] - 1, len(config["cycles"]) - 1)]["to"]
    
    save_account(account)
    
    print(f"\n  📊 Sessão: {total_trades} trades | P&L: R$ {total_profit:+.2f} | "
          f"Saldo: R$ {account['balance']:.2f}")
    print(f"  📈 Ciclo {account['cycle']}: {get_cycle_name(account['cycle'])} — "
          f"R$ {account['balance']:.2f} / R$ {account['cycle_target']:,.0f} "
          f"({account['balance']/account['cycle_target']*100:.1f}%)")
    
    if account["balance"] >= account["cycle_target"]:
        next_cycle = min(account["cycle"] + 1, len(config["cycles"]))
        next_target = config["cycles"][next_cycle - 1]["to"]
        print(f"\n  🎯 META DO CICLO {account['cycle']} ATINGIDA!")
        print(f"  Próximo: Ciclo {next_cycle}: {get_cycle_name(next_cycle)} → R$ {next_target:,.0f}")
    
    return total_trades

# ═══════════════════════════════════════════════════════
# STATUS
# ═══════════════════════════════════════════════════════

def show_status(account):
    config = load_config()
    total_trades = len(account["trades"])
    wins = sum(1 for t in account["trades"] if t["won"])
    losses = total_trades - wins
    wr = wins / total_trades if total_trades > 0 else 0
    total_profit = sum(t["profit"] for t in account["trades"])
    avg_profit = total_profit / total_trades if total_trades > 0 else 0
    
    # Stats martingale
    mg_trades = [t for t in account["trades"] if t.get("mg_active")]
    mg_wins = sum(1 for t in mg_trades if t["won"])
    mg_wr = mg_wins / len(mg_trades) if mg_trades else 0
    
    print("═" * 60)
    print(f"  📊 HERMES QUANT V2 — PAPER TRADE STATUS")
    print("═" * 60)
    print(f"  Saldo:      R$ {account['balance']:.2f}")
    print(f"  Inicial:    R$ {account['initial_balance']:.2f}")
    print(f"  Lucro:      R$ {total_profit:+.2f} ({total_profit/account['initial_balance']*100:+.1f}%)")
    print(f"  Ciclo:      {account['cycle']} — {get_cycle_name(account['cycle'])}")
    print(f"  Meta ciclo: R$ {account['cycle_target']:,.0f}")
    print(f"  Progresso:  {account['balance']/account['cycle_target']*100:.1f}%")
    print(f"\n  📈 Estatísticas:")
    print(f"  Total trades: {total_trades}")
    print(f"  Win/Loss:     {wins}/{losses}")
    print(f"  Win Rate:     {wr:.1%}")
    print(f"  Avg P&L:      R$ {avg_profit:.2f}")
    print(f"  Best streak:  {account['best_streak']}")
    print(f"  Worst streak: {account['worst_streak']}")
    print(f"\n  ⚡ Martingale:")
    print(f"  Trades MG:    {len(mg_trades)} ({mg_wins} wins, {len(mg_trades)-mg_wins} losses)")
    print(f"  MG Win Rate:  {mg_wr:.1%}")
    print(f"\n  🎯 Setups ativos:")
    for setup in config["active_setups"]:
        if not setup["enabled"]:
            continue
        key = f"{setup['symbol'].split('/')[0]}_{setup['tf']}"
        mg = account["martingale"].get(key, {})
        mg_status = f"⚡ Nível {mg.get('level', 0)}" if mg.get("active") else "● Normal"
        print(f"  {setup['symbol'].split('/')[0]:6s} {setup['tf']:4s} | "
              f"Threshold >{setup['threshold']:.0%} | "
              f"Stake {setup['stake_pct']:.1%} | {mg_status}")
    print("═" * 60)

def show_history(account, limit=10):
    trades = account["trades"][-limit:][::-1]
    print("─" * 60)
    print(f"  📜 ÚLTIMAS {len(trades)} TRADES")
    print("─" * 60)
    print(f"  {'#':>4s} {'Ativo':6s} {'Tipo':4s} {'Conf':5s} {'Stake':>7s} {'Result':>8s} {'MG':>3s} {'Saldo':>8s}")
    print(f"  {'─' * 48}")
    for t in trades:
        icon = "✅" if t["won"] else "❌"
        pf_str = f"+R$ {t['profit']:.2f}" if t["won"] else f"-R$ {-t['profit']:.2f}"
        mg_str = f"L{t.get('mg_level', 0)}" if t.get("mg_active") else "  "
        print(f"  {t['id']:>4d} {t['symbol'].split('/')[0]:6s} {t['type']:4s} "
              f"{t['confidence']:.0%} R$ {t['stake']:>5.2f} {pf_str:>8s} {mg_str:>3s}")
    print("─" * 60)
    # Resumo
    wins = sum(1 for t in trades if t["won"])
    total = len(trades)
    print(f"  📊 Período: {total} trades | {wins} wins | {total-wins} losses | WR {wins/total:.1%}" if total > 0 else "")

def show_projections():
    config = load_config()
    print("─" * 60)
    print("  🎯 METAS — 4 CICLOS")
    print("─" * 60)
    for c in config["cycles"]:
        print(f"  🔄 {c['name']:8s} R$ {c['from']:>5,.0f} → R$ {c['to']:>6,.0f} | "
              f"Risco {c['risk']:.1%} | ~{c['est_days']} dias")
    total_days = sum(c["est_days"] for c in config["cycles"])
    print(f"\n  🏆 Total: ~{total_days} dias | R$ {config['cycles'][0]['from']:.0f} → R$ {config['cycles'][-1]['to']:,.0f}")
    print("─" * 60)

def reset_account():
    account = load_account()
    config = load_config()
    account["balance"] = account["initial_balance"]
    account["trades"] = []
    account["daily_trades"] = 0
    account["daily_wins"] = 0
    account["daily_losses"] = 0
    account["current_streak"] = 0
    account["best_streak"] = 0
    account["worst_streak"] = 0
    account["cycle"] = 1
    account["cycle_target"] = config["cycles"][0]["to"]
    account["martingale"] = {}
    save_account(account)
    print(f"✅ Conta resetada: R$ {account['balance']:.2f}")

# ═══════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════

if __name__ == "__main__":
    import random
    action = sys.argv[1] if len(sys.argv) > 1 else "status"
    account = load_account()
    
    if action == "scan":
        scan_trades(account)
    elif action == "status":
        show_status(account)
    elif action == "history":
        limit = int(sys.argv[2]) if len(sys.argv) > 2 else 10
        show_history(account, limit)
    elif action == "reset":
        reset_account()
    elif action == "projections":
        show_projections()
    else:
        show_status(account)
