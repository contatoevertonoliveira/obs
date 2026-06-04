#!/usr/bin/env python3.12
"""Backtest Quotex — dados reais vs modelos treinados (2 dias)."""
import os, sys, asyncio, json, warnings
from datetime import datetime
warnings.filterwarnings("ignore")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
import pandas as pd
import joblib
from ta.momentum import RSIIndicator
from ta.trend import MACD, EMAIndicator, ADXIndicator
from ta.volatility import BollingerBands, AverageTrueRange

# ═══════════════════════════════════════════════
QUOTEX_EMAIL = os.environ.get("QUOTEX_EMAIL", "")
QUOTEX_PASSWORD = os.environ.get("QUOTEX_PASSWORD", "")

ASSET_MAP = {"BTC/USDT": "BTCUSD_otc", "ETH/USDT": "ETHUSD_otc"}
TF_PERIOD = {"1m": 60, "5m": 300, "15m": 900}
TF_LABEL = {"1m": "M1", "5m": "M5", "15m": "M15", "3m": "M3", "30m": "M30"}

# Features comuns que podemos calcular
FEATURES = {
    "open": lambda df: df["open"], "high": lambda df: df["high"],
    "low": lambda df: df["low"], "close": lambda df: df["close"],
    "volume": lambda df: df.get("volume", df.get("ticks", 0)),
    "return_1": lambda df: df["close"].pct_change(),
    "return_5": lambda df: df["close"].pct_change(5),
    "return_10": lambda df: df["close"].pct_change(10),
    "range": lambda df: (df["high"] - df["low"]) / df["close"],
    "body": lambda df: abs(df["close"] - df["open"]) / (df["high"] - df["low"] + 1e-10),
    "upper_shadow": lambda df: (df["high"] - np.maximum(df["open"], df["close"])) / (df["high"] - df["low"] + 1e-10),
    "lower_shadow": lambda df: (np.minimum(df["open"], df["close"]) - df["low"]) / (df["high"] - df["low"] + 1e-10),
    "rsi": lambda df: RSIIndicator(df["close"], 14).rsi(),
    "macd": lambda df: MACD(df["close"]).macd(),
    "macd_signal": lambda df: MACD(df["close"]).macd_signal(),
    "macd_hist": lambda df: MACD(df["close"]).macd_diff(),
    "bb_width": lambda df: (BollingerBands(df["close"]).bollinger_hband() - BollingerBands(df["close"]).bollinger_lband()) / df["close"],
    "atr": lambda df: AverageTrueRange(df["high"], df["low"], df["close"]).average_true_range(),
    "atr_pct": lambda df: AverageTrueRange(df["high"], df["low"], df["close"]).average_true_range() / df["close"],
    "adx": lambda df: ADXIndicator(df["high"], df["low"], df["close"]).adx(),
    "plus_di": lambda df: ADXIndicator(df["high"], df["low"], df["close"]).adx_pos(),
    "minus_di": lambda df: ADXIndicator(df["high"], df["low"], df["close"]).adx_neg(),
}

def compute_required_features(df, required_cols):
    """Calcula features que o modelo precisa, preenche faltantes com 0."""
    for col in required_cols:
        if col in df.columns:
            continue
        if col.startswith("ema_") and not col.startswith("dist_"):
            parts = col.split("_")
            if len(parts) >= 2 and parts[-1].isdigit():
                period = int(parts[-1])
                df[f"ema_{period}"] = EMAIndicator(df["close"], period).ema_indicator()
            if col.endswith("_slope"):
                base_col = "_".join(parts[:-1])
                if base_col in df.columns:
                    df[col] = df[base_col].diff(5)
                else:
                    df[col] = 0.0
            elif col in df.columns:
                pass
            else:
                df[col] = df.get(f"ema_{period}", 0.0) if 'period' in locals() else 0.0
        elif col.startswith("dist_ema_"):
            period = int(col.split("_")[-1])
            ema = EMAIndicator(df["close"], period).ema_indicator()
            df[col] = (df["close"] - ema) / ema
        elif col in FEATURES:
            try: df[col] = FEATURES[col](df)
            except: df[col] = 0.0
        else:
            df[col] = 0.0

async def run():
    from pyquotex.stable_api import Quotex
    from config.settings import MODEL_DIR
    
    client = Quotex(email=QUOTEX_EMAIL, password=QUOTEX_PASSWORD, lang="pt")
    await client.connect()
    balance = await client.get_balance()
    
    print(f"\n{'='*60}")
    print(f"  🧪 BACKTEST QUOTEX")
    print(f"  {datetime.now().strftime('%d/%m/%Y %H:%M')} UTC")
    print(f"  💰 Saldo DEMO: R$ {balance:.2f}")
    print(f"{'='*60}")
    
    setups = [
        ("BTC/USDT", "1m", 0.70),
        ("ETH/USDT", "5m", 0.65),
        ("BTC/USDT", "15m", 0.82),
    ]
    
    for symbol, tf, threshold in setups:
        period = TF_PERIOD.get(tf, 60)
        asset = ASSET_MAP.get(symbol, f"{symbol.split('/')[0]}USD_otc")
        label = TF_LABEL.get(tf, tf.upper())
        sym_key = symbol.replace("/", "_")
        
        # Carregar modelos
        models_loaded = {}
        for tgt in ["call_1", "put_1", "call_5", "put_5"]:
            mp = f"{MODEL_DIR}/{sym_key}_{label}_{tgt}_xgb.json"
            if os.path.exists(mp):
                try: models_loaded[tgt] = joblib.load(mp)
                except: pass
        
        if not models_loaded:
            print(f"\n  ⏭️  {symbol:10s} {label:4s} | sem modelos")
            continue
        
        # Pegar feature names do primeiro modelo
        sample_model = list(models_loaded.values())[0]
        if hasattr(sample_model, "feature_names_in_"):
            required_cols = list(sample_model.feature_names_in_)
        else:
            required_cols = [f"f_{i}" for i in range(sample_model.n_features_in_)]
        
        print(f"\n  📥 {symbol:10s} {label:4s} (48h)...", end=" ", flush=True)
        
        try:
            candles = await client.get_historical_candles(
                asset, amount_of_seconds=172800, period=period, max_workers=5
            )
        except Exception as e:
            print(f"❌ {e}")
            continue
        
        if not candles or len(candles) < 50:
            print("❌ dados insuficientes")
            continue
        
        print(f"{len(candles)} candles")
        
        # DataFrame
        df = pd.DataFrame(candles)
        df.rename(columns={"time": "timestamp", "ticks": "volume"}, inplace=True)
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="s")
        df = df.sort_values("timestamp").reset_index(drop=True)
        
        # Targets
        spreads = {"1m": 0.0005, "5m": 0.0010, "15m": 0.0015}
        spread = spreads.get(tf, 0.001)
        df["target_call"] = ((df["close"].shift(-1) - df["close"]) / df["close"] > spread).astype(int)
        df["target_put"] = ((df["close"] - df["close"].shift(-1)) / df["close"] > spread).astype(int)
        
        # Computar features que o modelo precisa
        compute_required_features(df, required_cols)
        
        # Remover NaN
        df = df.dropna(subset=required_cols[:20]).copy() if len(required_cols) > 20 else df
        
        if len(df) < 20:
            print("  ⚠ poucos dados após limpeza")
            continue
        
        # Predizer
        results = []
        X = df[required_cols].fillna(0).values
        
        for mk, model in models_loaded.items():
            td = "call" if "call" in mk else "put"
            tc = f"target_{td}"
            if tc not in df.columns:
                continue
            
            y_prob = model.predict_proba(X)[:, 1]
            confs = y_prob if td == "call" else (1 - y_prob)
            
            for i in range(len(df)):
                conf = float(confs[i])
                if conf < threshold:
                    continue
                results.append({
                    "type": td.upper(), "confidence": conf,
                    "model": mk,
                    "actual": int(df[tc].iloc[i]),
                    "won": bool(int(df[tc].iloc[i]) == 1),
                })
        
        if not results:
            print(f"  📊 {symbol:10s} {label:4s} | 0 trades (th={threshold})")
            continue
        
        df_r = pd.DataFrame(results)
        total = len(df_r)
        wins = df_r["won"].sum()
        wr = wins / total
        payout = 0.80
        exp = (wr * payout) - ((1 - wr) * 1)
        
        print(f"  📊 {total:>5d} trades | WR {wr:.1%} | Exp {exp:.2%} | {'✅' if exp > 0 else '❌'}")
        for mk, g in df_r.groupby("model"):
            g_wr = g["won"].mean()
            g_exp = (g_wr * payout) - ((1 - g_wr) * 1)
            print(f"      {mk:10s}: {len(g):>4d} trades | WR {g_wr:.1%} | Exp {g_exp:.2%}")
    
    await client.close()
    print(f"\n  ✅ BACKTEST QUOTEX CONCLUÍDO!")

if __name__ == "__main__":
    asyncio.run(run())
