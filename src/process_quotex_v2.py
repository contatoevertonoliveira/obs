#!/usr/bin/env python3.12
"""Re-processa TODOS os dados Quotex com spreads calibrados por par+TF."""
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

# Carregar spreads calibrados
SPREADS_PATH = "config/quotex_spreads.json"
if os.path.exists(SPREADS_PATH):
    with open(SPREADS_PATH) as f:
        CALIBRATED_SPREADS = json.load(f)
    print(f"✅ Spreads calibrados carregados de {SPREADS_PATH}")
else:
    CALIBRATED_SPREADS = {}
    print("⚠️  Usando spreads padrão")

# Spreads padrão (fallback) - separados por classe
DEFAULT_SPREADS = {
    "crypto": {"call_1": 0.0008, "call_5": 0.0020},
    "forex":  {"call_1": 0.0005, "call_5": 0.0010},
}

# Identificar se é forex ou crypto pelo nome
FOREX_NAMES = {"EUR","JPY","GBP","CHF","CAD","EURJPY","EURGBP","GBPJPY",
               "AUDUSD","NZDUSD","EURAUD","EURCAD","GBPAUD","GBPCAD",
               "AUDJPY","CADJPY","CHFJPY","AUDCAD","BRLUSD",
               "EURUSD_N","GBPUSD_N","USDJPY_N","USDCHF_N","USDCAD_N"}

def get_spread(name, tf, target):
    """Retorna spread calibrado ou padrão."""
    if name in CALIBRATED_SPREADS and tf in CALIBRATED_SPREADS[name]:
        cfg = CALIBRATED_SPREADS[name][tf]
        if target == "call_1":
            return cfg.get("spread_1", DEFAULT_SPREADS["forex"]["call_1"])
        else:
            return cfg.get("spread_5", DEFAULT_SPREADS["forex"]["call_5"])
    
    # Fallback por classe
    if name in FOREX_NAMES or name.startswith("EUR") or any(c.isalpha() for c in name if c.isupper()):
        # Check if it's forex
        if any(f in name for f in ["EUR","JPY","GBP","CHF","CAD","AUD","NZD","BRL"]):
            return DEFAULT_SPREADS["forex"]["call_1"] if target == "call_1" else DEFAULT_SPREADS["forex"]["call_5"]
    
    return DEFAULT_SPREADS["crypto"]["call_1"] if target == "call_1" else DEFAULT_SPREADS["crypto"]["call_5"]


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
    
    # Log info dos targets
    bal_call1 = df["target_call_1"].mean() * 100
    bal_put1 = df["target_put_1"].mean() * 100
    bal_call5 = df["target_call_5"].mean() * 100
    bal_put5 = df["target_put_5"].mean() * 100
    
    df = df.dropna().reset_index(drop=True)
    
    return df, {
        "spread_1": sp1, "spread_5": sp5,
        "bal_call_1": f"{bal_call1:.1f}%",
        "bal_put_1": f"{bal_put1:.1f}%",
        "bal_call_5": f"{bal_call5:.1f}%",
        "bal_put_5": f"{bal_put5:.1f}%",
    }


def main():
    files = sorted([f for f in os.listdir(RAW_DIR) if f.endswith(".csv")])
    print(f"Processando {len(files)} arquivos com spreads calibrados...")
    
    stats = []
    
    for fname in files:
        raw_path = f"{RAW_DIR}/{fname}"
        out_path = f"{OUT_DIR}/{fname}"
        
        # Extrair nome do ativo e TF do filename
        parts = fname.replace(".csv", "").split("_")
        if len(parts) < 2:
            continue
        # Nome pode ser "BNB_M1" ou "EURJPY_M1" ou "EURUSD_N_M1"
        # Tentar extrair: nome e tf
        tf = parts[-1]  # M1, M5, M15
        name = "_".join(parts[:-1])  # BNB, EURJPY, EURUSD_N
        
        print(f"\n  📥 {fname:25s} [{name:8s} {tf:4s}]...", end=" ", flush=True)
        
        try:
            df = pd.read_csv(raw_path)
            raw_count = len(df)
            
            df_proc, info = compute_features(df, name, tf)
            proc_count = len(df_proc)
            
            df_proc.to_csv(out_path, index=False)
            
            feat_cols = len([c for c in df_proc.columns if "target" not in c 
                            and c not in ["symbol_id","timestamp","open","high","low",
                                         "close","volume","last_tick","asset"]])
            
            print(f"✅ {raw_count}->{proc_count} candles | {feat_cols} features | "
                  f"sp1={info['spread_1']:.5f} sp5={info['spread_5']:.5f} | "
                  f"C1:{info['bal_call_1']} P1:{info['bal_put_1']} C5:{info['bal_call_5']} P5:{info['bal_put_5']}")
            
            stats.append({
                "file": fname, "name": name, "tf": tf,
                "raw": raw_count, "processed": proc_count,
                **info
            })
            
        except Exception as e:
            print(f"❌ ERRO: {str(e)[:80]}")
    
    # Resumo
    print(f"\n{'='*70}")
    print("  📊 RESUMO - TARGETS COM SPREADS CALIBRADOS")
    print(f"{'='*70}")
    print(f"{'ARQUIVO':25s} {'SP1':>8s} {'SP5':>8s}  C1    P1    C5    P5")
    print(f"{'-'*70}")
    for s in stats:
        print(f"{s['file']:25s} {s['spread_1']:>8.5f} {s['spread_5']:>8.5f}  "
              f"{s['bal_call_1']:>5s} {s['bal_put_1']:>5s} {s['bal_call_5']:>5s} {s['bal_put_5']:>5s}")
    
    print(f"\n✅ Processamento concluído! Dados em {OUT_DIR}/")
    print(f"   {len(stats)} arquivos processados")

if __name__ == "__main__":
    main()
