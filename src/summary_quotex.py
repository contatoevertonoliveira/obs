#!/usr/bin/env python3.12
"""Resumo geral de todos os modelos Quotex - versão limpa e honesta."""
import os, sys, json, warnings
import pandas as pd
import numpy as np
import joblib
from datetime import datetime
warnings.filterwarnings("ignore")

os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.getcwd())

MODEL_DIR = "models/quotex"
PROC_DIR = "data/processed/quotex"

# Carregar resultados do treino
with open(f"{MODEL_DIR}/training_results.json") as f:
    train_results = json.load(f)

print("=" * 68)
print("  📊 RESUMO GERAL - TODOS OS MODELOS QUOTEX")
print(f"  {datetime.now().strftime('%d/%m/%Y %H:%M')} UTC")
print("=" * 68)

# Para cada combinação ativo+TF, mostrar os 4 targets
ativos_tfs = sorted(set(k for k in train_results.keys()))

# Tabela consolidadora
print(f"\n{'ATIVO':6s} {'TF':4s} | {'call_1':>12s} {'put_1':>12s} {'call_5':>12s} {'put_5':>12s}")
print("-" * 58)

viable = []  # (ativo, TF, target, WR, trades, exp)

for atf in ativos_tfs:
    combos = train_results[atf]
    name, tf = atf.split("_")
    
    targets_info = {}
    for tgt in ["target_call_1", "target_put_1", "target_call_5", "target_put_5"]:
        if tgt not in combos:
            targets_info[tgt] = "  sem dados   "
            continue
        
        m = combos[tgt]
        wr = m.get("wr_th0.7", 0)
        trades = m.get("trades_th0.7", 0)
        exp = m.get("exp_th0.7", -1)
        
        if trades >= 10 and exp > 0:
            flag = "✅"
            viable.append((exp, name, tf, tgt.replace("target_", ""), wr, trades))
        elif trades >= 10:
            flag = "⚠️"
        else:
            flag = "⬜"
        
        stats = f"{flag} WR{wr:.0%} ({trades:>3d})"
        targets_info[tgt] = stats
    
    print(f"{name:6s} {tf:4s} | {targets_info['target_call_1']:>12s} {targets_info['target_put_1']:>12s} {targets_info['target_call_5']:>12s} {targets_info['target_put_5']:>12s}")

# Modelos viáveis
print(f"\n{'='*68}")
print(f"  🏆 MODELOS VIÁVEIS (th=0.7, trades>=10, exp>0)")
print(f"{'='*68}")

viable_sorted = sorted(viable, reverse=True)

print(f"\n{'ATIVO':6s} {'TF':4s} {'TARGET':12s} {'WR':>8s} {'TRADES':>8s} {'EXPECT':>8s}")
print("-" * 48)

for exp, name, tf, target, wr, trades in viable_sorted:
    print(f"{name:6s} {tf:4s} {target:12s} {wr:.1%}  {trades:>4d}     {exp:.1%}")

# Sumário executivo
print(f"\n{'='*68}")
print(f"  📋 SUMÁRIO EXECUTIVO")
print(f"{'='*68}")

# Por timeframe
for tf_name in ["M1", "M5", "M15"]:
    tf_viable = [(exp, name, target, wr, trades) for exp, name, tf, target, wr, trades in viable_sorted if tf == tf_name]
    if tf_viable:
        print(f"\n  📈 {tf_name}: {len(tf_viable)} modelos viáveis")
        for exp, name, target, wr, trades in tf_viable[:5]:
            print(f"      {name:4s} {target:12s}: WR {wr:.1%} ({trades:>3d} trades, exp {exp:.1%})")

# Recomendação para paper trade
print(f"\n{'='*68}")
print(f"  🎯 RECOMENDAÇÃO PARA PAPER TRADE (conta DEMO)")
print(f"{'='*68}")

# Melhores setups considerando consistência
print(f"\n  CRITÉRIOS: WR>55%, trades>=20, exp>0\n")
for exp, name, tf, target, wr, trades in viable_sorted:
    if wr > 0.55 and trades >= 20:
        stake = "2.0%" if exp > 0.20 else "1.5%" if exp > 0.10 else "1.0%"
        mg = "Sim" if wr > 0.65 else "Não"
        print(f"  ✅ {name:4s} {tf:4s} {target:12s}: WR {wr:.1%} ({trades:>3d} trades, exp {exp:.1%}) | stake {stake} | martingale {mg}")

print(f"\n{'='*68}")
print(f"  📁 Modelos salvos em: {MODEL_DIR}/")
print(f"  📁 Dados processados: {PROC_DIR}/")
print("=" * 68)
