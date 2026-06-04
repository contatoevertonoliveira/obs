#!/usr/bin/env python3
"""Debug: verifica alinhamento entre predição e target real."""
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

split = int(len(X) * 0.8)
X_test, y_test = X.iloc[split:], y.iloc[split:]
y_prob = model.predict_proba(X_test)[:, 1]

print(f"Total teste: {len(y_test):,} candles")
print(f"target_call rate no teste: {y_test.mean():.2%}")
print()

# Mostrar top 20 por probabilidade
top_idx = np.argsort(y_prob)[-20:][::-1]
print(f"{'#':>4s} {'y_prob':>8s} {'target_call':>12s}")
print("-" * 30)
for i, idx in enumerate(top_idx):
    print(f"{i+1:>4d} {y_prob[idx]:.4f} {y_test.iloc[idx]:>12d}")

# Contagem: quantos acima de 0.88?
high_conf = y_prob > 0.88
print(f"\nAcima de 0.88: {high_conf.sum():,} candles")
if high_conf.sum() > 0:
    wr = y_test[high_conf].mean()
    print(f"Win Rate: {wr:.2%}")
    print(f"Target rate na faixa: {y_test[high_conf].mean():.2%}")

# Ver distribuição completa
print(f"\nDistribuição de y_prob:")
for thresh in [0.5, 0.6, 0.7, 0.8, 0.85, 0.9, 0.95]:
    n = (y_prob >= thresh).sum()
    print(f"  >={thresh:.2f}: {n:>6,d} ({n/len(y_prob)*100:.2f}%)")
