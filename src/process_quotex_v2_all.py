#!/usr/bin/env python3.12
"""Re-processa TODOS os arquivos Quotex com spreads calibrados."""
import os, sys, json, warnings
import pandas as pd
import numpy as np
from ta.momentum import RSIIndicator
from ta.trend import MACD, EMAIndicator, ADXIndicator
from ta.volatility import BollingerBands, AverageTrueRange
warnings.filterwarnings("ignore")

os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.getcwd())

RAW_DIR = "data/raw/quotex"
OUT_DIR = "data/processed/quotex_v2"
os.makedirs(OUT_DIR, exist_ok=True)

# Cripto names
CRYPTO = {"BTC","ETH","SOL","LTC","BNB"}

# Spreads cripto (default)
CRYPTO_SPREAD = {"call_1": 0.0008, "call_5": 0.0020}

# Spreads forex calibrados (serao usados como fallback)
FOREX_FALLBACK = {"call_1": 0.0005, "call_5": 0.0010}

def get_spread(name, tf, target):
    """Retorna spread calibrado."""
    # Cripto
    if name in CRYPTO:
        return CRYPTO_SPREAD[target]
    
    # Pares especificos com calibracao manual baseada na volatilidade
    spreads = {
        "EUR":  {"M1": (0.00032, 0.00064), "M5": (0.00072, 0.00145), "M15": (0.00131, 0.00262)},
        "JPY":  {"M1": (0.00032, 0.00063), "M5": (0.00072, 0.00143), "M15": (0.00127, 0.00254)},
        "GBP":  {"M1": (0.00003, 0.00006), "M5": (0.00007, 0.00014), "M15": (0.00014, 0.00029)},
        "CHF":  {"M1": (0.00032, 0.00064), "M5": (0.00072, 0.00143), "M15": (0.00126, 0.00252)},
        "CAD":  {"M1": (0.00020, 0.00041), "M5": (0.00048, 0.00097), "M15": (0.00084, 0.00169)},
    }
    
    # Verificar se name esta na lista de spreads conhecidos
    if name in spreads and tf in spreads[name]:
        s1, s5 = spreads[name][tf]
        return s1 if target == "call_1" else s5
    
    # Para pares forex que nao tem calibracao ainda (EURJPY, etc), usar fallback 0.0005/0.0010
    # Verificar se parece forex (contem letras de pares forex)
    if any(f in name for f in ["EUR","JPY","GBP","CHF","CAD","NZD","AUD","BRL"]):
        return FOREX_FALLBACK[target]
    
    return CRYPTO_SPREAD[target]


def compute_features(df, name, tf):
    """Calcula features + targets com spreads calibrados."""
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
    
    # RSI
    df["rsi_14"] = RSIIndicator(df["close"], 14).rsi()
    df["rsi_7"] = RSIIndicator(df["close"], 7).rsi()
    df["rsi_21"] = RSIIndicator(df["close"], 21).rsi()
    
    # MACD
    macd = MACD(df["close"])
    df["macd"] = macd.macd()
    df["macd_signal"] = macd.macd_signal()
    df["macd_hist"] = macd.macd_diff()
    
    # EMAs
    for period in [7, 14, 21, 50, 100, 200]:
        df[f"ema_{period}"] = EMAIndicator(df["close"], period).ema_indicator()
        df[f"dist_ema_{period}"] = (df["close"] - df[f"ema_{period}"]) / df[f"ema_{period}"]
        df[f"ema_{period}_slope"] = df[f"ema_{period}"].diff(5)
    
    # Bollinger
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
    
    # Volatilidade
    df["volatility_5"] = df["return_1"].rolling(5).std()
    df["volatility_10"] = df["return_1"].rolling(10).std()
    df["volatility_20"] = df["return_1"].rolling(20).std()
    
    # TARGETS com spreads CALIBRADOS
    sp1 = get_spread(name, tf, "call_1")
    sp5 = get_spread(name, tf, "call_5")
    
    df["target_call_1"] = ((df["close"].shift(-1) - df["close"]) / df["close"] > sp1).astype(int)
    df["target_put_1"] = ((df["close"] - df["close"].shift(-1)) / df["close"] > sp1).astype(int)
    df["target_call_5"] = ((df["close"].shift(-5) - df["close"]) / df["close"] > sp5).astype(int)
    df["target_put_5"] = ((df["close"] - df["close"].shift(-5)) / df["close"] > sp5).astype(int)
    
    df = df.dropna().reset_index(drop=True)
    
    return df


def main():
    files = sorted([f for f in os.listdir(RAW_DIR) if f.endswith(".csv")])
    print(f"Processando {len(files)} arquivos...")
    
    summary = []
    
    for fname in files:
        raw_path = f"{RAW_DIR}/{fname}"
        out_path = f"{OUT_DIR}/{fname}"
        
        # Extrair nome e TF do filename
        parts = fname.replace(".csv", "").split("_")
        tf = parts[-1]
        name = "_".join(parts[:-1])
        
        print(f"  {fname:25s} [{name:12s} {tf:4s}]...", end=" ", flush=True)
        
        try:
            df = pd.read_csv(raw_path)
            raw_n = len(df)
            df_proc = compute_features(df, name, tf)
            proc_n = len(df_proc)
            df_proc.to_csv(out_path, index=False)
            
            # Estatisticas dos targets
            c1 = f"{df_proc['target_call_1'].mean()*100:.1f}%"
            p1 = f"{df_proc['target_put_1'].mean()*100:.1f}%"
            c5 = f"{df_proc['target_call_5'].mean()*100:.1f}%"
            p5 = f"{df_proc['target_put_5'].mean()*100:.1f}%"
            
            sp1 = get_spread(name, tf, "call_1")
            sp5 = get_spread(name, tf, "call_5")
            
            print(f"OK | {raw_n}->{proc_n} | sp1={sp1:.5f} sp5={sp5:.5f} | C1:{c1} P1:{p1} C5:{c5} P5:{p5}")
            
            summary.append({
                "file": fname, "name": name, "tf": tf,
                "candles": proc_n, "spread_1": sp1, "spread_5": sp5,
                "c1_pct": c1, "p1_pct": p1, "c5_pct": c5, "p5_pct": p5
            })
            
        except Exception as e:
            print(f"ERRO: {str(e)[:60]}")
    
    # Salvar summary
    with open(f"{OUT_DIR}/summary.json", "w") as f:
        json.dump(summary, f, indent=2)
    
    print(f"\n{'='*70}")
    print(f"  ✅ PROCESSAMENTO V2 CONCLUIDO!")
    print(f"  📁 {OUT_DIR}/")
    print(f"  📊 {len(summary)} arquivos processados")
    print(f"{'='*70}")

if __name__ == "__main__":
    main()
