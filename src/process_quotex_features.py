#!/usr/bin/env python3.12
"""Processa features dos dados brutos da Quotex."""
import os, sys, warnings
import pandas as pd
import numpy as np
from ta.momentum import RSIIndicator
from ta.trend import MACD, EMAIndicator, ADXIndicator
from ta.volatility import BollingerBands, AverageTrueRange
warnings.filterwarnings("ignore")

os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.getcwd())

RAW_DIR = "data/raw/quotex"
OUT_DIR = "data/processed/quotex"
os.makedirs(OUT_DIR, exist_ok=True)

# Lista de features a calcular
def compute_features(df):
    """Calcula features técnicas num DataFrame OHLCV."""
    df = df.copy()
    
    # Retornos
    df["return_1"] = df["close"].pct_change()
    df["return_5"] = df["close"].pct_change(5)
    df["return_10"] = df["close"].pct_change(10)
    df["return_20"] = df["close"].pct_change(20)
    
    # Range e corpo
    df["range"] = (df["high"] - df["low"]) / df["close"]
    df["body"] = abs(df["close"] - df["open"]) / (df["high"] - df["low"] + 1e-10)
    df["upper_shadow"] = (df["high"] - np.maximum(df["open"], df["close"])) / (df["high"] - df["low"] + 1e-10)
    df["lower_shadow"] = (np.minimum(df["open"], df["close"]) - df["low"]) / (df["high"] - df["low"] + 1e-10)
    
    # RSI (14, 7, 21)
    df["rsi_14"] = RSIIndicator(df["close"], 14).rsi()
    df["rsi_7"] = RSIIndicator(df["close"], 7).rsi()
    df["rsi_21"] = RSIIndicator(df["close"], 21).rsi()
    
    # MACD
    macd = MACD(df["close"])
    df["macd"] = macd.macd()
    df["macd_signal"] = macd.macd_signal()
    df["macd_hist"] = macd.macd_diff()
    
    # EMA
    for period in [7, 14, 21, 50, 100, 200]:
        df[f"ema_{period}"] = EMAIndicator(df["close"], period).ema_indicator()
        # Distância do preço à EMA
        df[f"dist_ema_{period}"] = (df["close"] - df[f"ema_{period}"]) / df[f"ema_{period}"]
        # Slope da EMA
        df[f"ema_{period}_slope"] = df[f"ema_{period}"].diff(5)
    
    # Bollinger Bands
    bb = BollingerBands(df["close"])
    df["bb_upper"] = bb.bollinger_hband()
    df["bb_lower"] = bb.bollinger_lband()
    df["bb_width"] = (bb.bollinger_hband() - bb.bollinger_lband()) / df["close"]
    df["bb_pct"] = (df["close"] - bb.bollinger_lband()) / (bb.bollinger_hband() - bb.bollinger_lband() + 1e-10)
    
    # ATR
    atr = AverageTrueRange(df["high"], df["low"], df["close"])
    df["atr"] = atr.average_true_range()
    df["atr_pct"] = atr.average_true_range() / df["close"]
    
    # ADX
    adx = ADXIndicator(df["high"], df["low"], df["close"])
    df["adx"] = adx.adx()
    df["plus_di"] = adx.adx_pos()
    df["minus_di"] = adx.adx_neg()
    
    # Volume
    df["volume_ma"] = df["volume"].rolling(20).mean()
    df["volume_ratio"] = df["volume"] / (df["volume_ma"] + 1e-10)
    
    # Volatilidade (desvio padrao rolling)
    df["volatility_5"] = df["return_1"].rolling(5).std()
    df["volatility_10"] = df["return_1"].rolling(10).std()
    df["volatility_20"] = df["return_1"].rolling(20).std()
    
    # Targets - CALL/PUT
    for ahead in [1, 5]:
        spread = 0.0005 if ahead == 1 else 0.0015
        df[f"target_call_{ahead}"] = (
            (df["close"].shift(-ahead) - df["close"]) / df["close"] > spread
        ).astype(int)
        df[f"target_put_{ahead}"] = (
            (df["close"] - df["close"].shift(-ahead)) / df["close"] > spread
        ).astype(int)
    
    # Remover linhas com NaN (do rolling)
    df = df.dropna().reset_index(drop=True)
    
    return df


def main():
    files = sorted(os.listdir(RAW_DIR))
    print(f"Processando {len(files)} arquivos de {RAW_DIR}/")
    
    for fname in files:
        if not fname.endswith(".csv"):
            continue
        
        raw_path = f"{RAW_DIR}/{fname}"
        out_path = f"{OUT_DIR}/{fname}"
        
        print(f"\n  📥 {fname:25s}...", end=" ", flush=True)
        
        try:
            df = pd.read_csv(raw_path)
            raw_count = len(df)
            
            df_proc = compute_features(df)
            proc_count = len(df_proc)
            
            # Salvar
            df_proc.to_csv(out_path, index=False)
            
            # Features geradas
            feat_cols = [c for c in df_proc.columns if c not in [
                "symbol_id", "timestamp", "open", "high", "low", "close",
                "volume", "last_tick", "asset",
                "target_call_1", "target_put_1", "target_call_5", "target_put_5"
            ]]
            
            print(f"✅ {raw_count} -> {proc_count} candles, {len(feat_cols)} features")
            
        except Exception as e:
            print(f"❌ ERRO: {str(e)[:80]}")
    
    print(f"\n✅ Processamento concluído! Dados em {OUT_DIR}/")

if __name__ == "__main__":
    main()
