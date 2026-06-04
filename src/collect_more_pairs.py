#!/usr/bin/env python3.12
"""Coleta NOVOS pares forex OTC + versões NORMAL para comparação."""
import os, sys, asyncio, json, time
from datetime import datetime
import pandas as pd

os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.getcwd())

DATA_DIR = "data/raw/quotex"
os.makedirs(DATA_DIR, exist_ok=True)

# NOVOS pares OTC para coletar
NEW_OTC = {
    "EURJPY":  "EURJPY_otc",
    "EURGBP":  "EURGBP_otc",
    "GBPJPY":  "GBPJPY_otc",
    "AUDUSD":  "AUDUSD_otc",
    "NZDUSD":  "NZDUSD_otc",
    "EURAUD":  "EURAUD_otc",
    "EURCAD":  "EURCAD_otc",
    "GBPAUD":  "GBPAUD_otc",
    "GBPCAD":  "GBPCAD_otc",
    "AUDJPY":  "AUDJPY_otc",
    "CADJPY":  "CADJPY_otc",
    "CHFJPY":  "CHFJPY_otc",
    "AUDCAD":  "AUDCAD_otc",
    "BRLUSD":  "BRLUSD_otc",
}

# Versoes NORMAL (nao OTC) dos principais
NORMAL = {
    "EURUSD_N": "EURUSD",
    "GBPUSD_N": "GBPUSD",
    "USDJPY_N": "USDJPY",
    "USDCHF_N": "USDCHF",
    "USDCAD_N": "USDCAD",
}

# TFs
TFs = [
    ("M1",  60,   259200,   "3 dias"),
    ("M5",  300,  1209600,  "14 dias"),
    ("M15", 900,  2592000,  "30 dias"),
]

async def fetch(client, name, asset, tf_label, period, seconds):
    try:
        candles = await asyncio.wait_for(
            client.get_historical_candles(asset, amount_of_seconds=seconds, period=period, max_workers=8),
            timeout=90
        )
        count = len(candles) if candles else 0
        if count > 0:
            first = datetime.fromtimestamp(candles[0]["time"])
            last = datetime.fromtimestamp(candles[-1]["time"])
            cov = (candles[-1]["time"] - candles[0]["time"]) / 3600
            
            df = pd.DataFrame(candles)
            df.rename(columns={"time": "timestamp", "ticks": "volume"}, inplace=True)
            df["timestamp"] = pd.to_datetime(df["timestamp"], unit="s")
            df = df.sort_values("timestamp").reset_index(drop=True)
            
            fname = f"{DATA_DIR}/{name}_{tf_label}.csv"
            df.to_csv(fname, index=False)
            
            print(f"  ✅ {name:8s} {tf_label:4s} | {count:>5d} candles ({cov:.1f}h) -> {fname}")
            return count
        else:
            print(f"  ⚠️ {name:8s} {tf_label:4s} | 0 candles")
            return 0
    except asyncio.TimeoutError:
        print(f"  ⏱️ {name:8s} {tf_label:4s} | TIMEOUT")
        return 0
    except Exception as e:
        print(f"  ❌ {name:8s} {tf_label:4s} | ERRO: {str(e)[:60]}")
        return 0

async def main():
    from pyquotex.stable_api import Quotex
    email = os.environ.get("QUOTEX_EMAIL", "")
    pw = os.environ.get("QUOTEX_PASSWORD", "")
    
    client = Quotex(email=email, password=pw, lang="pt")
    await client.connect()
    bal = await client.get_balance()
    
    total_pairs = len(NEW_OTC) + len(NORMAL)
    total_lotes = total_pairs * len(TFs)
    
    print(f"{'='*65}")
    print(f"  🚀 COLETA NOVOS PARES QUOTEX")
    print(f"  {datetime.now().strftime('%d/%m/%Y %H:%M')} UTC")
    print(f"  💰 Saldo DEMO: R$ {bal:.2f}")
    print(f"  📊 {total_pairs} pares × {len(TFs)} TFs = {total_lotes} lotes")
    print(f"{'='*65}")
    
    # Juntar todos
    ALL = {**NEW_OTC, **NORMAL}
    total_candles = 0
    lotes_ok = 0
    lotes_total = 0
    
    for name, asset in ALL.items():
        print(f"\n{'─'*50}")
        print(f"  📥 {name:8s} ({asset})")
        print(f"{'─'*50}")
        
        for tf_label, period, seconds, label in TFs:
            if lotes_total > 0:
                await asyncio.sleep(2)
            
            count = await fetch(client, name, asset, tf_label, period, seconds)
            total_candles += count
            lotes_total += 1
            if count > 0:
                lotes_ok += 1
    
    await client.close()
    
    print(f"\n{'='*65}")
    print(f"  ✅ COLETA CONCLUÍDA!")
    print(f"  📊 {total_candles} candles, {lotes_ok}/{lotes_total} lotes OK")
    print(f"{'='*65}")

if __name__ == "__main__":
    asyncio.run(main())
