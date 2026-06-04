#!/usr/bin/env python3
"""
HERMES QUANT V2 — TRADING AGENT
=================================
Executado pelos cron jobs das sessões de trading.
Gera sinais CALL/PUT com base nos modelos treinados + MRD + Compound Tracker.

Uso:
  python3 src/trading_agent.py session   → Executa sessão atual
  python3 src/trading_agent.py status    → Status geral do dia
"""
import os, sys, json
from datetime import datetime, timezone

os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ".")
from config.settings import MODEL_DIR, PAYOUT_RATE, SYMBOLS
from src.compound_tracker import METAS_BRL, gerar_projecao_completa
from src.signal_engine import generate_signals


# Sessões de trading
SESSOES = [
    {"nome": "🌅 Londres", "horario": 12, "ativos": ["BTC/USDT", "ETH/USDT", "SOL/USDT", "BNB/USDT"], "multi": 1.0},
    {"nome": "⚡ Nova York", "horario": 17, "ativos": ["XRP/USDT", "ADA/USDT", "LINK/USDT"], "multi": 1.2},
    {"nome": "🌙 Pré-Ásia", "horario": 23, "ativos": ["DOGE/USDT", "AVAX/USDT", "DOT/USDT"], "multi": 0.85},
]


def get_current_sessions():
    """Identifica a(s) sessão(ões) ativa(s) agora."""
    now = datetime.now(timezone.utc)
    hora = now.hour
    
    ativas = []
    for s in SESSOES:
        # Sessão ativa nas próximas 3 horas
        if s["horario"] <= hora < s["horario"] + 3:
            ativas.append(s)
    
    return ativas


def executar_sessao():
    """Executa a sessão atual: gera sinais, calcula metas."""
    now = datetime.now(timezone.utc)
    
    print("─" * 60)
    print(f"  🤖 HERMES QUANT V2 — TRADING AGENT")
    print(f"  {now.strftime('%d/%m/%Y %H:%M')} UTC")
    print("─" * 60)
    
    # Sessão atual
    sessoes = get_current_sessions()
    if not sessoes:
        print("\n  ⏰ Fora do horário das sessões.")
        print("  Próximas sessões:")
        for s in SESSOES:
            h = s["horario"]
            if h > now.hour:
                print(f"    {s['nome']} — {h}h UTC")
        return
    
    for sessao in sessoes:
        print(f"\n  📍 {sessao['nome']} (multiplicador: {sessao['multi']}x)")
        print(f"  Ativos: {', '.join(a.split('/')[0] for a in sessao['ativos'])}")
        print()
        
        for symbol in sessao['ativos']:
            if symbol not in SYMBOLS:
                continue
            
            for tf in ["1m"]:
                signals, msg = generate_signals(symbol, tf, min_prob=0.60)
                
                if signals:
                    for sig in signals:
                        icon = "✅" if sig.get("tradable", False) else "⛔"
                        conf = sig["confidence"]
                        tipo = sig["type"]
                        regime = sig.get("regime", "?")
                        
                        # Aplicar multiplicador da sessão
                        conf_ajustada = conf * sessao["multi"]
                        
                        print(
                            f"  {icon} {symbol.split('/')[0]:6s} "
                            f"{tipo:4s} | "
                            f"Conf: {conf:.1%} (ajust: {conf_ajustada:.1%}) | "
                            f"Regime: {regime}"
                        )
                else:
                    sym_short = symbol.split('/')[0]
                    print(f"  ⏳ {sym_short:6s} — {msg}")
        
        # Estatísticas da sessão
        print()
        print(f"  📊 Meta hoje:")
        print(f"    Meta 1: R$ 1.000 ({'🏁' if False else '🔄 em progresso'})")
        print(f"    Meta 2: R$ 10.000")
        print(f"    Meta 3: R$ 50.000")
    
    # Resumo diário
    print()
    print("─" * 60)
    print("  📈 RESUMO DO DIA")
    
    # Lógica de compound tracking
    proj = gerar_projecao_completa(100.0)
    for p in proj:
        if not p.get("atingida", False):
            nome = p["nome"]
            trades = p.get("trades_necessarios", 0)
            dias = p.get("dias_estimados", 0)
            print(f"    {nome}: ~{trades:,} trades • ~{dias} dias")
            break
    
    print("─" * 60)
    print("  ✅ Sessão concluída — próximo scan em 30min")


def status_geral():
    """Mostra status geral do sistema."""
    proj = gerar_projecao_completa(100.0)
    
    print("─" * 60)
    print("  📊 HERMES QUANT — STATUS GERAL")
    print("─" * 60)
    print()
    
    # Metas
    print("  🎯 METAS:")
    for p in proj:
        meta = p["meta"]
        atingida = p.get("atingida", False)
        if atingida:
            print(f"    ✅ {p['nome']}: R$ {meta:,.0f} (atingida!)")
        else:
            trades = p.get("trades_necessarios", 0)
            dias = p.get("dias_estimados", 0)
            print(f"    🔄 {p['nome']}: R$ {meta:,.0f} (~{trades:,} trades, ~{dias} dias)")
    
    # Sessões do dia
    print()
    print("  📅 SESSÕES DE HOJE:")
    for s in SESSOES:
        ativos = ", ".join(a.split("/")[0] for a in s["ativos"])
        print(f"    {s['nome']} — {s['horario']}h UTC: {ativos}")
    
    # Próximos cron jobs
    print()
    print("  ⏰ PRÓXIMOS JOBS:")
    print("    📊 Dashboard: 08:00 UTC (diário)")
    print(f"    ⚡ Próxima sessão: {SESSOES[0]['nome']} {SESSOES[0]['horario']}h UTC")
    
    print("─" * 60)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "status":
        status_geral()
    else:
        executar_sessao()
