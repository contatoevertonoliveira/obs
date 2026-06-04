#!/usr/bin/env python3
"""
Hermes Quant V2 — Fase 3: Reconhecimento de Padrões Candlestick
Detecta automaticamente padrões e converte em features numéricas.

Padrões suportados:
  - MHI1, MHI2, MHI3 (Máxima Histórica Interna)
  - Torres Gêmeas (Twin Towers)
  - Três Mosqueteiros (Three Soldiers / Three Crows)
  - Doji
  - Martelo / Hammer
  - Engolfo (Bullish / Bearish Engulfing)
  - Pin Bar
  - Inside Bar
  - Outside Bar
"""
import os, sys, warnings
warnings.filterwarnings("ignore")

import pandas as pd
import numpy as np

os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ".")
from config.settings import (SYMBOLS, INPUT_TFS, CONTEXT_TFS, TF_LABEL, PROCESSED_DIR, RAW_DIR)


def load_features(symbol, tf):
    """Carrega dados processados (com features) ou raw."""
    label = TF_LABEL.get(tf, tf)
    feat_path = os.path.join(PROCESSED_DIR, f"{symbol.replace('/', '_')}_{label}_features.parquet")
    raw_path = os.path.join(RAW_DIR, f"{symbol.replace('/', '_')}_{label}.parquet")

    if os.path.exists(feat_path):
        return pd.read_parquet(feat_path)
    elif os.path.exists(raw_path):
        return pd.read_parquet(raw_path)
    return None


# ═══════════════════════════════════════════════════════════
# DETECTORES DE PADRÃO
# ═══════════════════════════════════════════════════════════

# ── Doji ──────────────────────────────────────────────────
def detect_doji(df, threshold=0.005):
    """
    Doji: corpo muito pequeno comparado ao range total.
    threshold = proporção máxima do corpo em relação ao range.
    """
    body = abs(df["close"] - df["open"])
    total_range = df["high"] - df["low"]
    doji = (body / total_range.replace(0, np.nan)) < threshold
    return doji.astype(int)


# ── Martelo / Hammer ──────────────────────────────────────
def detect_hammer(df, body_ratio=0.3, shadow_ratio=2.0):
    """
    Martelo: corpo pequeno no topo, sombra inferior longa.
    - Corpo < 30% do range total
    - Sombra inferior >= 2x o corpo
    - Sombra superior pequena
    """
    body = abs(df["close"] - df["open"])
    total_range = df["high"] - df["low"]
    lower_shadow = df[["open", "close"]].min(axis=1) - df["low"]
    upper_shadow = df["high"] - df[["open", "close"]].max(axis=1)

    is_small_body = (body / total_range.replace(0, np.nan)) < body_ratio
    is_long_lower = lower_shadow >= shadow_ratio * body
    is_small_upper = upper_shadow < body

    return (is_small_body & is_long_lower & is_small_upper).astype(int)


# ── Shooting Star / Estrela Cadente ───────────────────────
def detect_shooting_star(df, body_ratio=0.3, shadow_ratio=2.0):
    """
    Estrela Cadente: corpo pequeno na base, sombra superior longa.
    """
    body = abs(df["close"] - df["open"])
    total_range = df["high"] - df["low"]
    lower_shadow = df[["open", "close"]].min(axis=1) - df["low"]
    upper_shadow = df["high"] - df[["open", "close"]].max(axis=1)

    is_small_body = (body / total_range.replace(0, np.nan)) < body_ratio
    is_long_upper = upper_shadow >= shadow_ratio * body
    is_small_lower = lower_shadow < body

    return (is_small_body & is_long_upper & is_small_lower).astype(int)


# ── Engolfo ───────────────────────────────────────────────
def detect_engulfing(df):
    """
    Engolfo:
      Bullish: candle atual verde, corpo engole o candle anterior (bear)
      Bearish: candle atual vermelho, corpo engole o candle anterior (bull)
    """
    body_prev = abs(df["close"].shift(1) - df["open"].shift(1))
    body_curr = abs(df["close"] - df["open"])

    # Bullish: atual verde, anterior vermelho, corpo atual > corpo anterior
    bullish = (
        (df["close"] > df["open"]) &
        (df["close"].shift(1) < df["open"].shift(1)) &
        (body_curr > body_prev * 1.1)
    ).astype(int)

    # Bearish: atual vermelho, anterior verde, corpo atual > corpo anterior
    bearish = (
        (df["close"] < df["open"]) &
        (df["close"].shift(1) > df["open"].shift(1)) &
        (body_curr > body_prev * 1.1)
    ).astype(int)

    df["pat_engulfing_bull"] = bullish
    df["pat_engulfing_bear"] = bearish
    return df


# ── Pin Bar ───────────────────────────────────────────────
def detect_pin_bar(df, body_ratio=0.2, wick_ratio=2.0):
    """
    Pin Bar: corpo muito pequeno, sombra (inferior ou superior) muito longa.
    """
    body = abs(df["close"] - df["open"])
    total_range = df["high"] - df["low"]
    lower_shadow = df[["open", "close"]].min(axis=1) - df["low"]
    upper_shadow = df["high"] - df[["open", "close"]].max(axis=1)

    is_small_body = (body / total_range.replace(0, np.nan)) < body_ratio

    # Pin bullish: sombra inferior >= 2x range total (exceto corpo)
    pin_bull = (is_small_body & (lower_shadow >= wick_ratio * (total_range - body))).astype(int)
    # Pin bearish: sombra superior >= 2x range total (exceto corpo)
    pin_bear = (is_small_body & (upper_shadow >= wick_ratio * (total_range - body))).astype(int)

    df["pat_pin_bull"] = pin_bull
    df["pat_pin_bear"] = pin_bear
    return df


# ── Inside Bar ────────────────────────────────────────────
def detect_inside_bar(df):
    """
    Inside Bar: candle totalmente dentro do range do candle anterior.
    """
    inside = (
        (df["high"] <= df["high"].shift(1)) &
        (df["low"] >= df["low"].shift(1))
    ).astype(int)
    return inside


# ── Outside Bar ───────────────────────────────────────────
def detect_outside_bar(df):
    """
    Outside Bar: candle engole COMPLETAMENTE o range do anterior.
    """
    outside = (
        (df["high"] > df["high"].shift(1)) &
        (df["low"] < df["low"].shift(1))
    ).astype(int)
    return outside


# ── MHI (Máxima Histórica Interna) ────────────────────────
def detect_mhi(df, lookback=20):
    """
    MHI1, MHI2, MHI3:
      MHI1: máxima de lookback candles
      MHI2: segunda maior
      MHI3: terceira maior
    Similar para mínimas (LHI).
    """
    window = df["high"].rolling(lookback, min_periods=lookback)
    lh_window = df["low"].rolling(lookback, min_periods=lookback)

    # Máximas
    df["pat_mhi1"] = (df["high"] >= window.max()).astype(int)
    # Para MHI2/MHI3 precisamos de lógica mais sofisticada - simplificamos
    rank = df["high"].rolling(lookback, min_periods=lookback).apply(
        lambda x: np.sum(x > x.iloc[-1]) + 1 if len(x) == lookback else 99
    )
    df["pat_mhi_rank"] = rank  # 1 = maior, 2 = segunda maior...
    df["pat_mhi2"] = (rank == 2).astype(int)
    df["pat_mhi3"] = (rank == 3).astype(int)

    # Mínimas (LHI)
    df["pat_lhi1"] = (df["low"] <= lh_window.min()).astype(int)
    rank_l = df["low"].rolling(lookback, min_periods=lookback).apply(
        lambda x: np.sum(x < x.iloc[-1]) + 1 if len(x) == lookback else 99
    )
    df["pat_lhi2"] = (rank_l == 2).astype(int)
    df["pat_lhi3"] = (rank_l == 3).astype(int)

    return df


# ── Três Soldados / Três Corvos ──────────────────────────
def detect_three_soldiers(df):
    """
    Três Soldados: 3 candles verdes consecutivos com corpos crescentes.
    Três Corvos: 3 candles vermelhos consecutivos com corpos crescentes.
    """
    body = abs(df["close"] - df["open"])
    body_prev1 = body.shift(1)
    body_prev2 = body.shift(2)

    # Três Soldados (bullish)
    soldiers = (
        (df["close"] > df["open"]) &
        (df["close"].shift(1) > df["open"].shift(1)) &
        (df["close"].shift(2) > df["open"].shift(2)) &
        (body > body_prev1) & (body_prev1 > body_prev2)
    ).astype(int)

    # Três Corvos (bearish)
    crows = (
        (df["close"] < df["open"]) &
        (df["close"].shift(1) < df["open"].shift(1)) &
        (df["close"].shift(2) < df["open"].shift(2)) &
        (body > body_prev1) & (body_prev1 > body_prev2)
    ).astype(int)

    df["pat_3_soldiers"] = soldiers
    df["pat_3_crows"] = crows
    return df


# ── Torres Gêmeas ─────────────────────────────────────────
def detect_twin_towers(df, lookback=10, tolerance=0.005):
    """
    Torres Gêmeas: dois topos (ou fundos) no mesmo nível com intervalo entre eles.
    """
    def _is_peak(x):
        arr = np.asarray(x)
        return 1 if len(arr) == 5 and arr[2] == max(arr) else 0

    def _is_valley(x):
        arr = np.asarray(x)
        return 1 if len(arr) == 5 and arr[2] == min(arr) else 0

    top = df["high"].rolling(5, center=True, min_periods=3).apply(_is_peak, raw=True)

    # Simplificado: marca candles que são picos locais
    twin_top = (
        (top == 1) &
        (top.shift(lookback) == 1) &
        (abs(df["high"] / df["high"].shift(lookback) - 1) < tolerance)
    ).astype(int)

    bottom = df["low"].rolling(5, center=True, min_periods=3).apply(_is_valley, raw=True)

    twin_bottom = (
        (bottom == 1) &
        (bottom.shift(lookback) == 1) &
        (abs(df["low"] / df["low"].shift(lookback) - 1) < tolerance)
    ).astype(int)

    df["pat_twin_towers_top"] = twin_top
    df["pat_twin_towers_bottom"] = twin_bottom
    return df


# ═══════════════════════════════════════════════════════════
# PIPELINE PRINCIPAL
# ═══════════════════════════════════════════════════════════

def add_all_patterns(df):
    """Aplica todos os detectores de padrão no DataFrame."""
    # Padrões básicos
    df["pat_doji"] = detect_doji(df)
    df["pat_hammer"] = detect_hammer(df)
    df["pat_shooting_star"] = detect_shooting_star(df)
    df = detect_engulfing(df)
    df = detect_pin_bar(df)
    df["pat_inside_bar"] = detect_inside_bar(df)
    df["pat_outside_bar"] = detect_outside_bar(df)

    # Padrões com lookback
    df = detect_mhi(df)
    df = detect_three_soldiers(df)
    df = detect_twin_towers(df)

    # Feature composta: quantidade de padrões bullish e bearish
    bullish_cols = [
        "pat_hammer", "pat_engulfing_bull", "pat_pin_bull",
        "pat_3_soldiers", "pat_twin_towers_bottom"
    ]
    bearish_cols = [
        "pat_shooting_star", "pat_engulfing_bear", "pat_pin_bear",
        "pat_3_crows", "pat_twin_towers_top"
    ]

    existing_bull = [c for c in bullish_cols if c in df.columns]
    existing_bear = [c for c in bearish_cols if c in df.columns]

    df["pat_bullish_count"] = df[existing_bull].sum(axis=1)
    df["pat_bearish_count"] = df[existing_bear].sum(axis=1)
    df["pat_signal"] = df["pat_bullish_count"] - df["pat_bearish_count"]

    return df


def process_symbol(symbol, tf):
    """Processa padrões para um par + timeframe."""
    label = TF_LABEL.get(tf, tf)
    symbol_short = symbol.replace("/USDT", "")

    df = load_features(symbol, tf)
    if df is None or len(df) < 200:
        print(f"  ⚠ {symbol_short:6s} {label:4s} → sem dados")
        return

    print(f"  🔍 {symbol_short:6s} {label:4s} | {len(df):>8,d} candles", end="")

    # Adicionar padrões
    df = add_all_patterns(df)

    # Feature cols que começam com pat_
    pat_cols = [c for c in df.columns if c.startswith("pat_")]
    print(f" | {len(pat_cols)} padrões detectados")

    # Salvar de volta (com padrões incluídos)
    out_path = os.path.join(PROCESSED_DIR, f"{symbol.replace('/', '_')}_{label}_features.parquet")
    df.to_parquet(out_path, index=False, compression="zstd")

    return df


def main():
    print("=" * 62)
    print("  🔍 HERMES QUANT V2 — RECONHECIMENTO DE PADRÕES")
    print("=" * 62)
    print(f"  Padrões: Doji, Martelo, Estrela Cadente, Engolfo,")
    print(f"           Pin Bar, Inside/Outside, MHI1-3, LHI1-3,")
    print(f"           3 Soldados, 3 Corvos, Torres Gêmeas")
    print("=" * 62)

    for symbol in SYMBOLS:
        print(f"\n{'─' * 40}")
        for tf in INPUT_TFS + CONTEXT_TFS:
            process_symbol(symbol, tf)

    print(f"\n{'=' * 62}")
    print(f"  ✅ PADRÕES PROCESSADOS!")
    print(f"{'=' * 62}")


if __name__ == "__main__":
    main()
