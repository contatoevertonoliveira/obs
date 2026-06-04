#!/usr/bin/env python3
"""
Hermes Quant V2 — Coleta Multi-Ativo Automática
Coleta todos os símbolos pendentes em ordem de prioridade.
Usa checkpointing para retomar de onde parou.
"""
import os, sys, json, time, subprocess
from datetime import datetime, timezone

os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ".")
from config.settings import RAW_DIR

# ═══════════════════════════════════════════════════════════
# ORDEM DE PRIORIDADE
# ═══════════════════════════════════════════════════════════

PRIORITY_SYMBOLS = [
    "ETH/USDT",    # Lote 2 — já começou
    "SOL/USDT",    # Lote 2
    "BNB/USDT",    # Lote 3
    "XRP/USDT",    # Lote 3
    "ADA/USDT",    # Lote 3
    "DOGE/USDT",   # Lote 4
    "LINK/USDT",   # Lote 4
    "AVAX/USDT",   # Lote 4
    "DOT/USDT",    # Lote 4
]

TIMEFRAMES = ["1m", "5m", "15m"]


def check_progress():
    """Verifica o que já foi coletado."""
    checkpoint_file = os.path.join(RAW_DIR, ".checkpoints.json")
    checkpoints = {}
    if os.path.exists(checkpoint_file):
        with open(checkpoint_file) as f:
            checkpoints = json.load(f)

    now_ms = int(time.time() * 1000)
    three_years_ago = now_ms - 3 * 365 * 24 * 3600 * 1000

    print(f"{'Símbolo':12s} {'TF':4s} {'Status':20s} {'Progresso':>10s}")
    print("-" * 50)

    for symbol in PRIORITY_SYMBOLS:
        for tf in TIMEFRAMES:
            key = f"{symbol}:{tf}"
            cp = checkpoints.get(key, 0)

            if cp == 0:
                status = "⏳ Pendente"
                pct = 0
            elif cp >= now_ms - 3600000:  # < 1h atrás → completo
                status = "✅ Completo"
                pct = 100
            else:
                pct = min(99, (cp - three_years_ago) / (now_ms - three_years_ago) * 100)
                status = f"🔄 {pct:.0f}%"

            sym_short = symbol.split("/")[0]
            print(f"{sym_short:12s} {tf:4s} {status:20s} {pct:>9.0f}%")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "check":
        check_progress()
    else:
        # Iniciar coleta via data_collector modificado
        print("🚀 Iniciando coleta multi-ativo em lote...")
        print(f"   Símbolos: {', '.join(s.split('/')[0] for s in PRIORITY_SYMBOLS)}")
        print(f"   Timeframes: {', '.join(TIMEFRAMES)}")
        print()

        # Atualizar settings para coletar só o necessário
        import importlib
        spec = importlib.util.spec_from_file_location("settings", "config/settings.py")
        settings = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(settings)

        collector_path = os.path.join("src", "data_collector.py")

        # Executar o collector que vai puxar do checkpoint
        result = subprocess.run(
            [sys.executable, "-u", collector_path],
            capture_output=True, text=True, timeout=7200
        )
        print(result.stdout[-2000:] if len(result.stdout) > 2000 else result.stdout)
        if result.stderr:
            print("STDERR:", result.stderr[-500:])
