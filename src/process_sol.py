#!/usr/bin/env python3
"""Processa SOL: features + padrões + estrutura."""
import sys, os, warnings
warnings.filterwarnings("ignore")
os.chdir("/root/hermes-quant-v2")
sys.path.insert(0, ".")

from src.feature_engineering import process_symbol
from src.pattern_recognition import add_all_patterns
from src.market_structure import (
    detect_trend_ema, detect_trend_adx, detect_breakout,
    detect_pullback, detect_volatility_regime, classify_market_structure
)
import pandas as pd
from config.settings import PROCESSED_DIR

TF_MAP = {"1m": "M1", "5m": "M5", "15m": "M15"}
TFS = ["1m", "5m", "15m"]

for tf in TFS:
    label = TF_MAP[tf]
    print(f"\n{'='*50}")
    print(f"Processando SOL {label}...")
    print(f"{'='*50}")

    df = process_symbol("SOL/USDT", tf)
    if df is None or len(df) < 1000:
        print(f"  Dados insuficientes para SOL {label}")
        continue

    print(f"  Features: {len(df):,} candles, {len(df.columns)} cols")

    feat_path = os.path.join(PROCESSED_DIR, f"SOL_USDT_{label}_features.parquet")
    df = pd.read_parquet(feat_path)

    df = add_all_patterns(df)
    df = detect_trend_ema(df)
    df = detect_trend_adx(df)
    df = detect_breakout(df)
    df = detect_pullback(df)
    df = detect_volatility_regime(df)
    df = classify_market_structure(df)

    df.to_parquet(feat_path, index=False, compression="zstd")
    print(f"  Padroes + Estrutura: {len(df.columns)} cols")
    print(f"  Salvo: {feat_path}")

print(f"\n{'='*50}")
print("SOL processado com sucesso!")
print(f"{'='*50}")
