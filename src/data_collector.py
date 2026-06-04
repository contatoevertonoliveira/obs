#!/usr/bin/env python3
"""
Hermes Quant V2 — Data Lake Collector
Coleta OHLCV da Binance Futures com checkpointing.
Foco: M1, M5, M15 para opções binárias (H1, H4 só contexto).
Armazena em Parquet (zstd) para performance.
"""
import os, sys, json, time
from datetime import datetime, timezone, timedelta

import ccxt
import pandas as pd

os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ".")
from config.settings import (
    SYMBOLS, ALL_TFS, INPUT_TFS, TF_LABEL, TF_MS,
    LIMIT, MIN_HISTORY_DAYS, RAW_DIR, CHECKPOINT_FILE,
)

os.makedirs(RAW_DIR, exist_ok=True)

# ── Exchange ──────────────────────────────────────────────────────────
exchange = ccxt.binance({
    "enableRateLimit": True,
    "options": {"defaultType": "future"},
})

def load_checkpoints():
    if os.path.exists(CHECKPOINT_FILE):
        with open(CHECKPOINT_FILE) as f:
            return json.load(f)
    return {}

def save_checkpoints(cp):
    with open(CHECKPOINT_FILE, "w") as f:
        json.dump(cp, f, indent=2)

def get_start_time():
    return int((datetime.now(timezone.utc) - timedelta(days=MIN_HISTORY_DAYS)).timestamp() * 1000)

def fetch_all_ohlcv(symbol, tf, since):
    key = f"{symbol}:{tf}"
    checkpoints = load_checkpoints()
    if key in checkpoints and checkpoints[key] is not None:
        since = checkpoints[key]

    all_candles = []
    retries = 0
    max_retries = 5
    label = TF_LABEL.get(tf, tf)
    is_input = "📊" if tf in INPUT_TFS else "📐"
    symbol_short = symbol.replace("/USDT", "")

    parquet_path = os.path.join(RAW_DIR, f"{symbol.replace('/', '_')}_{label}.parquet")
    existing_df = pd.DataFrame()
    if os.path.exists(parquet_path):
        try:
            existing_df = pd.read_parquet(parquet_path)
            if not existing_df.empty:
                last_ts = int(existing_df["timestamp"].max())
                if last_ts > since:
                    since = last_ts + TF_MS[tf]
        except Exception:
            pass

    ts_step = LIMIT * TF_MS[tf]
    loop_count = 0

    while True:
        now_ms = int(time.time() * 1000)
        if since >= now_ms:
            break

        try:
            candles = exchange.fetch_ohlcv(symbol, tf, since=since, limit=LIMIT)
        except Exception as e:
            retries += 1
            if retries > max_retries:
                print(f"    ✗ ERRO: {e}")
                break
            wait = 2 ** retries
            print(f"    ⚠ Retry {retries}/{max_retries} em {wait}s: {e}")
            time.sleep(wait)
            continue

        if not candles:
            break

        all_candles.extend(candles)
        loop_count += 1
        last_ts = candles[-1][0]
        checkpoints[key] = last_ts
        save_checkpoints(checkpoints)
        since = last_ts + TF_MS[tf]

        # Progresso a cada 10 lotes
        if loop_count % 10 == 0:
            pct = min(100, (last_ts - get_start_time()) / (now_ms - get_start_time()) * 100)
            print(f"  {is_input} {symbol_short:6s} {label:4s} → {len(all_candles):>6,d} candles ({pct:.0f}%)")

        # Salva incrementalmente a cada 5000 candles
        if len(all_candles) >= 5000:
            df_new = pd.DataFrame(all_candles, columns=["timestamp","open","high","low","close","volume"])
            df_new["timestamp"] = df_new["timestamp"].astype("int64")
            df_new["symbol"] = symbol
            df = pd.concat([existing_df, df_new], ignore_index=True) if not existing_df.empty else df_new
            df = df.drop_duplicates(subset=["timestamp", "symbol"], keep="last").sort_values("timestamp").reset_index(drop=True)
            df.to_parquet(parquet_path, index=False, compression="zstd")
            all_candles = []
            existing_df = df

        time.sleep(0.3)

    # Final save
    if all_candles:
        df_new = pd.DataFrame(all_candles, columns=["timestamp","open","high","low","close","volume"])
        df_new["timestamp"] = df_new["timestamp"].astype("int64")
        df_new["symbol"] = symbol
        df = pd.concat([existing_df, df_new], ignore_index=True) if not existing_df.empty else df_new
        df = df.drop_duplicates(subset=["timestamp", "symbol"], keep="last").sort_values("timestamp").reset_index(drop=True)
        df.to_parquet(parquet_path, index=False, compression="zstd")
    elif not existing_df.empty:
        df = existing_df
    else:
        print(f"    ⚠ {symbol_short:6s} {label:4s} → vazio")
        return

    print(f"  ✅ {symbol_short:6s} {label:4s} → {len(df):>8,d} candles salvos")
    return df

def main():
    print("=" * 62)
    print("  🏗️  HERMES QUANT V2 — DATA LAKE (OPÇÕES BINÁRIAS)")
    print("=" * 62)
    print(f"  Fonte: Binance Futures")
    print(f"  Símbolos: {len(SYMBOLS)}")
    print(f"  Entrada: {', '.join(TF_LABEL[tf] for tf in INPUT_TFS)}")
    print(f"  Contexto: {', '.join(TF_LABEL[tf] for tf in ALL_TFS if tf not in INPUT_TFS)}")
    print(f"  Histórico: {MIN_HISTORY_DAYS // 365}+ anos")
    print("=" * 62)

    for symbol in SYMBOLS:
        print(f"\n{'─' * 40}")
        for tf in ALL_TFS:
            since = get_start_time()
            fetch_all_ohlcv(symbol, tf, since)
        print(f"  ─ {symbol} completo")

    print(f"\n{'=' * 62}")
    print(f"  ✅ DATA LAKE CONCLUÍDO!")
    print(f"  📁 Dados em: {os.path.abspath(RAW_DIR)}")
    print(f"{'=' * 62}")

if __name__ == "__main__":
    main()
