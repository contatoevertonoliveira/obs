#!/usr/bin/env python3.12
"""Testa limites com M5, M15 para periodos mais longos."""
import os, sys, asyncio
from datetime import datetime

os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.getcwd())

async def test(client, label, asset, secs, period, workers, timeout=120):
    print(f"\n{label:35s}...", end=" ", flush=True)
    try:
        candles = await asyncio.wait_for(
            client.get_historical_candles(asset, amount_of_seconds=secs, period=period, max_workers=workers),
            timeout=timeout
        )
        count = len(candles) if candles else 0
        if count > 0:
            first = datetime.fromtimestamp(candles[0]["time"])
            last = datetime.fromtimestamp(candles[-1]["time"])
            cov = (candles[-1]["time"] - candles[0]["time"]) / 3600
            expected = cov * 3600 / period
            density = count / (cov / 24 * (86400 / period)) * 100
            print(f"{count:>5d} candles ({cov:.1f}h, {density:.0f}% dens.) | {first.strftime('%d/%m')} -> {last.strftime('%d/%m')}")
        else:
            print("0 candles")
    except asyncio.TimeoutError:
        print(f"TIMEOUT ({timeout}s)")
    except Exception as e:
        print(f"ERRO: {str(e)[:80]}")

async def main():
    from pyquotex.stable_api import Quotex
    email = os.environ.get("QUOTEX_EMAIL", "")
    pw = os.environ.get("QUOTEX_PASSWORD", "")
    client = Quotex(email=email, password=pw, lang="pt")
    await client.connect()
    bal = await client.get_balance()
    print(f"Saldo DEMO: R$ {bal:.2f}")
    
    # M5 - testar 7, 14, 30 dias
    await test(client, "BTC 7d M5 (wrk=8)", "BTCUSD_otc", 604800, 300, 8)
    await test(client, "BTC 14d M5 (wrk=8)", "BTCUSD_otc", 1209600, 300, 8)
    await test(client, "BTC 30d M5 (wrk=10, 180s)", "BTCUSD_otc", 2592000, 300, 10, 180)
    
    # M15 - testar 30, 60 dias
    await test(client, "BTC 30d M15 (wrk=8)", "BTCUSD_otc", 2592000, 900, 8)
    await test(client, "BTC 60d M15 (wrk=10, 180s)", "BTCUSD_otc", 5184000, 900, 10, 180)
    
    # Se M5 funciona pra 14 dias, testar todos ativos em M5
    await client.close()

if __name__ == "__main__":
    asyncio.run(main())
