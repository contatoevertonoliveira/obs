#!/usr/bin/env python3
"""Backtest com Martingale real — Hermes Quant V2."""
import os, sys, json, warnings
warnings.filterwarnings("ignore")
os.chdir("/root/hermes-quant-v2")
sys.path.insert(0, ".")

import pandas as pd
import numpy as np
import joblib
from config.settings import TF_LABEL, PROCESSED_DIR, MODEL_DIR, PAYOUT_RATE
from src.market_regime import classify_regime, load_regime_performance_cache

SYMBOLS = ["BTC/USDT", "ETH/USDT"]
TFS = ["1m", "5m", "15m"]
MODEL_TARGET_MAP = {"call_1": "target_call", "put_1": "target_put",
                    "call_5": "target_call_5", "put_5": "target_put_5"}

# ═══════════════════════════════════════════════════════
# PARÂMETROS MARTINGALE
# ═══════════════════════════════════════════════════════
BASE_STAKE_PCT = 0.02          # 2% do saldo
MARTINGALE_MULT = [1.0, 2.5, 6.0]  # níveis: 1x, 2.5x, 6x
MAX_MG_LEVELS = 2              # 2 níveis de martingale
INITIAL_CAPITAL = 100.0
MIN_CONF_M1 = 0.85             # Threshold mínimo M1
MIN_CONF_M5 = 0.82             # Threshold mínimo M5
MIN_CONF_M15 = 0.78            # Threshold mínimo M15

TFS_LIST = [
    ("1m",  200_000, 0.88),   # BTC M1 threshold original
    ("5m",  200_000, 0.85),   # Original BTC M5
    ("15m", None,    0.82),   # Original M15
]

def load_data(symbol, tf, max_rows=None):
    label = TF_LABEL.get(tf, tf)
    path = f"{PROCESSED_DIR}/{symbol.replace('/', '_')}_{label}_features.parquet"
    if not os.path.exists(path):
        return None
    df = pd.read_parquet(path)
    if max_rows and len(df) > max_rows:
        df = df.tail(max_rows)
    return df

def load_models(symbol, tf):
    label = TF_LABEL.get(tf, tf)
    models = {}
    for target in ["call_1", "put_1", "call_5", "put_5"]:
        path = f"{MODEL_DIR}/{symbol.replace('/', '_')}_{label}_{target}_xgb.json"
        if os.path.exists(path):
            models[target] = joblib.load(path)
    return models

def compute_martingale_stake(balance, level):
    """Calcula stake no nível martingale atual.
    level=0: base stake (2%)
    level=1: 2.5x  (recupera loss + lucro)
    level=2: 6.0x  (recupera loss anterior + atual)
    """
    base = balance * BASE_STAKE_PCT
    mult = MARTINGALE_MULT[min(level, len(MARTINGALE_MULT) - 1)]
    return round(base * mult, 2), base

def backtest_martingale(symbol, tf_info):
    tf, max_rows, min_conf = tf_info
    label = TF_LABEL.get(tf, tf)
    symbol_short = symbol.replace("/USDT", "")
    
    df = load_data(symbol, tf, max_rows)
    models = load_models(symbol, tf)
    if df is None or not models:
        return None
    
    # Features
    drop_cols = ["timestamp", "datetime", "symbol",
                 "target_call", "target_put",
                 "target_call_3", "target_put_3",
                 "target_call_5", "target_put_5", "struct_market"]
    feature_cols = [c for c in df.columns
                    if c not in drop_cols
                    and not c.startswith("target_")
                    and df[c].dtype in ["float64", "float32", "int64", "int32"]]
    
    X = df[feature_cols].copy()
    mask = X.isna().any(axis=1)
    X = X[~mask]
    df_clean = df[~mask].copy()
    
    if len(X) < 5000:
        return None
    
    split = int(len(X) * 0.8)
    X_test = X.iloc[split:]
    df_test = df_clean.iloc[split:].copy()
    n_test = len(X_test)
    
    print(f"\n{'─' * 55}")
    print(f"  🎯 {symbol:10s} {label:4s} | {n_test:,} candles teste")
    print(f"{'─' * 55}")
    
    # Batch predict
    preds = {}
    for key, model in models.items():
        preds[key] = model.predict_proba(X_test)[:, 1]
    
    # Simulate trading with martingale
    balance_flat = INITIAL_CAPITAL
    balance_mg = INITIAL_CAPITAL
    mg_level = 0
    mg_active = False  # True when we're in a martingale recovery sequence
    consecutive_losses = 0
    
    trades_flat = []
    trades_mg = []
    
    regime_name = "nosignal"
    
    for i in range(n_test):
        best_conf, best_trade = 0, None
        
        for model_key in models:
            target_dir = "call" if "call" in model_key else "put"
            conf = float(preds[model_key][i])
            
            # Dynamic threshold based on balance remaining
            if conf < min_conf:
                continue
            if conf <= best_conf:
                continue
            
            target_col = MODEL_TARGET_MAP[model_key]
            actual = int(df_test[target_col].iloc[i]) if target_col in df_test.columns else 0
            
            # MRD every 10 candles
            if i % 10 == 0:
                window = df_clean.iloc[:split + i]
                regime = classify_regime(window)
                regime_name = regime["regime"]
            elif trades_flat:
                regime_name = trades_flat[-1]["regime"]
            
            best_conf = conf
            best_trade = {
                "timestamp": int(df_test["timestamp"].iloc[i]),
                "type": target_dir.upper(),
                "confidence": conf,
                "regime": regime_name,
                "actual": actual,
                "won": actual == 1,
            }
        
        if best_trade is None:
            continue
        
        won = best_trade["won"]
        
        # ── FLAT (sem martingale) ──
        stake_flat = round(balance_flat * BASE_STAKE_PCT, 2)
        profit_flat = round(stake_flat * PAYOUT_RATE, 2) if won else -stake_flat
        balance_flat = round(balance_flat + profit_flat, 2)
        trades_flat.append({**best_trade, "stake": stake_flat, "profit": profit_flat, "balance": balance_flat, "mg_level": 0})
        
        # ── COM MARTINGALE ──
        # Compute stake FIRST, using current mg_level BEFORE updating state
        stake_mg, base = compute_martingale_stake(balance_mg, mg_level if mg_active else 0)
        stake_mg = min(stake_mg, balance_mg * 0.5)  # Cap at 50% of balance
        stake_mg = max(stake_mg, 0.50)  # Min stake R$0.50
        stake_mg = round(stake_mg, 2)
        if stake_mg > balance_mg:
            stake_mg = balance_mg
        
        profit_mg = round(stake_mg * PAYOUT_RATE, 2) if won else -stake_mg
        balance_mg = round(balance_mg + profit_mg, 2)
        
        # Record trade with current mg state BEFORE updating
        current_mg_level = mg_level if mg_active else 0
        current_mg_active = mg_active
        
        # THEN update martingale state for NEXT trade
        if mg_active and won:
            mg_level = 0; mg_active = False; consecutive_losses = 0
        elif mg_active and not won:
            consecutive_losses += 1
            if consecutive_losses >= MAX_MG_LEVELS:
                mg_level = 0; mg_active = False; consecutive_losses = 0
            else:
                mg_level = consecutive_losses
        elif not mg_active and won:
            mg_level = 0; consecutive_losses = 0
        elif not mg_active and not won:
            mg_active = True; mg_level = 1; consecutive_losses = 1
        
        trades_mg.append({**best_trade, "stake": stake_mg, "profit": profit_mg, 
                          "balance": balance_mg, "mg_level": current_mg_level,
                          "mg_active": current_mg_active})
    
    if not trades_flat:
        return None
    
    # MÉTRICAS
    df_f = pd.DataFrame(trades_flat)
    df_m = pd.DataFrame(trades_mg)
    
    wins_f = df_f["won"].sum()
    total_f = len(df_f)
    wr_f = wins_f / total_f
    exp_f = (wr_f * PAYOUT_RATE) - ((1 - wr_f) * 1)
    final_f = trades_flat[-1]["balance"]
    profit_f = final_f - INITIAL_CAPITAL
    
    wins_m = df_m["won"].sum()
    total_m = len(df_m)
    wr_m = wins_m / total_m
    final_m = trades_mg[-1]["balance"]
    profit_m = final_m - INITIAL_CAPITAL
    
    # Martingale stats
    mg_trades = df_m[df_m["mg_active"] == True]
    mg_wins = mg_trades["won"].sum() if len(mg_trades) > 0 else 0
    mg_total = len(mg_trades)
    
    # Summary
    icon = "✅" if profit_m > profit_f else "⚠️"
    
    print(f"  📊 Trades: {total_f}")
    print(f"  💰 FLAT:    R$ {INITIAL_CAPITAL:.2f} → R$ {final_f:.2f} ({profit_f:+.2f}) WR {wr_f:.1%} Exp {exp_f:.2%}")
    print(f"  💰 MARTINGALE: R$ {INITIAL_CAPITAL:.2f} → R$ {final_m:.2f} ({profit_m:+.2f}) WR {wr_m:.1%} {icon}")
    print(f"  📈 Melhora: R$ {profit_m - profit_f:+.2f}")
    
    if mg_total > 0:
        mg_wr = mg_wins / mg_total
        max_lvl = df_m["mg_level"].max()
        print(f"  🎲 Martingale: {mg_total} trades em recuperação | WR {mg_wr:.1%} | max nível {int(max_lvl)}")
        
        # Per level breakdown
        for level in range(int(max_lvl) + 1):
            lvl_trades = df_m[df_m["mg_level"] == level]
            if len(lvl_trades) == 0:
                continue
            lvl_wins = lvl_trades["won"].sum()
            print(f"     Nível {level} ({MARTINGALE_MULT[level]}x): {len(lvl_trades)} trades | {lvl_wins} wins | WR {lvl_wins/len(lvl_trades):.1%}")
    
    return {
        "symbol": symbol, "tf": tf,
        "trades": total_f,
        "win_rate": wr_f,
        "final_flat": final_f, "profit_flat": profit_f,
        "final_mg": final_m, "profit_mg": profit_m,
        "improvement": profit_m - profit_f,
        "mg_trades": mg_total, "mg_wr": wins_m / max(total_m, 1),
    }

print("=" * 55)
print("  🧪 BACKTEST MARTINGALE — HERMES QUANT V2")
print("=" * 55)
print(f"  Capital: R$ {INITIAL_CAPITAL:.2f}")
print(f"  Stake base: {BASE_STAKE_PCT:.0%} do saldo")
print(f"  Martingale níveis: {MARTINGALE_MULT}")  
print(f"  Payout: {PAYOUT_RATE:.0%}")
print(f"  Thresholds: M1>{MIN_CONF_M1} M5>{MIN_CONF_M5} M15>{MIN_CONF_M15}")
print("=" * 55)

results = []
for symbol in SYMBOLS:
    for tf_info in TFS_LIST:
        r = backtest_martingale(symbol, tf_info)
        if r:
            results.append(r)

print(f"\n{'=' * 55}")
print(f"  📊 RESUMO — FLAT vs MARTINGALE")
print(f"{'=' * 55}")
print(f"  {'Ativo':10s} {'TF':4s} {'Trades':>6s} {'WR':>6s}  "
      f"{'Flat':>10s} {'Mg':>10s} {'Dif':>8s}  {'Mg W':>6s}")
print(f"  {'─' * 55}")
for r in results:
    icon = "✅" if r["improvement"] > 0 else "❌"
    print(f"  {r['symbol']:10s} {r['tf']:4s} {r['trades']:6d} "
          f"{r['win_rate']:.1%}  "
          f"R${r['profit_flat']:>+7.2f} R${r['profit_mg']:>+7.2f} "
          f"{r['improvement']:>+7.2f} {icon:>6s}")

# Salvar
with open(f"{MODEL_DIR}/backtest_martingale.json", "w") as f:
    json.dump(results, f, indent=2, default=str)
print(f"\n  📁 models/backtest_martingale.json")
