#!/usr/bin/env python3
"""
HERMES QUANT V2 — COMPOUND TRACKER 6M
=======================================
Acompanhamento dos 4 ciclos para atingir R$ 50.000 em 6 meses.

Ciclo 1 - Seed:     R$ 100 → R$ 500   (5x)  ~30 dias | 15 trades/dia | 2% risco
Ciclo 2 - Growth:   R$ 500 → R$ 3.000 (6x)  ~45 dias | 12 trades/dia | 1.5% risco
Ciclo 3 - Scale:    R$ 3.000 → R$ 15.000 (5x) ~55 dias | 10 trades/dia | 1.2% risco
Ciclo 4 - Legacy:   R$ 15.000 → R$ 50.000 (3.3x) ~50 dias | 8 trades/dia | 1% risco

Total: R$ 100 → R$ 50.000 em ~180 dias (6 meses)
"""
import json, os, sys
from datetime import datetime, timezone

os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ".")
from config.settings import MODEL_DIR, PAYOUT_RATE

# ═══════════════════════════════════════════════════════════
# CICLOS
# ═══════════════════════════════════════════════════════════

CYCLES_6M = [
    {
        "name": "Seed",
        "emoji": "🌱",
        "from": 100.0,
        "to": 500.0,
        "mult": 5.0,
        "trades_per_day": 15,
        "risk_pct": 2.0,
        "mg_levels": 2,
        "est_days": 30,
        "description": "Foco em consolidar o sistema e validar a estratégia",
        "color": "#00d4aa",
    },
    {
        "name": "Growth",
        "emoji": "🔥",
        "from": 500.0,
        "to": 3000.0,
        "mult": 6.0,
        "trades_per_day": 12,
        "risk_pct": 1.5,
        "mg_levels": 2,
        "est_days": 45,
        "description": "Expandir multi-ativos e aumentar frequência",
        "color": "#00ffcc",
    },
    {
        "name": "Scale",
        "emoji": "⚡",
        "from": 3000.0,
        "to": 15000.0,
        "mult": 5.0,
        "trades_per_day": 10,
        "risk_pct": 1.2,
        "mg_levels": 1,
        "est_days": 55,
        "description": "Operar com todos os 10 ativos, gestão profissional",
        "color": "#ffaa00",
    },
    {
        "name": "Legacy",
        "emoji": "🏆",
        "from": 15000.0,
        "to": 50000.0,
        "mult": 3.33,
        "trades_per_day": 8,
        "risk_pct": 1.0,
        "mg_levels": 0,
        "est_days": 50,
        "description": "Capital grande, risco reduzido, consistência",
        "color": "#ff4466",
    },
]


def calcular_projecao(capital_inicial=100.0, wr=0.619, payout=PAYOUT_RATE, days=180):
    """
    Simula a evolução do capital ao longo dos dias.
    Usando a expectativa real do backtest: +11.37% por trade.
    """
    exp_por_trade = wr * payout - (1 - wr)

    timeline = []
    capital = capital_inicial
    ciclo_atual = 0

    for dia in range(1, days + 1):
        # Determinar ciclo atual baseado no capital
        while ciclo_atual < len(CYCLES_6M) and capital >= CYCLES_6M[ciclo_atual]["to"]:
            ciclo_atual += 1

        ciclo = CYCLES_6M[ciclo_atual] if ciclo_atual < len(CYCLES_6M) else CYCLES_6M[-1]

        tpd = ciclo["trades_per_day"]
        risk = ciclo["risk_pct"] / 100

        # Expectativa diária com este ciclo
        capital_risco = capital * risk
        daily_return = tpd * capital_risco * exp_por_trade

        # Avançar capital
        capital += daily_return

        # A cada 5 dias salvar checkpoint
        if dia % 5 == 0 or dia == 1 or capital >= CYCLES_6M[min(ciclo_atual, len(CYCLES_6M)-1)]["to"]:
            timeline.append({
                "dia": dia,
                "capital": round(capital, 2),
                "ciclo": ciclo["name"],
                "ciclo_idx": ciclo_atual,
                "trades_hoje": tpd,
                "lucro_hoje": round(daily_return, 2),
                "pct_meta_6m": round(min(100, (capital - capital_inicial) / (50000 - capital_inicial) * 100), 1),
            })

    return timeline


def gerar_relatorio(capital_inicial=100.0):
    """Gera relatório completo dos 4 ciclos."""
    lines = []
    lines.append("═" * 62)
    lines.append("  🎯 HERMES QUANT V2 — PLANO 6 MESES (4 CICLOS)")
    lines.append("═" * 62)
    lines.append(f"  Capital inicial: R$ {capital_inicial:.2f}")
    lines.append(f"  Meta final: R$ 50.000,00")
    lines.append(f"  Crescimento: {50000/capital_inicial:.0f}x em 180 dias")
    lines.append(f"  WR base: 61.9% · Payout: {PAYOUT_RATE:.0%} · Exp/trade: +11.37%")
    lines.append("═" * 62)

    for i, ciclo in enumerate(CYCLES_6M):
        lines.append(f"\n  {ciclo['emoji']} {ciclo['name']:8s} — R$ {ciclo['from']:>6,.0f} → R$ {ciclo['to']:>6,.0f} ({ciclo['mult']:.0f}x)")
        lines.append(f"      {'─' * 40}")
        lines.append(f"      Trades/dia: {ciclo['trades_per_day']}")
        lines.append(f"      Risco/trade: {ciclo['risk_pct']:.1f}%")
        lines.append(f"      Martingale: {ciclo['mg_levels']} níveis")
        lines.append(f"      Previsão: ~{ciclo['est_days']} dias")
        lines.append(f"      {ciclo['description']}")

    # Simulação
    timeline = calcular_projecao(capital_inicial, days=180)

    lines.append(f"\n{'═' * 62}")
    lines.append(f"  📈 PROJEÇÃO DIA A DIA")
    lines.append(f"{'═' * 62}")
    lines.append(f"  {'Dia':>5s} {'Capital':>10s} {'Ciclo':12s} {'Trades':>7s} {'Lucro':>8s} {'% Meta':>7s}")
    lines.append(f"  {'─' * 50}")

    for t in timeline:
        lines.append(f"  {t['dia']:>5d} R$ {t['capital']:>8.2f} {t['ciclo']:12s} {t['trades_hoje']:>5d} R$ {t['lucro_hoje']:>6.2f} {t['pct_meta_6m']:>6.1f}%")

    # Marcos
    lines.append(f"\n{'═' * 62}")
    lines.append(f"  🏆 MARCOS")
    lines.append(f"{'═' * 62}")
    for t in timeline:
        if t["capital"] >= 500:
            lines.append(f"  ✅ {t['ciclo']:8s}: R$ {t['capital']:>8.2f} no dia {t['dia']}")
            break
    for t in timeline:
        if t["capital"] >= 3000:
            lines.append(f"  ✅ Growth:   R$ {t['capital']:>8.2f} no dia {t['dia']}")
            break
    for t in timeline:
        if t["capital"] >= 15000:
            lines.append(f"  ✅ Scale:    R$ {t['capital']:>8.2f} no dia {t['dia']}")
            break
    for t in timeline:
        if t["capital"] >= 50000:
            lines.append(f"  ✅ Legacy:   R$ {t['capital']:>8.2f} no dia {t['dia']} — 🏆 META ATINGIDA!")
            break

    return "\n".join(lines), timeline


def calcular_estrategia_agressiva(wr=0.619, payout=PAYOUT_RATE):
    """
    Calcula quantos trades/dia são necessários para cada ciclo
    atingir a meta no prazo estimado.
    """
    exp = wr * payout - (1 - wr)

    results = []
    for ciclo in CYCLES_6M:
        capital_medio = (ciclo["from"] + ciclo["to"]) / 2
        risk_per_trade = capital_medio * ciclo["risk_pct"] / 100
        profit_per_trade = risk_per_trade * exp
        trades_necessarios = (ciclo["to"] - ciclo["from"]) / max(profit_per_trade, 0.01)
        trades_por_dia = trades_necessarios / max(ciclo["est_days"], 1)

        results.append({
            "ciclo": ciclo["name"],
            "capital_medio": round(capital_medio, 2),
            "risk_trade": round(risk_per_trade, 2),
            "profit_trade": round(profit_per_trade, 2),
            "trades_necessarios": round(trades_necessarios),
            "trades_dia": round(trades_por_dia, 1),
            "tpd_config": ciclo["trades_per_day"],
            "viable": trades_por_dia <= ciclo["trades_per_day"] * 1.2,
        })

    return results


def save_cycles():
    """Salva configuração dos ciclos para o dashboard."""
    config = {
        "cycles": {f"c{i+1}": c for i, c in enumerate(CYCLES_6M)},
        "projection": calcular_projecao(days=180),
        "strategy": calcular_estrategia_agressiva(),
        "meta_6m": 50000,
        "capital_inicial": 100,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    path = os.path.join(MODEL_DIR, "compound_projection.json")
    with open(path, "w") as f:
        json.dump(config, f, indent=2, default=str)
    return path


# ═══════════════════════════════════════════════════════════
# METAS_BRL — metas em reais (compatível com trading_agent.py)
# ═══════════════════════════════════════════════════════════

METAS_BRL = {
    "meta_1": {"nome": "Seed",   "valor": 500.0,   "atingida": False},
    "meta_2": {"nome": "Growth", "valor": 3000.0,  "atingida": False},
    "meta_3": {"nome": "Scale",  "valor": 15000.0, "atingida": False},
    "meta_4": {"nome": "Legacy", "valor": 50000.0, "atingida": False},
}


def gerar_projecao_completa(capital_inicial=100.0):
    """
    Retorna lista de projeções por ciclo no formato esperado
    pelo trading_agent.py e dashboard.
    """
    proj = calcular_projecao(capital_inicial, days=180)
    # Último ponto da projeção
    final = proj[-1] if proj else {"capital": capital_inicial}
    capital_atual = final["capital"]

    resultados = []
    for ciclo in CYCLES_6M:
        atingida = capital_atual >= ciclo["to"]
        # Estimar trades necessários até esta meta
        estimativa = calcular_estrategia_agressiva()
        est = next((e for e in estimativa if e["ciclo"] == ciclo["name"]), None)
        resultados.append({
            "nome": ciclo["name"],
            "emoji": ciclo["emoji"],
            "meta": ciclo["to"],
            "atingida": atingida,
            "trades_necessarios": est["trades_necessarios"] if est else 0,
            "dias_estimados": ciclo["est_days"],
            "capital_atual": round(capital_atual, 2),
            "color": ciclo["color"],
        })
    return resultados


if __name__ == "__main__":
    # Gerar relatório
    relatorio, timeline = gerar_relatorio()

    # Salvar configuração
    path = save_cycles()
    print(relatorio)
    print(f"\n📁 Config salva: {path}")

    # Análise de viabilidade
    print(f"\n{'═' * 62}")
    print(f"  📊 ANÁLISE DE VIABILIDADE")
    print(f"{'═' * 62}")
    estrategia = calcular_estrategia_agressiva()
    for e in estrategia:
        icon = "✅" if e["viable"] else "⚠️"
        print(f"  {icon} {e['ciclo']:8s}: {e['trades_dia']:.1f} trades/dia necessários "
              f"(config: {e['tpd_config']}/dia) | "
              f"R$ {e['risk_trade']:.2f}/trade | Lucro R$ {e['profit_trade']:.2f}/trade")
