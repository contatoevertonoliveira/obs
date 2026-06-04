#!/usr/bin/env python3
"""
Hermes Quant V2 — Fase 4: Estrutura de Mercado
Identifica:
  - Bull Trend
  - Bear Trend
  - Range (laterally)
  - Breakout
  - Pullback
  - Reversal

Usa análise multi-timeframe: decisão em M1 validada por M5 e M15.
"""
import os, sys, warnings
warnings.filterwarnings("ignore")

import pandas as pd
import numpy as np

os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ".")
from config.settings import (
    SYMBOLS, INPUT_TFS, CONTEXT_TFS, TF_LABEL,
    PROCESSED_DIR, RAW_DIR, TF_MS,
)


def load_features(symbol, tf):
    """Carrega dados processados."""
    label = TF_LABEL.get(tf, tf)
    feat_path = os.path.join(PROCESSED_DIR, f"{symbol.replace('/', '_')}_{label}_features.parquet")
    raw_path = os.path.join(RAW_DIR, f"{symbol.replace('/', '_')}_{label}.parquet")

    if os.path.exists(feat_path):
        return pd.read_parquet(feat_path)
    elif os.path.exists(raw_path):
        return pd.read_parquet(raw_path)
    return None


# ═══════════════════════════════════════════════════════════
# INDICADORES DE ESTRUTURA
# ═══════════════════════════════════════════════════════════

def detect_trend_ema(df):
    """
    Tendência baseada em alinhamento de EMAs.
    Bull: EMA9 > EMA21 > EMA50
    Bear: EMA9 < EMA21 < EMA50
    Força: quão distantes estão as médias.
    """
    has_emas = all(f"ema_{p}" in df.columns for p in [9, 21, 50])

    if not has_emas:
        # Calcular EMAs
        for p in [9, 21, 50]:
            df[f"ema_{p}"] = df["close"].ewm(span=p, adjust=False).mean()

    df["struct_trend_bull"] = (
        (df["ema_9"] > df["ema_21"]) & (df["ema_21"] > df["ema_50"])
    ).astype(int)

    df["struct_trend_bear"] = (
        (df["ema_9"] < df["ema_21"]) & (df["ema_21"] < df["ema_50"])
    ).astype(int)

    # Força da tendência (distância normalizada entre EMA9 e EMA50)
    df["struct_trend_strength"] = (
        (df["ema_9"] - df["ema_50"]) / df["ema_50"]
    )

    # Tendência neutra / range
    df["struct_trend_range"] = (~df["struct_trend_bull"].astype(bool) & ~df["struct_trend_bear"].astype(bool)).astype(int)

    return df


def detect_trend_adx(df, period=14):
    """
    Confirma tendência via ADX.
    ADX > 25 = tendência forte
    ADX < 20 = range
    """
    if "adx" not in df.columns:
        # Calcular ADX inline
        high, low, close = df["high"], df["low"], df["close"]
        plus_dm = high.diff().clip(lower=0)
        minus_dm = -low.diff().clip(lower=0)
        tr = pd.concat([
            high - low,
            (high - close.shift()).abs(),
            (low - close.shift()).abs()
        ], axis=1).max(axis=1)
        atr = tr.rolling(period).mean()
        plus_di = 100 * (plus_dm.ewm(span=period, adjust=False).mean() / atr.replace(0, np.nan))
        minus_di = 100 * (minus_dm.ewm(span=period, adjust=False).mean() / atr.replace(0, np.nan))
        dx = abs(plus_di - minus_di) / (plus_di + minus_di).replace(0, np.nan) * 100
        df["adx"] = dx.rolling(period).mean()
        df["plus_di"] = plus_di
        df["minus_di"] = minus_di

    df["struct_adx_strong"] = (df["adx"] > 25).astype(int)
    df["struct_adx_weak"] = (df["adx"] < 20).astype(int)

    # Direção baseada em +DI vs -DI
    df["struct_di_bull"] = (df["plus_di"] > df["minus_di"]).astype(int)
    df["struct_di_bear"] = (df["minus_di"] > df["plus_di"]).astype(int)

    return df


def detect_breakout(df, lookback=20, std_mult=2.0):
    """
    Breakout: preço rompe canal de volatilidade.
    - High > BB Upper ou Low < BB Lower nas últimas barras
    - Volume acima da média
    """
    if "bb_upper" not in df.columns:
        # Calcular BB
        df["bb_mid"] = df["close"].rolling(lookback).mean()
        bb_std = df["close"].rolling(lookback).std()
        df["bb_upper"] = df["bb_mid"] + std_mult * bb_std
        df["bb_lower"] = df["bb_mid"] - std_mult * bb_std

    # Rompimento para cima
    df["struct_breakout_up"] = (
        (df["high"] >= df["bb_upper"]) &
        (df["close"] > df["bb_mid"])
    ).astype(int)

    # Rompimento para baixo
    df["struct_breakout_down"] = (
        (df["low"] <= df["bb_lower"]) &
        (df["close"] < df["bb_mid"])
    ).astype(int)

    # Volume confirmando breakout
    if "volume_sma" in df.columns:
        df["struct_breakout_up_vol"] = (
            df["struct_breakout_up"] & (df["volume"] > df["volume_sma"] * 1.5)
        ).astype(int)
        df["struct_breakout_down_vol"] = (
            df["struct_breakout_down"] & (df["volume"] > df["volume_sma"] * 1.5)
        ).astype(int)

    return df


def detect_pullback(df, lookback=5):
    """
    Pullback: após movimento direcional, correção contra a tendência.
    - Em bull trend: preço cai por lookback candles consecutivos
    - Em bear trend: preço sobe por lookback candles consecutivos
    """
    # Pullback em bull trend: após alta, X candles de baixa consecutiva
    down_streak = 0
    pullback_bull = np.zeros(len(df))

    for i in range(1, len(df)):
        if df["close"].iloc[i] < df["close"].iloc[i - 1]:
            down_streak += 1
        else:
            down_streak = 0

        if down_streak >= lookback and df["struct_trend_bull"].iloc[i] == 1:
            pullback_bull[i] = 1

    df["struct_pullback_bull"] = pullback_bull.astype(int)

    # Pullback em bear trend: após queda, X candles de alta consecutiva
    up_streak = 0
    pullback_bear = np.zeros(len(df))

    for i in range(1, len(df)):
        if df["close"].iloc[i] > df["close"].iloc[i - 1]:
            up_streak += 1
        else:
            up_streak = 0

        if up_streak >= lookback and df["struct_trend_bear"].iloc[i] == 1:
            pullback_bear[i] = 1

    df["struct_pullback_bear"] = pullback_bear.astype(int)

    return df


def detect_volatility_regime(df, period=20):
    """
    Regime de volatilidade: expansão vs compressão.
    """
    if "atr_pct" not in df.columns:
        hi_lo = df["high"] - df["low"]
        hi_cl = (df["high"] - df["close"].shift()).abs()
        lo_cl = (df["low"] - df["close"].shift()).abs()
        tr = pd.concat([hi_lo, hi_cl, lo_cl], axis=1).max(axis=1)
        df["atr"] = tr.rolling(14).mean()
        df["atr_pct"] = df["atr"] / df["close"] * 100

    df["struct_atr_sma"] = df["atr_pct"].rolling(period).mean()
    df["struct_vol_expansion"] = (df["atr_pct"] > df["struct_atr_sma"] * 1.2).astype(int)
    df["struct_vol_compression"] = (df["atr_pct"] < df["struct_atr_sma"] * 0.8).astype(int)

    return df


# ═══════════════════════════════════════════════════════════
# CLASSIFICADOR FINAL DE ESTRUTURA
# ═══════════════════════════════════════════════════════════

def classify_market_structure(df):
    """
    Classificação final combinando todos os sinais.
    """
    # Tendência consolidada
    bull_score = (
        df["struct_trend_bull"] * 2 +
        df["struct_di_bull"] * 1.5 +
        df["struct_adx_strong"] * 1
    )

    bear_score = (
        df["struct_trend_bear"] * 2 +
        df["struct_di_bear"] * 1.5 +
        df["struct_adx_strong"] * 1
    )

    conditions = [
        (bull_score >= bear_score) & (bull_score >= 2),
        (bear_score > bull_score) & (bear_score >= 2),
        (bull_score < 2) & (bear_score < 2),
    ]
    choices = ["bull", "bear", "range"]

    df["struct_market"] = np.select(conditions, choices, default="range")
    df["struct_market_score"] = np.maximum(bull_score, bear_score)

    # Sinais compostos
    df["struct_bias_bull"] = (df["struct_market"] == "bull").astype(int)
    df["struct_bias_bear"] = (df["struct_market"] == "bear").astype(int)
    df["struct_bias_range"] = (df["struct_market"] == "range").astype(int)

    return df


# ═══════════════════════════════════════════════════════════
# RESAMPLE MULTI-TIMEFRAME
# ═══════════════════════════════════════════════════════════

def add_context_from_higher_tf(df_lower, df_higher, tf_higher="5m"):
    """
    Adiciona colunas de contexto do timeframe superior ao inferior.
    Ex: usar M5 para validar M1.
    """
    if df_higher is None or len(df_higher) < 100:
        return df_lower

    higher = df_higher[["timestamp", "struct_market", "struct_market_score",
                         "struct_breakout_up", "struct_breakout_down",
                         "struct_pullback_bull", "struct_pullback_bear",
                         "struct_trend_bull", "struct_trend_bear",
                         "struct_vol_expansion", "struct_vol_compression"]].copy()

    higher.columns = [c if c == "timestamp" else f"{c}_{tf_higher}" for c in higher.columns]

    # Merge asof: puxa o contexto mais recente do TF superior
    df_lower = pd.merge_asof(
        df_lower.sort_values("timestamp"),
        higher.sort_values("timestamp"),
        on="timestamp",
        direction="backward"
    )

    return df_lower


# ═══════════════════════════════════════════════════════════
# PIPELINE
# ═══════════════════════════════════════════════════════════

def process_symbol(symbol):
    """Processa estrutura para um símbolo em todos os TFs."""
    symbol_short = symbol.replace("/USDT", "")

    # Carregar todos os TFs
    dfs = {}
    for tf in INPUT_TFS + CONTEXT_TFS:
        label = TF_LABEL.get(tf, tf)
        df = load_features(symbol, tf)
        if df is not None and len(df) > 200:
            dfs[label] = df

    if not dfs:
        print(f"  ⚠ {symbol_short:6s} → sem dados")
        return

    print(f"  🏗️  {symbol_short:6s} | {list(dfs.keys())}")

    # Adicionar estrutura em cada TF
    for label, df in dfs.items():
        df = detect_trend_ema(df)
        df = detect_trend_adx(df)
        df = detect_breakout(df)
        df = detect_pullback(df)
        df = detect_volatility_regime(df)
        df = classify_market_structure(df)
        dfs[label] = df

        # Salvar
        label_lower = label.replace("M", "m").replace("H", "h")
        out_path = os.path.join(PROCESSED_DIR, f"{symbol.replace('/', '_')}_{label}_features.parquet")
        df.to_parquet(out_path, index=False, compression="zstd")

    # Adicionar contexto de timeframes superiores nos inferiores
    tf_map = {"H1": "h1", "H4": "h4"}

    # M5 carrega contexto H1
    if "M5" in dfs and "H1" in dfs:
        dfs["M5"] = add_context_from_higher_tf(dfs["M5"], dfs["H1"], "h1")
        out = os.path.join(PROCESSED_DIR, f"{symbol.replace('/', '_')}_M5_features.parquet")
        dfs["M5"].to_parquet(out, index=False, compression="zstd")

    # M1 carrega contexto M5
    if "M1" in dfs and "M5" in dfs:
        dfs["M1"] = add_context_from_higher_tf(dfs["M1"], dfs["M5"], "m5")
        out = os.path.join(PROCESSED_DIR, f"{symbol.replace('/', '_')}_M1_features.parquet")
        dfs["M1"].to_parquet(out, index=False, compression="zstd")

    print(f"  ✅ {symbol_short:6s} → estrutura concluída")
    return dfs


def main():
    print("=" * 62)
    print("  🏗️  HERMES QUANT V2 — ESTRUTURA DE MERCADO")
    print("=" * 62)
    print(f"  Bull/Bear/Range | Breakout | Pullback | Volatilidade")
    print(f"  Contexto cross-TF: M1 ← M5 ← H1 ← H4")
    print("=" * 62)

    for symbol in SYMBOLS:
        print(f"\n{'─' * 40}")
        process_symbol(symbol)

    print(f"\n{'=' * 62}")
    print(f"  ✅ ESTRUTURA DE MERCADO CONCLUÍDA!")
    print(f"{'=' * 62}")


if __name__ == "__main__":
    main()
