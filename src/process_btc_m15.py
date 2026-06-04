#!/usr/bin/env python3
"""Pipeline rápido: processar BTC M15 e treinar modelo."""
import os, sys, subprocess, json, warnings
warnings.filterwarnings("ignore")

ROOT = "/root/hermes-quant-v2"
os.chdir(ROOT)
sys.path.insert(0, ROOT)

LOG = "/tmp/pipeline_btc_m15.log"

def log(msg):
    with open(LOG, "a") as f:
        f.write(msg + "\n")
    print(msg, flush=True)

def run(cmd, desc):
    log(f"\n{'='*55}")
    log(f"  ▶ {desc}")
    log(f"  $ {cmd}")
    log(f"{'='*55}")
    r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=600)
    if r.stdout: log(r.stdout[-2000:])
    if r.stderr: log(f"  ⚠ {r.stderr[:500]}")
    if r.returncode != 0:
        log(f"  ❌ Código {r.returncode}")
        return False
    log(f"  ✅ OK")
    return True

# 1. Feature Engineering BTC M15
log("="*55)
log("  🚀 PIPELINE BTC M15")
log("="*55)

raw = "data/raw/BTC_USDT_M15.parquet"
if not os.path.exists(raw):
    log(f"  ❌ {raw} não encontrado")
    exit(1)

# Process features using existing pipeline structure directly
log("\n--- Processando features BTC M15 ---")
import pandas as pd
import numpy as np
from ta.momentum import RSIIndicator, StochasticOscillator
from ta.trend import MACD, EMAIndicator, ADXIndicator, CCIIndicator
from ta.volatility import BollingerBands, AverageTrueRange
from ta.volume import OnBalanceVolumeIndicator

df = pd.read_parquet(raw)
log(f"  📂 {len(df):,} candles brutos")

# Preço base
for c in ["open", "high", "low", "close", "volume"]:
    if c not in df.columns: df[c] = df[c.upper()]

# Returns
df["returns"] = df["close"].pct_change()
df["log_return"] = np.log1p(df["returns"])
df["range_pct"] = (df["high"] - df["low"]) / df["close"]
df["body_pct"] = abs(df["close"] - df["open"]) / (df["high"] - df["low"] + 1e-10)

# EMAs
for p in [7, 14, 21, 50, 100, 200]:
    df[f"ema_{p}"] = EMAIndicator(df["close"], p).ema_indicator()
    df[f"dist_ema_{p}"] = (df["close"] - df[f"ema_{p}"]) / df[f"ema_{p}"]

# RSI
for p in [7, 14, 21]:
    df[f"rsi_{p}"] = RSIIndicator(df["close"], p).rsi()

# MACD
macd = MACD(df["close"])
df["macd"] = macd.macd()
df["macd_signal"] = macd.macd_signal()
df["macd_diff"] = macd.macd_diff()

# BB
bb = BollingerBands(df["close"])
df["bb_high"] = bb.bollinger_hband()
df["bb_low"] = bb.bollinger_lband()
df["bb_width"] = (df["bb_high"] - df["bb_low"]) / df["close"]
df["bb_pos"] = (df["close"] - df["bb_low"]) / (df["bb_high"] - df["bb_low"] + 1e-10)

# ATR
atr = AverageTrueRange(df["high"], df["low"], df["close"])
df["atr"] = atr.average_true_range()
df["atr_pct"] = df["atr"] / df["close"]

# ADX
adx = ADXIndicator(df["high"], df["low"], df["close"])
df["adx"] = adx.adx()
df["plus_di"] = adx.adx_pos()
df["minus_di"] = adx.adx_neg()
df["di_spread"] = abs(df["plus_di"] - df["minus_di"])

# CCI
for p in [14, 20]:
    df[f"cci_{p}"] = CCIIndicator(df["high"], df["low"], df["close"], p).cci()

# Stochastic
stoch = StochasticOscillator(df["high"], df["low"], df["close"])
df["stoch_k"] = stoch.stoch()
df["stoch_d"] = stoch.stoch_signal()

# Volume
df["volume_sma"] = df["volume"].rolling(20).mean()
df["vol_ratio"] = df["volume"] / (df["volume_sma"] + 1e-10)
df["obv"] = OnBalanceVolumeIndicator(df["close"], df["volume"]).on_balance_volume()

# Targets
spread = 0.0015
df["target_call"] = ((df["close"].shift(-1) - df["close"]) / df["close"] > spread).astype(int)
df["target_put"] = ((df["close"] - df["close"].shift(-1)) / df["close"] > spread).astype(int)
df["target_call_5"] = ((df["close"].shift(-5) - df["close"]) / df["close"] > spread * 1.5).astype(int)
df["target_put_5"] = ((df["close"] - df["close"].shift(-5)) / df["close"] > spread * 1.5).astype(int)

# Drop NaN
drop_cols = [c for c in df.columns if c.startswith(("rsi_", "ema_", "macd", "bb_", "atr", "adx", "cci_", "stoch_"))]
df = df.dropna(subset=drop_cols).copy()
log(f"  ⚙️  {len(df):,} candles | {len(df.columns)} cols | Features OK")

# ── PADRÕES ──
log(f"  🕯️  Padrões candlestick...")
import sys
sys.stdout.flush()
prev = df.shift(1)
df["pat_doji"] = (abs(df["close"] - df["open"]) <= (df["high"] - df["low"]) * 0.1).astype(int)
body = abs(df["close"] - df["open"])
wick = df["high"] - df["low"]
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
df["pat_harami"] = ((abs(df["close"] - df["open"]) < abs(prev["close"] - prev["open"]) * 0.5) & 
                    (df["open"] < prev["close"]) & (df["close"] > prev["open"])).astype(int)
log(f"✅ 23 padrões")

# ── ESTRUTURA ──
log(f"  🏗️  Features estruturais...")
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
log(f"✅ 32 estruturais")

# Estrutura de mercado
df["symbol"] = "BTC/USDT"
df["struct_market"] = np.select(
    [(df["trend_direction"] == 1) & (df["high_vol"] == 1),
     (df["trend_direction"] == -1) & (df["high_vol"] == 1),
     (df["trend_direction"] == 1) & (df["low_vol"] == 1),
     (df["trend_direction"] == -1) & (df["low_vol"] == 1)],
    ["bull_high", "bear_high", "bull_low", "bear_low"],
    default="range"
)

# Salvar
out_path = "data/processed/BTC_USDT_M15_features.parquet"
df.to_parquet(out_path, index=False)
log(f"  💾 Salvo: {out_path}")

# ── 2. TREINAR MODELO ──
log(f"\n{'='*55}")
log(f"  🧠 TREINANDO BTC M15")
log(f"{'='*55}")

import xgboost as xgb
import joblib
from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score
from config.settings import TF_LABEL, MODEL_DIR, PROCESSED_DIR

df = pd.read_parquet(out_path)
log(f"  📂 {len(df):,} candles carregados")

# Prepare features
drop_cols = ["timestamp", "datetime", "symbol",
             "target_call", "target_put",
             "target_call_3", "target_put_3",
             "target_call_5", "target_put_5",
             "struct_market"]
feature_cols = [c for c in df.columns
                if c not in drop_cols
                and not c.startswith("target_")
                and df[c].dtype in ["float64", "float32", "int64", "int32"]]
log(f"  Features: {len(feature_cols)}")

SYMBOL = "BTC/USDT"
targets = [("call_1", "target_call"), ("put_1", "target_put"),
           ("call_5", "target_call_5"), ("put_5", "target_put_5")]
results = {}

for t_name, t_col in targets:
    X = df[feature_cols].copy()
    y = df[t_col].copy()
    mask = X.isna().any(axis=1) | y.isna()
    X, y = X[~mask], y[~mask]
    
    if len(X) < 5000: continue
    
    split = int(len(X) * 0.8)
    X_train, X_test = X.iloc[:split], X.iloc[split:]
    y_train, y_test = y.iloc[:split], y.iloc[split:]
    val_idx = int(len(X_train) * 0.9)
    X_val, y_val = X_train.iloc[val_idx:], y_train.iloc[val_idx:]
    X_train = X_train.iloc[:val_idx]
    y_train = y_train.iloc[:val_idx]
    
    log(f"    {t_name:8s} | Treino: {len(X_train):,} | Val: {len(X_val):,} | Teste: {len(X_test):,}")
    
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
    
    log(f"Acc: {acc:.2%} | Prec: {prec:.2%} | Rec: {rec:.2%}")
    
    path = f"{MODEL_DIR}/BTC_USDT_M15_{t_name}_xgb.json"
    joblib.dump(model, path)
    log(f"      💾 Salvo: {os.path.basename(path)}")
    
    results[t_name] = {"target": t_name, "metrics": {"accuracy": acc, "precision": prec, "recall": rec, "samples": len(y_test)}}

# Save report
report = {"symbol": SYMBOL, "timeframe": "15m", "results": results}
with open(f"{MODEL_DIR}/BTC_USDT_M15_report.json", "w") as f:
    json.dump(report, f, indent=2, default=str)
log(f"  ✅ BTC M15 treinado!")

# ── 3. BACKTEST BTC M15 ──
log(f"\n{'='*55}")
log(f"  🧪 BACKTEST BTC M15")
log(f"{'='*55}")
log(f"  Payout: 80% | Threshold: 0.78")

MIN_CONF = 0.78
PAYOUT = 0.80

df_test = df.iloc[split:].copy()
models = {}
for t_name, _ in targets:
    path = f"{MODEL_DIR}/BTC_USDT_M15_{t_name}_xgb.json"
    if os.path.exists(path):
        models[t_name] = joblib.load(path)

trades = []
for i in range(len(df_test)):
    best_conf, best_trade = 0, None
    row = df_test.iloc[i]
    X_row = pd.DataFrame([row[feature_cols]])
    
    for m_key, model in models.items():
        target_dir = "call" if "call" in m_key else "put"
        target_col = dict(targets)[m_key]
        conf = float(model.predict_proba(X_row)[0, 1])
        
        if conf < MIN_CONF or conf <= best_conf:
            continue
        
        actual = int(row[target_col]) if target_col in df_test.columns else 0
        best_conf = conf
        best_trade = {
            "type": target_dir.upper(), "confidence": conf,
            "actual": actual, "won": actual == 1
        }
    
    if best_trade:
        trades.append(best_trade)

if trades:
    df_t = pd.DataFrame(trades)
    wr = df_t["won"].mean()
    exp = (wr * PAYOUT) - ((1 - wr) * 1)
    log(f"  📊 {len(trades)} trades | WR {wr:.1%} | Exp {exp:.2%} | {'✅' if exp > 0 else '❌'}")
    
    for regime in df_t["type"].unique():
        g = df_t[df_t["type"] == regime]
        w = g["won"].mean()
        log(f"    {regime:4s}: {len(g)} trades | WR {w:.1%}")
else:
    log(f"  ⚠ Nenhum trade gerado (threshold {MIN_CONF})")

log(f"\n{'='*55}")
log(f"  ✅ PIPELINE BTC M15 CONCLUÍDO")
log(f"  📁 Relatório: models/BTC_USDT_M15_report.json")
log(f"{'='*55}")
