#!/usr/bin/env python3
"""Status do pipeline Hermes Quant V2."""
import pandas as pd, os, sys
sys.path.insert(0, "/root/hermes-quant-v2")
from config.settings import SYMBOLS, INPUT_TFS, CONTEXT_TFS, TF_LABEL, RAW_DIR, PROCESSED_DIR, MODEL_DIR

print("=" * 70)
print("  ESTADO DO PIPELINE — HERMES QUANT V2")
print("=" * 70)
print()
print(f"  {'Ativo':<10s} {'TF':<5s} {'Raw':<9s} {'Features':<11s} {'Modelo':<9s} {'MRD':<6s} {'Candles':<10s}")
print(f"  {'-'*60}")

total_pairs = len(SYMBOLS) * len(INPUT_TFS)
raw_count = feat_count = model_count = mrd_count = 0

for s in SYMBOLS:
    for tf in INPUT_TFS:
        label = TF_LABEL.get(tf, tf)
        prefix = s.replace("/", "_")
        
        raw_path = os.path.join(RAW_DIR, f"{prefix}_{label}.parquet")
        feat_path = os.path.join(PROCESSED_DIR, f"{prefix}_{label}_features.parquet")
        xgb_path = os.path.join(MODEL_DIR, f"{prefix}_{label}_call_1_xgb.json")
        mrd_path = os.path.join(MODEL_DIR, f"{prefix}_{label}_regime_perf.json")
        
        has_raw = os.path.exists(raw_path)
        has_feat = os.path.exists(feat_path)
        has_model = os.path.exists(xgb_path)
        has_mrd = os.path.exists(mrd_path)
        
        raw_icon = "RAW" if has_raw else "..."
        feat_icon = "FEAT" if has_feat else "..."
        model_icon = "XGB" if has_model else "..."
        mrd_icon = "MRD" if has_mrd else "..."
        
        if has_raw: raw_count += 1
        if has_feat: feat_count += 1
        if has_model: model_count += 1
        if has_mrd: mrd_count += 1
        
        candles = 0
        if has_feat:
            try:
                df = pd.read_parquet(feat_path, columns=["close"])
                candles = len(df)
            except:
                pass
        
        sym_short = s.replace("/USDT", "")
        print(f"  {sym_short:<10s} {label:<5s} {raw_icon:<9s} {feat_icon:<11s} {model_icon:<9s} {mrd_icon:<6s} {candles:>8,d}")

print(f"  {'-'*60}")
print(f"  Total de pares (M1/M5/M15):  {total_pairs}")
print(f"  Com dados RAW:               {raw_count}/{total_pairs}")
print(f"  Com Features processados:    {feat_count}/{total_pairs}")
print(f"  Com modelos treinados:       {model_count}/{total_pairs}")
print(f"  Com MRD:                     {mrd_count}/{total_pairs}")
print(f"  {'='*70}")

# Summary by asset
print()
print(f"  RESUMO POR ATIVO:")
print(f"  {'-'*60}")
for s in SYMBOLS:
    sym_short = s.replace("/USDT", "")
    stages = []
    for tf in INPUT_TFS:
        label = TF_LABEL.get(tf, tf)
        prefix = s.replace("/", "_")
        xgb_path = os.path.join(MODEL_DIR, f"{prefix}_{label}_call_1_xgb.json")
        stages.append("XGB" if os.path.exists(xgb_path) else "RAW" if os.path.exists(os.path.join(RAW_DIR, f"{prefix}_{label}.parquet")) else "...")
    
    counts = sum(1 for st in stages if st == "XGB")
    total_tfs = len(INPUT_TFS)
    status = f"{counts}/{total_tfs} modelos treinados"
    print(f"  {sym_short:<10s} {' | '.join(stages):<20s} {status}")
