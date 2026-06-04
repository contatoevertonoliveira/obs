#!/usr/bin/env python3
"""Teste de calibração do modelo XGBoost."""
import pandas as pd, numpy as np, joblib, sys, os
os.chdir("/root/hermes-quant-v2")
sys.path.insert(0, ".")
from config.settings import PROCESSED_DIR, MODEL_DIR

df = pd.read_parquet(f"{PROCESSED_DIR}/BTC_USDT_M1_features.parquet")
model = joblib.load(f"{MODEL_DIR}/BTC_USDT_M1_call_1_xgb.json")

# Features
feat_cols = [c for c in df.columns if c not in [
    "timestamp", "datetime", "symbol",
    "target_call", "target_put", "target_call_3", "target_put_3",
    "target_call_5", "target_put_5", "struct_market"
] and df[c].dtype in ["float64", "float32", "int64", "int32"]]

X = df[feat_cols].copy()
mask = X.isna().any(axis=1)
X = X[~mask]
y = df["target_call"][~mask]

# Últimos 20%
split = int(len(X) * 0.8)
X_test, y_test = X.iloc[split:], y.iloc[split:]
y_prob = model.predict_proba(X_test)[:, 1]

# Calibração por faixa
bins = [0.5, 0.55, 0.6, 0.65, 0.7, 0.75, 0.8, 0.85, 0.9, 0.95, 1.0]
print(f"{'Range':>12s} {'N':>10s} {'WR':>8s} {'Exp(80%)':>12s}")
print("-" * 48)
for i in range(len(bins) - 1):
    lo, hi = bins[i], bins[i + 1]
    mask2 = (y_prob >= lo) & (y_prob < hi)
    n = int(mask2.sum())
    if n < 10:
        continue
    wr = float(y_test[mask2].mean())
    exp = wr * 0.80 - (1 - wr)
    print(f"{lo:.2f}-{hi:.2f}    {n:>8,d}  {wr:.2%}  {exp:.2%}")

# Top 1%, 5%, 10%
print()
for pct, label in [(0.01, "Top 1%"), (0.05, "Top 5%"), (0.10, "Top 10%"), (0.20, "Top 20%")]:
    threshold = np.percentile(y_prob, 100 - pct * 100)
    mask_top = y_prob >= threshold
    n = int(mask_top.sum())
    wr = float(y_test[mask_top].mean())
    exp = wr * 0.80 - (1 - wr)
    print(f"{label:>10s} (>{threshold:.2f})  {n:>8,d}  {wr:.2%}  {exp:.2%}")
