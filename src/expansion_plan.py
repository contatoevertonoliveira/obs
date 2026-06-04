#!/usr/bin/env python3
"""
Hermes Quant V2 — Estratégia de Crescimento Acelerado
=======================================================
Plano completo de expansão multi-ativo com juros compostos.

MATRIZ DE EXPANSÃO:
  Lote 1 (já temos): BTC ✅
  Lote 2 (próximo):  ETH, SOL
  Lote 3:             BNB, XRP, ADA
  Lote 4:             DOGE, LINK, AVAX, DOT

CICLO DE JUROS COMPOSTOS:
  Meta diária → reinvestimento automático → meta semanal → mensal

HORÁRIOS ÓTIMOS (volatilidade por período UTC):
  00:00-06:00  → Mercado asiático → BTC, ETH (alta liquidez)
  06:00-12:00  → Europa abrindo → ETH, SOL, LINK
  12:00-18:00  → Londres + NY → BTC, ETH, XRP, ADA (pico volatilidade)
  18:00-00:00  → NY tarde + Ásia reabrindo → DOGE, BNB, AVAX
"""
import os, sys, json, math
from datetime import datetime, timezone, timedelta

os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ".")
from config.settings import MODEL_DIR

# ═══════════════════════════════════════════════════════════
# 1. METAS COM JUROS COMPOSTOS
# ═══════════════════════════════════════════════════════════

class CompoundGrowthPlan:
    """
    Plano de crescimento com juros compostos sobre o capital.
    Cada dia: meta = capital_atual * (1 + taxa_diaria)ⁿ
    """
    
    def __init__(self, initial_capital=100, daily_target_pct=0.03, trade_size_pct=0.02):
        """
        Args:
            initial_capital: Capital inicial em USD
            daily_target_pct: Meta diária (3% = 0.03)
            trade_size_pct: Tamanho de cada trade (% do capital)
        """
        self.capital = initial_capital
        self.daily_target = daily_target_pct
        self.trade_size = trade_size_pct
        self.bank = initial_capital
        self.current_day = 0
        self.history = []
    
    def project(self, days=365):
        """Projeta crescimento por N dias."""
        cap = self.capital
        results = []
        
        for day in range(1, days + 1):
            trade_budget = cap * self.trade_size
            daily_gain = cap * self.daily_target
            cap += daily_gain
            
            results.append({
                "day": day,
                "capital": round(cap, 2),
                "daily_gain": round(daily_gain, 2),
                "trade_budget": round(trade_budget, 2),
                "trades_needed": max(1, int(math.ceil(self.daily_target / 0.01))),
            })
        
        return results
    
    def simulate_trades(self, win_rate=0.619, payout=0.80, trades_per_day=5):
        """Simula trades reais com WR definida."""
        import random
        random.seed(42)
        
        cap = self.capital
        results = []
        
        for day in range(1, 366):
            trade_size = cap * self.trade_size
            day_pnl = 0
            day_trades = 0
            
            for _ in range(trades_per_day):
                if random.random() < win_rate:
                    day_pnl += trade_size * payout  # win
                else:
                    day_pnl -= trade_size  # loss
                day_trades += 1
            
            cap += day_pnl
            self.bank = cap
            
            results.append({
                "day": day,
                "capital": round(cap, 2),
                "day_pnl": round(day_pnl, 2),
                "trades": day_trades,
            })
        
        return results
    
    def goal_summary(self, projection):
        """Resumo das metas."""
        milestones = [30, 90, 180, 365]
        lines = []
        
        lines.append(f"\n{'─' * 62}")
        lines.append(f"  📈 PLANO DE JUROS COMPOSTOS")
        lines.append(f"{'─' * 62}")
        lines.append(f"  Capital inicial:     ${self.capital:.2f}")
        lines.append(f"  Meta diária:         {self.daily_target:.1%}")
        lines.append(f"  Por trade:           {self.trade_size:.1%} do capital")
        lines.append(f"{'─' * 62}")
        
        for m in milestones:
            data = projection[m - 1] if m <= len(projection) else projection[-1]
            gain = (data["capital"] / self.capital - 1) * 100
            lines.append(
                f"  📍 {m:3d} dias: ${data['capital']:>8,.2f}  "
                f"(+{gain:+.0f}% | ${data['capital'] - self.capital:>+,.2f})"
                f"  | {data['trades_needed']} trades/dia necessários"
            )
        
        return "\n".join(lines)


# ═══════════════════════════════════════════════════════════
# 2. MATRIZ DE HORÁRIOS
# ═══════════════════════════════════════════════════════════

TRADING_MATRIX = {
    "00:00-04:00": {
        "label": "🌙 Ásia Madrugada",
        "pairs": ["BTC/USDT", "ETH/USDT"],
        "profile": "Baixa volatilidade, movimentos suaves",
        "recommended": "M15 (menos ruído)",
        "risk_mult": 0.7,
    },
    "04:00-08:00": {
        "label": "🌅 Ásia Tarde + Europa Abrindo",
        "pairs": ["BTC/USDT", "ETH/USDT", "SOL/USDT"],
        "profile": "Volatilidade crescente",
        "recommended": "M5, M15",
        "risk_mult": 0.85,
    },
    "08:00-12:00": {
        "label": "☀️ Europa Ativa",
        "pairs": ["BTC/USDT", "ETH/USDT", "SOL/USDT", "BNB/USDT"],
        "profile": "Boa volatilidade, movimentos técnicos",
        "recommended": "M5, M1 (se M5 validar)",
        "risk_mult": 1.0,
    },
    "12:00-16:00": {
        "label": "🔥 Londres + NY Abertura",
        "pairs": ["BTC/USDT", "ETH/USDT", "XRP/USDT", "ADA/USDT", "LINK/USDT"],
        "profile": "PICO de volatilidade, maiores movimentos",
        "recommended": "M1, M5",
        "risk_mult": 1.2,
    },
    "16:00-20:00": {
        "label": "⚡ NY Ativo + Europa Fechando",
        "pairs": ["BTC/USDT", "ETH/USDT", "SOL/USDT", "DOGE/USDT", "AVAX/USDT"],
        "profile": "Alta volatilidade com reversões",
        "recommended": "M5 (evitar M1 devido a spreads)",
        "risk_mult": 1.0,
    },
    "20:00-00:00": {
        "label": "🌆 NY Tarde + Ásia Preparando",
        "pairs": ["BTC/USDT", "ETH/USDT", "DOT/USDT", "LINK/USDT"],
        "profile": "Volatilidade moderada, tendências mais claras",
        "recommended": "M15, M5",
        "risk_mult": 0.85,
    },
}


# ═══════════════════════════════════════════════════════════
# 3. EXPANSÃO EM LOTES
# ═══════════════════════════════════════════════════════════

EXPANSION_PLAN = {
    "lote_1_btc": {
        "symbols": ["BTC/USDT"],
        "status": "✅ COMPLETO",
        "timeframes": ["1m", "5m"],
        "models": True,
        "backtest": True,
    },
    "lote_2_eth_sol": {
        "symbols": ["ETH/USDT", "SOL/USDT"],
        "status": "🔄 COLETANDO DADOS",
        "timeframes": ["1m", "5m", "15m"],
        "models": False,
        "backtest": False,
        "estimated_time": "1-2h de coleta",
    },
    "lote_3_bnb_xrp_ada": {
        "symbols": ["BNB/USDT", "XRP/USDT", "ADA/USDT"],
        "status": "⏳ AGUARDANDO",
        "timeframes": ["1m", "5m", "15m"],
        "models": False,
        "backtest": False,
        "estimated_time": "2-4h de coleta",
    },
    "lote_4_doge_link_avax_dot": {
        "symbols": ["DOGE/USDT", "LINK/USDT", "AVAX/USDT", "DOT/USDT"],
        "status": "⏳ AGUARDANDO",
        "timeframes": ["1m", "5m", "15m"],
        "models": False,
        "backtest": False,
        "estimated_time": "3-5h de coleta",
    },
}


# ═══════════════════════════════════════════════════════════
# 4. GERADOR DO RELATÓRIO
# ═══════════════════════════════════════════════════════════

def generate_expansion_report():
    """Gera relatório completo de expansão."""
    lines = []
    
    # Plano de juros compostos
    plan = CompoundGrowthPlan(
        initial_capital=100,
        daily_target_pct=0.03,  # 3% ao dia
        trade_size_pct=0.02     # 2% por trade
    )
    projection = plan.project(365)
    lines.append(plan.goal_summary(projection))
    
    # Simulação realista com WR 61.9%
    lines.append(f"\n  📊 SIMULAÇÃO REALISTA (WR 61.9%, payout 80%)")
    sim = plan.simulate_trades(win_rate=0.619, payout=0.80, trades_per_day=5)
    
    milestones = [30, 90, 180, 365]
    for m in milestones:
        if m <= len(sim):
            data = sim[m - 1]
            total_trades = sum(s["trades"] for s in sim[:m])
            lines.append(
                f"    📍 {m:3d} dias: ${data['capital']:>8,.2f}  "
                f"({total_trades:.0f} trades | PnL ${data['day_pnl']:>+.2f}/dia)"
            )
    
    # Matriz de horários
    lines.append(f"\n{'─' * 62}")
    lines.append(f"  🕐 MATRIZ DE TRADING — 24h")
    lines.append(f"{'─' * 62}")
    
    for period, info in TRADING_MATRIX.items():
        lines.append(
            f"  {period:14s} {info['label']:30s} | "
            f"{', '.join(p.split('/')[0] for p in info['pairs'])}"
        )
        lines.append(f"  {'':14s} → {info['profile']}")
        lines.append(f"  {'':14s} → {info['recommended']} | risco x{info['risk_mult']}")
        lines.append("")
    
    # Plano de expansão
    lines.append(f"{'─' * 62}")
    lines.append(f"  🚀 PLANO DE EXPANSÃO — LOTES")
    lines.append(f"{'─' * 62}")
    
    for lote, info in EXPANSION_PLAN.items():
        symbols_str = ", ".join(s.split("/")[0] for s in info["symbols"])
        lines.append(f"  {info['status']} {lote:20s} → {symbols_str}")
        lines.append(f"    TFs: {', '.join(info['timeframes'])} | {info.get('estimated_time', '')}")
    
    # Métricas compostas
    lines.append(f"\n{'─' * 62}")
    lines.append(f"  🎯 META: CAPITAL INICIAL × CRESCIMENTO")
    lines.append(f"{'─' * 62}")
    
    compound_examples = [
        (100, 0.03, 365, "$100 → $484.827"),
        (100, 0.05, 365, "$100 → $54.218.872 (otimista)"),
        (100, 0.02, 365, "$100 → $1.377 (conservador)"),
    ]
    
    for cap, rate, days, result in compound_examples:
        final = cap * (1 + rate) ** days
        lines.append(f"  R${cap} x {rate:.0%} ao dia x {days} dias = **R${final:_.2f}**")
    
    lines.append(f"\n{'─' * 62}")
    lines.append(f"  ⚠️ NOTA: Juros compostos de 3% ao dia NÃO são lineares.")
    lines.append(f"  A simulação realista com WR 61.9% mostra o cenário provável.")
    lines.append(f"  O plano considera reinvestimento total até o saque.")
    lines.append(f"{'─' * 62}")
    
    return "\n".join(lines)


def generate_schedule_config():
    """Gera configuração de jobs automáticos para cobrir 24h."""
    jobs = []
    
    for period, info in TRADING_MATRIX.items():
        start_hour = int(period.split(":")[0])
        pairs = info["pairs"]
        
        jobs.append({
            "time": f"{start_hour:02d}:00",
            "period": period,
            "pairs": [p.split("/")[0] for p in pairs],
            "tf": info["recommended"],
            "risk": info["risk_mult"],
        })
    
    return jobs


# ═══════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════

if __name__ == "__main__":
    report = generate_expansion_report()
    print(report)
    
    # Salvar como JSON
    output = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "matrix": {k: {
            "label": v["label"],
            "pairs": v["pairs"],
            "profile": v["profile"],
            "recommended": v["recommended"],
            "risk_mult": v["risk_mult"],
        } for k, v in TRADING_MATRIX.items()},
        "expansion_plan": {k: {
            "symbols": v["symbols"],
            "status": v["status"],
        } for k, v in EXPANSION_PLAN.items()},
    }
    
    out_path = os.path.join(MODEL_DIR, "expansion_plan.json")
    with open(out_path, "w") as f:
        json.dump(output, f, indent=2)
    print(f"\n📁 Config salva em: {out_path}")
