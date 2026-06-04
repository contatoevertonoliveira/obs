#!/usr/bin/env python3.12
"""Backtest com modelos treinados em dados Quotex."""
import os, sys, json, warnings
import pandas as pd
import numpy as np
import joblib
warnings.filterwarnings("ignore")

os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.getcwd())

PROC_DIR = "data/processed/quotex"
MODEL_DIR = "models/quotex"

# Setup config
SETUPS = [
    # (ativo, TF, target, threshold, stake%, martingale)
    ("BNB", "M5",  "call_5",  0.70, 2.0, True),
    ("BNB", "M15", "call_5",  0.70, 2.0, True),
    ("BTC", "M5",  "put_1",   0.60, 2.0, True),
]

# Também testar todos os modelos existentes com th=0.5 pra ver WR bruta
TEST_ALL = True

def simulate_trade(balance, stake_pct, payout, won):
    """Simula 1 trade com payout 80%."""
    stake = balance * stake_pct / 100
    if won:
        return balance + stake * payout
    else:
        return balance - stake

def simulate_martingale(balance, stake_pct, payout, won, level, max_level=3):
    """Martingale: 1x -> 2.5x -> 6x."""
    multipliers = [1.0, 2.5, 6.0]
    if level >= len(multipliers):
        level = len(multipliers) - 1
    stake = balance * stake_pct / 100 * multipliers[level]
    if won:
        return balance + stake * payout, 0  # reset level
    else:
        return balance - stake, level + 1

def run_backtest(name, df, model, target_col, threshold, stake_pct, use_martingale):
    """Roda backtest nos ultimos 2 dias do DataFrame."""
    df = df.copy()
    
    # pegar feature names do modelo
    if hasattr(model, "_feat_names"):
        feat_cols = model._feat_names
    elif hasattr(model, "feature_names_in_"):
        feat_cols = list(model.feature_names_in_)
    else:
        feat_cols = [f"f_{i}" for i in range(model.n_features_in_)]
    
    # Filtrar ultimos 2 dias
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    cutoff = df["timestamp"].max() - pd.Timedelta(days=2)
    df_test = df[df["timestamp"] >= cutoff].copy()
    
    if len(df_test) < 10:
        return {"error": "poucos dados"}
    
    # Features
    X = df_test[feat_cols].fillna(0).values
    
    # Predizer
    direction = target_col.split("_")[0]  # call ou put
    y_prob = model.predict_proba(X)[:, 1]
    
    # Se for put, inverter confianca
    if direction == "put":
        confs = 1 - y_prob
    else:
        confs = y_prob
    
    trades = []
    balance = 1000  # capital inicial ficticio
    peak = balance
    martingale_level = 0
    
    for i in range(len(df_test)):
        conf = float(confs[i])
        actual = int(df_test[target_col].iloc[i])
        
        if conf < threshold:
            continue
        
        won = actual == 1
        
        if use_martingale:
            new_balance, martingale_level = simulate_martingale(
                balance, stake_pct, 0.80, won, martingale_level
            )
        else:
            new_balance = simulate_trade(balance, stake_pct, 0.80, won)
        
        trades.append({
            "idx": i,
            "confidence": round(conf, 4),
            "won": won,
            "balance_before": round(balance, 2),
            "balance_after": round(new_balance, 2),
            "martingale_level": martingale_level if use_martingale else 0,
        })
        balance = new_balance
        peak = max(peak, balance)
    
    if not trades:
        return {"trades": 0, "error": "nenhum trade"}
    
    df_trades = pd.DataFrame(trades)
    total = len(df_trades)
    wins = df_trades["won"].sum()
    wr = wins / total
    final_balance = df_trades["balance_after"].iloc[-1]
    profit_pct = (final_balance / 1000 - 1) * 100
    max_dd = (1 - min(t["balance_after"] for t in trades) / peak) * 100
    
    # Estatisticas por nivel de confianca
    levels = {}
    for th in [0.6, 0.7, 0.8, 0.9]:
        mask = df_trades["confidence"] >= th
        if mask.sum() >= 5:
            wr_lvl = df_trades[mask]["won"].mean()
            exp_lvl = wr_lvl * 0.80 - (1 - wr_lvl) * 1
            levels[f"th{th:.1f}"] = {
                "trades": int(mask.sum()),
                "wr": round(float(wr_lvl), 4),
                "exp": round(float(exp_lvl), 4),
            }
    
    return {
        "trades": total,
        "wins": int(wins),
        "losses": total - int(wins),
        "wr": round(float(wr), 4),
        "final_balance": round(float(final_balance), 2),
        "profit_pct": round(float(profit_pct), 2),
        "max_dd": round(float(max_dd), 2),
        "martingale": use_martingale,
        "stake_pct": stake_pct,
        "threshold": threshold,
        "levels": levels,
    }


def main():
    # Carregar resultados do treino
    results_path = f"{MODEL_DIR}/training_results.json"
    if os.path.exists(results_path):
        with open(results_path) as f:
            train_results = json.load(f)
    
    print(f"{'='*65}")
    print("  🧪 BACKTEST - Modelos treinados em dados Quotex")
    print(f"{'='*65}")
    
    # Testar setups especificos
    print(f"\n{'─'*65}")
    print("  📊 SETUPS PRÉ-DEFINIDOS")
    print(f"{'─'*65}")
    
    for name, tf, target, threshold, stake, mg in SETUPS:
        model_name = f"{name}_{tf}_{target}_xgb"
        model_path = f"{MODEL_DIR}/{model_name}.json"
        data_path = f"{PROC_DIR}/{name}_{tf}.csv"
        target_col = f"target_{target}"
        
        if not os.path.exists(model_path):
            print(f"  ⏭️  {name:4s} {tf:4s} {target:10s}: modelo não encontrado")
            continue
        if not os.path.exists(data_path):
            print(f"  ⏭️  {name:4s} {tf:4s} {target:10s}: dados não encontrados")
            continue
        
        model = joblib.load(model_path)
        df = pd.read_csv(data_path)
        
        result = run_backtest(name, df, model, target_col, threshold, stake, mg)
        
        if "error" in result:
            print(f"  ❌ {name:4s} {tf:4s} {target:10s}: {result['error']}")
            continue
        
        status = "✅" if result["wr"] > 0.55 else "⚠️"
        print(f"  {status} {name:4s} {tf:4s} {target:10s}: "
              f"{result['trades']:>4d} trades | WR {result['wr']:.1%} | "
              f"P&L {result['profit_pct']:+.1f}% | DD {result['max_dd']:.1f}%")
        
        if result.get("levels"):
            for lv, ldata in result["levels"].items():
                exp_str = f"exp={ldata['exp']:+.1%}" if ldata["exp"] > 0 else f"exp={ldata['exp']:.1%} ❌"
                print(f"      {lv}: {ldata['trades']:>3d} trades | WR {ldata['wr']:.1%} | {exp_str}")
    
    # Testar TODOS os modelos
    if TEST_ALL:
        print(f"\n{'─'*65}")
        print("  📊 TODOS OS MODELOS (th=0.5)")
        print(f"{'─'*65}")
        
        all_results = []
        models_loaded = 0
        
        for f in sorted(os.listdir(MODEL_DIR)):
            if not f.endswith(".json") or f == "training_results.json":
                continue
            if not f.endswith("_xgb.json"):
                continue
            
            # Parse nome: BNB_M5_call_5_xgb.json
            parts = f.replace("_xgb.json", "").split("_")
            if len(parts) < 3:
                continue
            
            # O nome pode ser BTC_M5_put_1_xgb ou BNB_M15_call_5_xgb
            # Tentar extrair: ativo, TF, target
            name = parts[0]
            tf = parts[1]
            target = "_".join(parts[2:])
            target_col = f"target_{target}"
            data_path = f"{PROC_DIR}/{name}_{tf}.csv"
            
            if not os.path.exists(data_path):
                continue
            
            try:
                model = joblib.load(f"{MODEL_DIR}/{f}")
                df = pd.read_csv(data_path)
                models_loaded += 1
            except:
                continue
            
            result = run_backtest(name, df, model, target_col, 0.50, 1.0, False)
            
            if "error" in result or result["trades"] < 10:
                continue
            
            all_results.append((result["wr"], result["trades"], name, tf, target, result))
        
        # Ordenar por WR
        all_results.sort(reverse=True)
        
        print(f"  {models_loaded} modelos carregados, {len(all_results)} com >=10 trades\n")
        
        for wr, trades, name, tf, target, result in all_results[:20]:
            status = "✅" if wr > 0.55 else "⚠️"
            print(f"  {status} {name:4s} {tf:4s} {target:15s}: WR {wr:.1%} ({trades:>4d} trades) P&L {result['profit_pct']:+.1f}%")
        
        # Melhores com expectativa positiva
        print(f"\n  🏆 MODELOS COM EXPECTATIVA POSITIVA (th=0.5):")
        positive = [(r["profit_pct"], r["wr"], r["trades"], n, tf, tg) 
                    for wr, trades, n, tf, tg, r in all_results 
                    if r["profit_pct"] > 0 and trades >= 10]
        positive.sort(reverse=True)
        
        for profit, wr, trades, name, tf, target in positive[:15]:
            print(f"    {name:4s} {tf:4s} {target:15s}: WR {wr:.1%} ({trades:>4d} trades) P&L {profit:+.1f}%")

if __name__ == "__main__":
    main()
