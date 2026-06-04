#!/usr/bin/env python3.12
"""Analisa volatilidade dos pares forex OTC para calibrar spreads ideais."""
import os, sys, json
import pandas as pd
import numpy as np

os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.getcwd())

RAW_DIR = "data/raw/quotex"
FOREX_PAIRS = ["EUR", "JPY", "GBP", "CHF", "CAD"]

def analyze_volatility(df, name, tf):
    """Analisa retornos e sugere spreads ideais."""
    df = df.copy()
    
    # Retornos
    returns = df["close"].pct_change().dropna()
    
    # Estatisticas
    mean_abs_return = returns.abs().mean()
    median_abs_return = returns.abs().median()
    std_return = returns.std()
    q75 = returns.abs().quantile(0.75)
    q90 = returns.abs().quantile(0.90)
    atr = (df["high"] - df["low"]).mean() / df["close"].mean()
    
    return {
        "mean_abs_return": float(mean_abs_return),
        "median_abs_return": float(median_abs_return),
        "std_return": float(std_return),
        "q75_return": float(q75),
        "q90_return": float(q90),
        "atr_pct": float(atr),
    }

def main():
    results = {}
    
    for name in FOREX_PAIRS:
        for tf in ["M1", "M5", "M15"]:
            fpath = f"{RAW_DIR}/{name}_{tf}.csv"
            if not os.path.exists(fpath):
                continue
            
            df = pd.read_csv(fpath)
            vol = analyze_volatility(df, name, tf)
            
            # Sugerir spreads
            # call_1: queremos capturar movimentos acima de 1.5x o retorno medio
            # call_5: acima de 2.5x o retorno medio (5 candles a frente)
            vol["suggested_spread_1"] = max(vol["q75_return"], vol["mean_abs_return"] * 1.5)
            vol["suggested_spread_5"] = max(vol["q90_return"], vol["mean_abs_return"] * 3.0)
            
            if name not in results:
                results[name] = {}
            results[name][tf] = vol
    
    print(f"{'='*75}")
    print("  📊 ANÁLISE DE VOLATILIDADE - PARES FOREX OTC")
    print(f"{'='*75}")
    print(f"{'PAR':6s} {'TF':4s} {'Ret.Médio':>10s} {'Mediana':>8s} {'Std':>8s} {'Q75':>8s} {'Q90':>8s} {'ATR%':>8s} {'Spread1':>9s} {'Spread5':>9s}")
    print(f"{'-'*75}")
    
    for name in FOREX_PAIRS:
        for tf in ["M1", "M5", "M15"]:
            if name not in results or tf not in results[name]:
                continue
            v = results[name][tf]
            print(f"{name:6s} {tf:4s} {v['mean_abs_return']:>10.5f} {v['median_abs_return']:>8.5f} "
                  f"{v['std_return']:>8.5f} {v['q75_return']:>8.5f} {v['q90_return']:>8.5f} "
                  f"{v['atr_pct']:>8.4f} {v['suggested_spread_1']:>9.5f} {v['suggested_spread_5']:>9.5f}")
    
    print(f"\n{'='*75}")
    print("  🎯 SPREADS SUGERIDOS PARA CADA PAR/TF")
    print(f"{'='*75}")
    
    spreads_config = {}
    for name in FOREX_PAIRS:
        if name not in results:
            continue
        spreads_config[name] = {}
        for tf in ["M1", "M5", "M15"]:
            if tf not in results[name]:
                continue
            v = results[name][tf]
            s1 = round(v["suggested_spread_1"], 5)
            s5 = round(v["suggested_spread_5"], 5)
            spreads_config[name][tf] = {"spread_1": s1, "spread_5": s5}
            print(f"  {name:4s} {tf:4s}: call_1 spread={s1:.5f}  call_5 spread={s5:.5f}")
    
    # Salvar config
    config_path = "config/quotex_spreads.json"
    os.makedirs("config", exist_ok=True)
    with open(config_path, "w") as f:
        json.dump(spreads_config, f, indent=2)
    print(f"\n  Config salva em: {config_path}")
    
    # Comparar com cripto
    print(f"\n{'='*75}")
    print("  📊 COMPARAÇÃO: CRIPTO vs FOREX (M5)")
    print(f"{'='*75}")
    
    for name in ["BTC", "ETH", "SOL", "LTC", "BNB"]:
        fpath = f"{RAW_DIR}/{name}_M5.csv"
        if not os.path.exists(fpath):
            continue
        df = pd.read_csv(fpath)
        returns = df["close"].pct_change().dropna().abs()
        print(f"  {name:4s} M5: retorno médio={returns.mean():.5f}  Q75={returns.quantile(0.75):.5f}  Q90={returns.quantile(0.90):.5f}")

if __name__ == "__main__":
    main()
