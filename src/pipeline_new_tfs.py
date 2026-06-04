#!/usr/bin/env python3
"""Pipeline completo: Coletar M3/M30 → Processar → Treinar → MRD → Backtest"""
import os, sys, json, subprocess, time, warnings
from datetime import datetime, timezone, timedelta
warnings.filterwarnings("ignore")

ROOT = "/root/hermes-quant-v2"
os.chdir(ROOT)
sys.path.insert(0, ROOT)

LOG = "/tmp/pipeline_tfs.log"
RAW_DIR = "data/raw"

def log(msg):
    with open(LOG, "a") as f:
        f.write(msg + "\n")
    print(msg, flush=True)

# ── 1. COLETA M3 e M30 ──
log("=" * 55)
log("  🚀 PIPELINE: M3 + M15 + M30")
log("=" * 55)

import ccxt
import pandas as pd
import numpy as np

exchange = ccxt.binance({"enableRateLimit": True, "options": {"defaultType": "future"}})

def collect_tf(symbol, tf_name, days=365*2):
    """Coleta dados de um timeframe específico."""
    label_map = {"3m": "M3", "15m": "M15", "30m": "M30"}
    label = label_map.get(tf_name, tf_name.upper())
    sym_key = symbol.replace("/", "_")
    path = f"{RAW_DIR}/{sym_key}_{label}.parquet"
    
    # Check if already collected
    if os.path.exists(path):
        df = pd.read_parquet(path)
        log(f"  📂 {symbol:8s} {label:4s} | {len(df):,} candles (existente)")
        return True
    
    log(f"  📥 Coletando {symbol:8s} {label:4s}...")
    sys.stdout.flush()
    since = int((datetime.now(timezone.utc) - timedelta(days=days)).timestamp() * 1000)
    all_candles = []
    
    try:
        while True:
            candles = exchange.fetch_ohlcv(symbol, tf_name, since=since, limit=1000)
            if not candles:
                break
            all_candles.extend(candles)
            since = candles[-1][0] + 1
            time.sleep(0.3)
            if len(candles) < 1000:
                break
    except Exception as e:
        log(f"Erro: {e}")
        return False
    
    if not all_candles:
        log("sem dados")
        return False
    
    df = pd.DataFrame(all_candles, columns=["timestamp", "open", "high", "low", "close", "volume"])
    df["datetime"] = pd.to_datetime(df["timestamp"], unit="ms")
    df = df.drop_duplicates(subset=["timestamp"]).sort_values("timestamp").reset_index(drop=True)
    
    os.makedirs(RAW_DIR, exist_ok=True)
    df.to_parquet(path, index=False)
    log(f"{len(df):,} candles ✅")
    return True

# Coletar M3 e M30 para BTC e ETH
new_tfs = [("3m", 730), ("30m", 730)]  # (tf, days)
symbols = ["BTC/USDT", "ETH/USDT"]

for symbol in symbols:
    for tf_name, days in new_tfs:
        if not collect_tf(symbol, tf_name, days):
            log(f"  ❌ Falha na coleta {symbol} {tf_name}")

# ── 2. PROCESSAR FEATURES ──
log(f"\n{'='*55}")
log(f"  ⚙️  PROCESSANDO FEATURES")
log(f"{'='*55}")

from ta.momentum import RSIIndicator, StochasticOscillator
from ta.trend import MACD, EMAIndicator, ADXIndicator, CCIIndicator
from ta.volatility import BollingerBands, AverageTrueRange
from ta.volume import OnBalanceVolumeIndicator

PROCESSED_DIR = "data/processed"
os.makedirs(PROCESSED_DIR, exist_ok=True)

SPREADS = {"3m": 0.0008, "15m": 0.0015, "30m": 0.0020}
LABELS = {"3m": "M3", "15m": "M15", "30m": "M30"}

all_tasks = []
# BTC M3, M30 (BTC M15 já processado)
for symbol in symbols:
    for tf in ["3m", "30m"]:
        all_tasks.append((symbol, tf))
# ETH M3, M15, M30 (ETH M5 já existe)
for tf in ["3m", "15m", "30m"]:
    all_tasks.append(("ETH/USDT", tf))

for symbol, tf_name in all_tasks:
    label = LABELS[tf_name]
    sym_key = symbol.replace("/", "_")
    raw_path = f"{RAW_DIR}/{sym_key}_{label}.parquet"
    out_path = f"{PROCESSED_DIR}/{sym_key}_{label}_features.parquet"
    
    if not os.path.exists(raw_path):
        log(f"  ⚠ {sym_key} {label}: raw não encontrado")
        continue
    
    df = pd.read_parquet(raw_path)
    log(f"  📂 {sym_key:8s} {label:4s} | {len(df):,} candles brutos")
    
    # Features técnicas
    for c in ["open", "high", "low", "close", "volume"]:
        if c not in df.columns: df[c] = df[c.upper()]
    
    df["returns"] = df["close"].pct_change()
    df["log_return"] = np.log1p(df["returns"])
    df["range_pct"] = (df["high"] - df["low"]) / df["close"]
    df["body_pct"] = abs(df["close"] - df["open"]) / (df["high"] - df["low"] + 1e-10)
    
    for p in [7, 14, 21, 50, 100, 200]:
        df[f"ema_{p}"] = EMAIndicator(df["close"], p).ema_indicator()
        df[f"dist_ema_{p}"] = (df["close"] - df[f"ema_{p}"]) / df[f"ema_{p}"]
    
    for p in [7, 14, 21]:
        df[f"rsi_{p}"] = RSIIndicator(df["close"], p).rsi()
    
    macd = MACD(df["close"])
    df["macd"] = macd.macd()
    df["macd_signal"] = macd.macd_signal()
    df["macd_diff"] = macd.macd_diff()
    
    bb = BollingerBands(df["close"])
    df["bb_high"] = bb.bollinger_hband()
    df["bb_low"] = bb.bollinger_lband()
    df["bb_width"] = (df["bb_high"] - df["bb_low"]) / df["close"]
    df["bb_pos"] = (df["close"] - df["bb_low"]) / (df["bb_high"] - df["bb_low"] + 1e-10)
    
    atr = AverageTrueRange(df["high"], df["low"], df["close"])
    df["atr"] = atr.average_true_range()
    df["atr_pct"] = df["atr"] / df["close"]
    
    adx = ADXIndicator(df["high"], df["low"], df["close"])
    df["adx"] = adx.adx()
    df["plus_di"] = adx.adx_pos()
    df["minus_di"] = adx.adx_neg()
    df["di_spread"] = abs(df["plus_di"] - df["minus_di"])
    
    for p in [14, 20]:
        df[f"cci_{p}"] = CCIIndicator(df["high"], df["low"], df["close"], p).cci()
    
    stoch = StochasticOscillator(df["high"], df["low"], df["close"])
    df["stoch_k"] = stoch.stoch()
    df["stoch_d"] = stoch.stoch_signal()
    
    df["volume_sma"] = df["volume"].rolling(20).mean()
    df["vol_ratio"] = df["volume"] / (df["volume_sma"] + 1e-10)
    df["obv"] = OnBalanceVolumeIndicator(df["close"], df["volume"]).on_balance_volume()
    
    # Targets
    spread = SPREADS[tf_name]
    df["target_call"] = ((df["close"].shift(-1) - df["close"]) / df["close"] > spread).astype(int)
    df["target_put"] = ((df["close"] - df["close"].shift(-1)) / df["close"] > spread).astype(int)
    df["target_call_5"] = ((df["close"].shift(-5) - df["close"]) / df["close"] > spread * 1.5).astype(int)
    df["target_put_5"] = ((df["close"] - df["close"].shift(-5)) / df["close"] > spread * 1.5).astype(int)
    
    # Drop NaN
    drop_feats = [c for c in df.columns if c.startswith(("rsi_", "ema_", "macd", "bb_", "atr", "adx", "cci_", "stoch_"))]
    before = len(df)
    df = df.dropna(subset=drop_feats).copy()
    
    # Padrões
    prev = df.shift(1)
    body = abs(df["close"] - df["open"])
    wick = df["high"] - df["low"]
    
    df["pat_doji"] = (body <= wick * 0.1).astype(int)
    df["pat_hammer"] = ((np.minimum(df["open"], df["close"]) - df["low"]) >= body * 2).astype(int)
    df["pat_shooting"] = ((df["high"] - np.maximum(df["open"], df["close"])) >= body * 2).astype(int)
    df["pat_marubozu"] = (body >= wick * 0.95).astype(int)
    df["pat_spinning"] = ((body <= wick * 0.3) & 
                          ((df["high"] - np.maximum(df["open"], df["close"])) >= body) &
                          ((np.minimum(df["open"], df["close"]) - df["low"]) >= body)).astype(int)
    df["pat_engulfing"] = ((df["close"] > df["open"]) & (prev["close"] < prev["open"]) & 
                           (df["open"] < prev["close"]) & (df["close"] > prev["open"])).astype(int)
    df["pat_engulfing_bear"] = ((df["close"] < df["open"]) & (prev["close"] > prev["open"]) & 
                                (df["open"] > prev["close"]) & (df["close"] < prev["open"])).astype(int)
    df["pat_harami"] = ((body < abs(prev["close"] - prev["open"]) * 0.5) & 
                        (df["open"] < prev["close"]) & (df["close"] > prev["open"])).astype(int)
    
    # Estrutura
    df["trend_strength"] = df["adx"] / 100
    df["trend_direction"] = np.where(df["plus_di"] > df["minus_di"], 1, -1)
    df["is_uptrend"] = (df["ema_21"] > df["ema_50"]).astype(int)
    df["is_downtrend"] = (df["ema_21"] < df["ema_50"]).astype(int)
    df["ema_aligned"] = ((df["ema_7"] > df["ema_21"]) & (df["ema_21"] > df["ema_50"])).astype(int)
    df["ema_aligned_bear"] = ((df["ema_7"] < df["ema_21"]) & (df["ema_21"] < df["ema_50"])).astype(int)
    df["hh_20"] = df["high"].rolling(20).max()
    df["ll_20"] = df["low"].rolling(20).min()
    df["breakout_high"] = (df["high"] > df["hh_20"].shift(1)).astype(int)
    df["breakout_low"] = (df["low"] < df["ll_20"].shift(1)).astype(int)
    df["pullback_bull"] = ((df["is_uptrend"] == 1) & (df["close"] < df["ema_21"])).astype(int)
    df["pullback_bear"] = ((df["is_downtrend"] == 1) & (df["close"] > df["ema_21"])).astype(int)
    df["vol_ma_20"] = df["atr_pct"].rolling(20).mean()
    df["high_vol"] = (df["atr_pct"] > df["vol_ma_20"] * 1.3).astype(int)
    df["low_vol"] = (df["atr_pct"] < df["vol_ma_20"] * 0.7).astype(int)
    df["momentum_5"] = df["close"].pct_change(5)
    df["momentum_10"] = df["close"].pct_change(10)
    df["roc"] = df["close"].pct_change(periods=14) * 100
    df["sr_dist_res"] = (df["high"] - df["close"]) / (df["high"] - df["low"] + 1e-10)
    df["sr_dist_sup"] = (df["close"] - df["low"]) / (df["high"] - df["low"] + 1e-10)
    df["sqeeze"] = (df["bb_width"] < df["bb_width"].rolling(20).mean()).astype(int)
    
    df["symbol"] = symbol
    df["struct_market"] = np.select(
        [(df["trend_direction"] == 1) & (df["high_vol"] == 1),
         (df["trend_direction"] == -1) & (df["high_vol"] == 1),
         (df["trend_direction"] == 1) & (df["low_vol"] == 1),
         (df["trend_direction"] == -1) & (df["low_vol"] == 1)],
        ["bull_high", "bear_high", "bull_low", "bear_low"],
        default="range"
    )
    
    df.to_parquet(out_path, index=False)
    log(f"  ✅ {sym_key:8s} {label:4s} | {len(df):,} candles | {len(df.columns)} cols")

# ── 3. TREINAR MODELOS ──
log(f"\n{'='*55}")
log(f"  🧠 TREINANDO MODELOS")
log(f"{'='*55}")

import xgboost as xgb
import joblib
from sklearn.metrics import accuracy_score, precision_score, recall_score
from config.settings import MODEL_DIR

MODEL_DIR = "models"
TARGETS = [("call_1", "target_call"), ("put_1", "target_put"),
           ("call_5", "target_call_5"), ("put_5", "target_put_5")]

drop_cols = ["timestamp", "datetime", "symbol", "target_call", "target_put",
             "target_call_3", "target_put_3", "target_call_5", "target_put_5",
             "struct_market"]

for symbol in ["BTC/USDT", "ETH/USDT"]:
    for tf_name in ["3m", "15m", "30m"]:
        label = LABELS[tf_name]
        sym_key = symbol.replace("/", "_")
        feat_path = f"{PROCESSED_DIR}/{sym_key}_{label}_features.parquet"
        
        if not os.path.exists(feat_path):
            log(f"  ⚠ {sym_key} {label}: sem dados processados")
            continue
        
        df = pd.read_parquet(feat_path)
        feature_cols = [c for c in df.columns if c not in drop_cols 
                        and not c.startswith("target_") 
                        and df[c].dtype in ["float64", "float32", "int64", "int32"]]
        
        log(f"  🎯 {sym_key:8s} {label:4s} | {len(df):,} candles | {len(feature_cols)} features")
        
        results = {}
        for t_name, t_col in TARGETS:
            X = df[feature_cols].copy()
            y = df[t_col].copy()
            mask = X.isna().any(axis=1) | y.isna()
            X, y = X[~mask], y[~mask]
            
            if len(X) < 5000:
                continue
            
            split = int(len(X) * 0.8)
            X_train, X_test = X.iloc[:split], X.iloc[split:]
            y_train, y_test = y.iloc[:split], y.iloc[split:]
            val_idx = int(len(X_train) * 0.9)
            X_val, y_val = X_train.iloc[val_idx:], y_train.iloc[val_idx:]
            X_train, y_train = X_train.iloc[:val_idx], y_train.iloc[:val_idx]
            
            model = xgb.XGBClassifier(
                n_estimators=500, max_depth=6, learning_rate=0.05,
                subsample=0.8, colsample_bytree=0.8, min_child_weight=3,
                reg_alpha=0.1, reg_lambda=1.0,
                scale_pos_weight=sum(y_train == 0) / max(sum(y_train == 1), 1),
                random_state=42, n_jobs=-1,
                eval_metric="logloss", early_stopping_rounds=50, verbosity=0,
            )
            model.fit(X_train, y_train, eval_set=[(X_val, y_val)], verbose=False)
            
            y_pred = model.predict(X_test)
            y_prob = model.predict_proba(X_test)[:, 1]
            
            acc = accuracy_score(y_test, y_pred)
            prec = precision_score(y_test, y_pred, zero_division=0)
            rec = recall_score(y_test, y_pred, zero_division=0)
            
            # Quick backtest
            confs = y_prob if "call" in t_name else (1 - y_prob)
            target_direction = "call" if "call" in t_name else "put"
            threshold = 0.70
            trades_found = 0
            trades_won = 0
            for j in range(len(confs)):
                if confs[j] >= threshold:
                    trades_found += 1
                    if y_test.iloc[j] == 1:
                        trades_won += 1
            
            wr = trades_won / trades_found if trades_found > 0 else 0
            exp = (wr * 0.80) - ((1 - wr) * 1)
            
            log(f"    {t_name:8s} | Acc: {acc:.2%} | "
                f"{'✅' if exp > 0 else '❌'} "
                f"WR>0.70: {wr:.1%} ({trades_found} trades) Exp {exp:.2%}")
            
            model_path = f"{MODEL_DIR}/{sym_key}_{label}_{t_name}_xgb.json"
            joblib.dump(model, model_path)
            results[t_name] = {"target": t_name, "metrics": {"accuracy": acc, "precision": prec, "recall": rec}}
        
        report = {"symbol": symbol, "timeframe": tf_name, "results": results}
        with open(f"{MODEL_DIR}/{sym_key}_{label}_report.json", "w") as f:
            json.dump(report, f, indent=2, default=str)
        log(f"  ✅ {sym_key} {label} concluído")

log(f"\n{'='*55}")
log(f"  ✅ PIPELINE CONCLUÍDO!")
log(f"{'='*55}")
log(f"  Relatório: {LOG}")
