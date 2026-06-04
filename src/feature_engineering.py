#!/usr/bin/env python3
"""
Hermes Quant V2 — Fase 2: Feature Engineering
Pipeline de indicadores técnicos para opções binárias M1/M5/M15.
"""
import os, sys, glob, warnings
warnings.filterwarnings("ignore")

import pandas as pd
import numpy as np

os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ".")
from config.settings import (
    SYMBOLS, ALL_TFS, INPUT_TFS, CONTEXT_TFS,
    TF_LABEL, TF_MS, RAW_DIR, PROCESSED_DIR,
)

os.makedirs(PROCESSED_DIR, exist_ok=True)


def load_data(symbol, tf):
    """Carrega um parquet do raw."""
    label = TF_LABEL.get(tf, tf)
    path = os.path.join(RAW_DIR, f"{symbol.replace('/', '_')}_{label}.parquet")
    if not os.path.exists(path):
        return None
    df = pd.read_parquet(path)
    df["datetime"] = pd.to_datetime(df["timestamp"], unit="ms")
    df = df.sort_values("timestamp").reset_index(drop=True)
    return df


# ═══════════════════════════════════════════════════════════
# INDICADORES
# ═══════════════════════════════════════════════════════════

def add_ema(df, periods=[9, 21, 50, 200]):
    """Médias Móveis Exponenciais."""
    for p in periods:
        df[f"ema_{p}"] = df["close"].ewm(span=p, adjust=False).mean()
        df[f"ema_{p}_slope"] = df[f"ema_{p}"].diff()  # inclinação
    return df


def add_rsi(df, period=14):
    """RSI — Relative Strength Index."""
    delta = df["close"].diff()
    gain = delta.clip(lower=0)
    loss = (-delta).clip(lower=0)
    avg_gain = gain.ewm(span=period, adjust=False).mean()
    avg_loss = loss.ewm(span=period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    df["rsi"] = 100 - (100 / (1 + rs))
    return df


def add_macd(df, fast=12, slow=26, signal=9):
    """MACD — Moving Average Convergence Divergence."""
    ema_fast = df["close"].ewm(span=fast, adjust=False).mean()
    ema_slow = df["close"].ewm(span=slow, adjust=False).mean()
    df["macd"] = ema_fast - ema_slow
    df["macd_signal"] = df["macd"].ewm(span=signal, adjust=False).mean()
    df["macd_hist"] = df["macd"] - df["macd_signal"]
    return df


def add_bollinger(df, period=20, std=2):
    """Bollinger Bands."""
    df["bb_mid"] = df["close"].rolling(period).mean()
    bb_std = df["close"].rolling(period).std()
    df["bb_upper"] = df["bb_mid"] + std * bb_std
    df["bb_lower"] = df["bb_mid"] - std * bb_std
    df["bb_width"] = df["bb_upper"] - df["bb_lower"]
    df["bb_position"] = (df["close"] - df["bb_lower"]) / (df["bb_upper"] - df["bb_lower"]).replace(0, np.nan)
    return df


def add_atr(df, period=14):
    """ATR — Average True Range."""
    high_low = df["high"] - df["low"]
    high_close = (df["high"] - df["close"].shift()).abs()
    low_close = (df["low"] - df["close"].shift()).abs()
    tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    df["atr"] = tr.rolling(period).mean()
    df["atr_pct"] = df["atr"] / df["close"] * 100  # ATR percentual
    return df


def add_adx(df, period=14):
    """ADX — Average Directional Index."""
    high, low, close = df["high"], df["low"], df["close"]
    plus_dm = high.diff()
    minus_dm = low.diff()
    plus_dm[plus_dm < 0] = 0
    minus_dm[minus_dm > 0] = 0
    tr = pd.concat([high - low, (high - close.shift()).abs(), (low - close.shift()).abs()], axis=1).max(axis=1)
    atr = tr.rolling(period).mean()
    plus_di = 100 * (plus_dm.ewm(span=period, adjust=False).mean() / atr.replace(0, np.nan))
    minus_di = 100 * (-minus_dm.ewm(span=period, adjust=False).mean() / atr.replace(0, np.nan))
    dx = abs(plus_di - minus_di) / (plus_di + minus_di).replace(0, np.nan) * 100
    df["adx"] = dx.rolling(period).mean()
    df["plus_di"] = plus_di
    df["minus_di"] = minus_di
    return df


def add_stochastic(df, k_period=14, d_period=3):
    """Stochastic Oscillator."""
    low_min = df["low"].rolling(k_period).min()
    high_max = df["high"].rolling(k_period).max()
    df["stoch_k"] = 100 * (df["close"] - low_min) / (high_max - low_min).replace(0, np.nan)
    df["stoch_d"] = df["stoch_k"].rolling(d_period).mean()
    return df


def add_cci(df, period=20):
    """CCI — Commodity Channel Index."""
    tp = (df["high"] + df["low"] + df["close"]) / 3
    sma = tp.rolling(period).mean()
    mad = tp.rolling(period).apply(lambda x: np.abs(x - x.mean()).mean())
    df["cci"] = (tp - sma) / (0.015 * mad.replace(0, np.nan))
    return df


def add_price_features(df):
    """Features de preço: retornos, volatilidade, gaps."""
    df["return_1"] = df["close"].pct_change(1)
    df["return_5"] = df["close"].pct_change(5)
    df["return_10"] = df["close"].pct_change(10)
    df["range"] = (df["high"] - df["low"]) / df["close"]
    df["body"] = abs(df["close"] - df["open"]) / df["close"]
    df["upper_shadow"] = (df["high"] - df[["open", "close"]].max(axis=1)) / df["close"]
    df["lower_shadow"] = (df[["open", "close"]].min(axis=1) - df["low"]) / df["close"]
    df["volatility"] = df["return_1"].rolling(20).std()
    df["gap"] = df["open"] - df["close"].shift(1)
    df["gap_pct"] = df["gap"] / df["close"].shift(1)
    return df


def add_volume_features(df):
    """Features de volume."""
    df["volume_sma"] = df["volume"].rolling(20).mean()
    df["volume_ratio"] = df["volume"] / df["volume_sma"].replace(0, np.nan)
    return df


def add_distance_features(df):
    """Distância do preço até as médias."""
    for p in [9, 21, 50, 200]:
        if f"ema_{p}" in df.columns:
            df[f"dist_ema_{p}"] = (df["close"] - df[f"ema_{p}"]) / df[f"ema_{p}"] * 100
    return df


# ═══════════════════════════════════════════════════════════
# TARGET — para opções binárias
# ═══════════════════════════════════════════════════════════

def add_targets(df, tf="1m"):
    """
    Cria targets para opções binárias com spread configurável.
    """
    from config.settings import TARGET_SPREAD_PCT, TARGET_SPREAD_MULT

    spread = TARGET_SPREAD_PCT.get(tf, 0.05) / 100.0  # Converter para decimal

    # Próximo candle (target principal para CALL/PUT 1-minuto)
    df["target_call"] = (df["close"].shift(-1) > df["close"] * (1 + spread)).astype(int)
    df["target_put"]  = (df["close"].shift(-1) < df["close"] * (1 - spread)).astype(int)

    # Balanceamento: garante que CALL e PUT não se sobreponham
    # Se ambos forem 1, vira 0 (neutro - movimento insuficiente)
    both = (df["target_call"] == 1) & (df["target_put"] == 1)
    df.loc[both, "target_call"] = 0
    df.loc[both, "target_put"] = 0
    # Se nenhum for 1, ambos 0 (neutro) — já é o padrão

    # Próximos 3 candles
    spread_3 = spread * TARGET_SPREAD_MULT
    df["target_call_3"] = (df["close"].shift(-3) > df["close"] * (1 + spread_3)).astype(int)
    df["target_put_3"]  = (df["close"].shift(-3) < df["close"] * (1 - spread_3)).astype(int)

    # Próximos 5 candles
    spread_5 = spread * TARGET_SPREAD_MULT * 1.5
    df["target_call_5"] = (df["close"].shift(-5) > df["close"] * (1 + spread_5)).astype(int)
    df["target_put_5"]  = (df["close"].shift(-5) < df["close"] * (1 - spread_5)).astype(int)

    return df


# ═══════════════════════════════════════════════════════════
# PIPELINE PRINCIPAL
# ═══════════════════════════════════════════════════════════

def process_symbol(symbol, tf):
    """Executa todo o pipeline de features para um par."""
    label = TF_LABEL.get(tf, tf)
    symbol_short = symbol.replace("/USDT", "")

    df = load_data(symbol, tf)
    if df is None or len(df) < 500:
        return None

    print(f"  ⚙️  {symbol_short:6s} {label:4s} | {len(df):>8,d} candles brutos", end="")

    # Aplicar indicadores
    df = add_ema(df)
    df = add_rsi(df)
    df = add_macd(df)
    df = add_bollinger(df)
    df = add_atr(df)
    df = add_adx(df)
    df = add_stochastic(df)
    df = add_cci(df)
    df = add_price_features(df)
    df = add_volume_features(df)
    df = add_distance_features(df)
    df = add_targets(df, tf)

    # Remover linhas com NaN do início (indicadores precisam de aquecimento)
    min_required = max(200, 50 * (1 if tf == "1m" else 20 if tf == "5m" else 10))
    df = df.iloc[min_required:].reset_index(drop=True)

    # Salvar
    out_path = os.path.join(PROCESSED_DIR, f"{symbol.replace('/', '_')}_{label}_features.parquet")
    df.to_parquet(out_path, index=False, compression="zstd")

    n_cols = len(df.columns)
    print(f" → {len(df):>8,d} candles | {n_cols} features ✅")
    return df


def main():
    print("=" * 62)
    print("  ⚙️  HERMES QUANT V2 — FEATURE ENGINEERING")
    print("=" * 62)
    print(f"  Indicadores: EMA, RSI, MACD, BB, ATR, ADX, Stoch, CCI")
    print(f"  Targets: CALL/PUT 1, 3, 5 candles")
    print("=" * 62)

    # Processa apenas timeframes de entrada primeiro
    for symbol in SYMBOLS:
        for tf in INPUT_TFS + CONTEXT_TFS:
            process_symbol(symbol, tf)

    print(f"\n{'=' * 62}")
    print(f"  ✅ FEATURE ENGINEERING CONCLUÍDO!")
    print(f"  📁 Dados em: {os.path.abspath(PROCESSED_DIR)}")
    print(f"{'=' * 62}")


if __name__ == "__main__":
    main()
