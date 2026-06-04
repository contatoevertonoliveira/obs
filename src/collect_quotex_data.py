#!/usr/bin/env python3.12
"""Coleta dados Quotex para treino - lote por lote, sem travar."""
import os, sys, asyncio, json, time
from datetime import datetime
import pandas as pd

os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.getcwd())

DATA_DIR = "data/raw/quotex"
os.makedirs(DATA_DIR, exist_ok=True)

# Config: ativo -> (asset_code)
ASSETS = {
    "BTC":  "BTCUSD_otc",
    "ETH":  "ETHUSD_otc",
    "SOL":  "SOLUSD_otc",
    "LTC":  "LTCUSD_otc",
    "BNB":  "BNBUSD_otc",
    "EUR":  "EURUSD_otc",
    "JPY":  "USDJPY_otc",
    "GBP":  "GBPUSD_otc",
    "CHF":  "USDCHF_otc",
    "CAD":  "USDCAD_otc",
}

# TFs que sabemos que funcionam
TFs = [
    ("M1",  60,   259200,   "3 dias"),     # 3 dias -> ~4300 candles
    ("M5",  300,  1209600,  "14 dias"),    # 14 dias -> ~4000 candles
    ("M15", 900,  2592000,  "30 dias"),    # 30 dias -> ~2900 candles
]

async def fetch_single(client, name, asset, tf_label, period, seconds, label):
    """Baixa candles de 1 ativo+TF."""
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
            
            # Salvar CSV
            df = pd.DataFrame(candles)
            df.rename(columns={"time": "timestamp", "ticks": "volume"}, inplace=True)
            df["timestamp"] = pd.to_datetime(df["timestamp"], unit="s")
            df = df.sort_values("timestamp").reset_index(drop=True)
            
            fname = f"{DATA_DIR}/{name}_{tf_label}.csv"
            df.to_csv(fname, index=False)
            
            print(f"  ✅ {name:4s} {tf_label:4s} | {count:>5d} candles ({cov:.1f}h)"
                  f" [{first.strftime('%d/%m %H:%M')} -> {last.strftime('%d/%m %H:%M')}]"
                  f" -> {fname}")
            return count
        else:
            print(f"  ⚠️ {name:4s} {tf_label:4s} | 0 candles")
            return 0
    except asyncio.TimeoutError:
        print(f"  ⏱️ {name:4s} {tf_label:4s} | TIMEOUT (90s)")
        return 0
    except Exception as e:
        print(f"  ❌ {name:4s} {tf_label:4s} | ERRO: {str(e)[:80]}")
        return 0

async def main():
    from pyquotex.stable_api import Quotex
    email = os.environ.get("QUOTEX_EMAIL", "")
    pw = os.environ.get("QUOTEX_PASSWORD", "")
    
    client = Quotex(email=email, password=pw, lang="pt")
    await client.connect()
    bal = await client.get_balance()
    
    print(f"{'='*65}")
    print(f"  🚀 COLETA MASSA DADOS QUOTEX")
    print(f"  {datetime.now().strftime('%d/%m/%Y %H:%M')} UTC")
    print(f"  💰 Saldo DEMO: R$ {bal:.2f}")
    print(f"  📁 Salvando em: {DATA_DIR}/")
    print(f"  📊 {len(ASSETS)} ativos × {len(TFs)} TFs = {len(ASSETS)*len(TFs)} lotes")
    print(f"{'='*65}")
    
    total_candles = 0
    total_lotes = 0
    lotes_ok = 0
    
    for name, asset in ASSETS.items():
        print(f"\n{'─'*50}")
        print(f"  📥 ATIVO: {name:4s} ({asset})")
        print(f"{'─'*50}")
        
        for tf_label, period, seconds, label in TFs:
            # Pausa de 3s entre chamadas pra não sobrecarregar
            if total_lotes > 0:
                await asyncio.sleep(3)
            
            count = await fetch_single(client, name, asset, tf_label, period, seconds, label)
            total_candles += count
            total_lotes += 1
            if count > 0:
                lotes_ok += 1
    
    await client.close()
    
    # Resumo final
    print(f"\n{'='*65}")
    print(f"  ✅ COLETA CONCLUÍDA!")
    print(f"  📊 Total: {total_candles} candles em {lotes_ok}/{total_lotes} lotes OK")
    print(f"  📁 Arquivos em: {DATA_DIR}/")
    print(f"{'='*65}")
    
    # Listar arquivos
    files = sorted(os.listdir(DATA_DIR))
    print(f"\n  Arquivos gerados ({len(files)}):")
    for f in files:
        size = os.path.getsize(f"{DATA_DIR}/{f}")
        print(f"    {f:25s} {size:>7,d} bytes")

if __name__ == "__main__":
    asyncio.run(main())
