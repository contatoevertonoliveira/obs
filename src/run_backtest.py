#!/usr/bin/env python3
"""Backtest completo: BTC + ETH, todos TFs, com downsample."""
import os, sys, warnings
warnings.filterwarnings("ignore")
os.chdir("/root/hermes-quant-v2")
sys.path.insert(0, ".")

import pandas as pd
import numpy as np
import json, joblib

from src.market_regime import classify_regime, load_regime_performance_cache
from config.settings import TF_LABEL, PROCESSED_DIR, MODEL_DIR, PAYOUT_RATE

SYMBOLS = ["BTC/USDT", "ETH/USDT"]
TFS = ["1m", "5m", "15m"]

# Model -> target column mapping
MODEL_TARGET_MAP = {
    "call_1": "target_call", "put_1": "target_put",
    "call_5": "target_call_5", "put_5": "target_put_5",
}

def load_data(symbol, tf, max_rows=None):
    label = TF_LABEL.get(tf, tf)
    path = f"{PROCESSED_DIR}/{symbol.replace('/', '_')}_{label}_features.parquet"
    if not os.path.exists(path):
        return None
    df = pd.read_parquet(path)
    if max_rows and len(df) > max_rows:
        df = df.tail(max_rows)
    return df

def load_models(symbol, tf):
    label = TF_LABEL.get(tf, tf)
    models = {}
    for target in ["call_1", "put_1", "call_5", "put_5"]:
        path = f"{MODEL_DIR}/{symbol.replace('/', '_')}_{label}_{target}_xgb.json"
        if os.path.exists(path):
            models[target] = joblib.load(path)
    return models

def backtest(symbol, tf):
    limits = {"1m": 200_000, "5m": 200_000, "15m": None}
    df = load_data(symbol, tf, limits.get(tf))
    models = load_models(symbol, tf)
    
    if df is None or not models:
        print(f"  ⚠ {symbol} {tf}: sem dados/modelos")
        return
    
    feature_cols = [c for c in df.columns
                    if c not in ["timestamp", "datetime", "symbol",
                                  "target_call", "target_put",
                                  "target_call_3", "target_put_3",
                                  "target_call_5", "target_put_5",
                                  "struct_market"]
                    and df[c].dtype in ["float64", "float32", "int64", "int32"]]
    
    X = df[feature_cols].copy()
    mask = X.isna().any(axis=1)
    X = X[~mask]
    df_clean = df[~mask].copy()
    
    if len(X) < 5000:
        print(f"  ⚠ {symbol} {tf}: dados insuficientes ({len(X)})")
        return
    
    split = int(len(X) * 0.8)
    X_test = X.iloc[split:]
    df_test = df_clean.iloc[split:].copy()
    
    print(f"📊 {symbol:10s} {tf:4s} | {len(df_test):,} candles teste | ", end="", flush=True)
    
    # Batch predict all models
    preds = {}
    for key, model in models.items():
        preds[key] = model.predict_proba(X_test)[:, 1]
    
    # Generate trades
    trades = []
    tf_thresholds = {"1m": 0.88, "5m": 0.85, "15m": 0.82}
    min_conf = tf_thresholds.get(tf, 0.85)
    
    for i in range(len(X_test)):
        best_conf, best_trade = 0, None
        for model_key in models:
            target_dir = "call" if "call" in model_key else "put"
            conf = float(preds[model_key][i])
            if conf < min_conf:
                continue
            if conf <= best_conf:
                continue
            
            target_col = MODEL_TARGET_MAP[model_key]
            actual = int(df_test[target_col].iloc[i]) if target_col in df_test.columns else 0
            
            # MRD (every 10 candles)
            regime_name = "nosignal"
            if i % 10 == 0 and len(df_clean) > 50:
                window = df_clean.iloc[:split + i]
                regime = classify_regime(window)
                regime_name = regime["regime"]
            elif trades:
                regime_name = trades[-1]["regime"]
            
            best_conf = conf
            best_trade = {
                "timestamp": int(df_test["timestamp"].iloc[i]),
                "type": target_dir.upper(),
                "confidence": conf,
                "regime": regime_name,
                "actual": actual,
                "won": actual == 1,
            }
        
        if best_trade:
            trades.append(best_trade)
    
    if not trades:
        print("0 trades ❌")
        return
    
    df_t = pd.DataFrame(trades)
    total = len(df_t)
    wins = df_t["won"].sum()
    wr = wins / total
    exp = (wr * PAYOUT_RATE) - ((1 - wr) * 1)
    
    print(f"{total} trades | WR {wr:.1%} | Exp {exp:.2%} | ", end="")
    print("✅" if exp > 0 else "⚠️ ")
    
    # Per regime breakdown
    for regime, group in df_t.groupby("regime"):
        n = len(group)
        if n < 5:
            continue
        w = group["won"].sum()
        wr_g = w / n
        exp_g = (wr_g * PAYOUT_RATE) - ((1 - wr_g) * 1)
        print(f"    {regime:25s}: {n:>5d} trades | WR {wr_g:.1%} | Exp {exp_g:+.2%}")
    
    return df_t

print("=" * 55)
print("  🧪 BACKTEST COMPLETO — HERMES QUANT V2")
print("=" * 55)
print(f"  Payout: {PAYOUT_RATE:.0%} | Thresholds: M1>0.88 M5>0.85 M15>0.82")
print("=" * 55)

results = []
for symbol in SYMBOLS:
    for tf in TFS:
        r = backtest(symbol, tf)
        if r is not None:
            wr = r["won"].mean()
            exp = (wr * PAYOUT_RATE) - ((1 - wr) * 1)
            results.append({
                "symbol": symbol, "tf": tf,
                "trades": len(r), "win_rate": round(wr, 4),
                "expectancy": round(exp, 4)
            })

print(f"\n{'=' * 55}")
print(f"  📊 RESUMO CONSOLIDADO")
print(f"{'=' * 55}")
for r in results:
    print(f"  {r['symbol']:10s} {r['tf']:4s} | {r['trades']:>6d} trades | "
          f"WR {r['win_rate']:.1%} | Exp {r['expectancy']:+.2%} "
          f"{'✅' if r['expectancy'] > 0 else '❌'}")

# Save results
with open(f"{MODEL_DIR}/backtest_results.json", "w") as f:
    json.dump(results, f, indent=2)
print(f"\n  📁 Resultados salvos em models/backtest_results.json")
