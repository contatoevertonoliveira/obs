#!/usr/bin/env python3.12
"""Treina modelos XGBoost V2 com dados Quotex calibrados."""
import os, sys, json, warnings, time
import pandas as pd
import numpy as np
import joblib
import xgboost as xgb
from sklearn.metrics import accuracy_score
warnings.filterwarnings("ignore")

os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.getcwd())

PROC_DIR = "data/processed/quotex_v2"
MODEL_DIR = "models/quotex_v2"
os.makedirs(MODEL_DIR, exist_ok=True)

EXCLUDE = {"symbol_id","timestamp","open","high","low","close","volume","last_tick","asset"}
TARGETS = ["target_call_1","target_put_1","target_call_5","target_put_5"]

def get_features(df):
    return [c for c in df.columns if c not in EXCLUDE and c not in TARGETS]

def train_one(X_train, y_train, X_val, y_val):
    """Treina 1 modelo XGBoost."""
    neg = (y_train == 0).sum()
    pos = (y_train == 1).sum()
    scale = neg / max(pos, 1)
    
    model = xgb.XGBClassifier(
        n_estimators=200, max_depth=5, learning_rate=0.05,
        subsample=0.8, colsample_bytree=0.8,
        scale_pos_weight=scale,
        eval_metric="logloss", use_label_encoder=False, verbosity=0,
    )
    model.fit(X_train, y_train, eval_set=[(X_val, y_val)], verbose=False)
    
    y_prob = model.predict_proba(X_val)[:, 1]
    y_pred = model.predict(X_val)
    acc = accuracy_score(y_val, y_pred)
    
    metrics = {"accuracy": float(acc)}
    for th in [0.5, 0.6, 0.7, 0.8]:
        mask = y_prob >= th
        if mask.sum() >= 5:
            wr = (y_val[mask] == 1).mean()
            exp = wr * 0.80 - (1 - wr) * 1
            metrics[f"wr_th{th:.1f}"] = float(wr)
            metrics[f"trades_th{th:.1f}"] = int(mask.sum())
            metrics[f"exp_th{th:.1f}"] = float(exp)
        else:
            metrics[f"wr_th{th:.1f}"] = 0.0
            metrics[f"trades_th{th:.1f}"] = 0
            metrics[f"exp_th{th:.1f}"] = -1.0
    
    return model, metrics

def main():
    files = sorted([f for f in os.listdir(PROC_DIR) if f.endswith(".csv") and f != "summary.json"])
    
    print(f"{'='*65}")
    print(f"  🧠 TREINO V2 - {len(files)} arquivos × 4 targets")
    print(f"  {datetime.now().strftime('%d/%m/%Y %H:%M')} UTC")
    print(f"{'='*65}")
    
    results = {}
    total_models = 0
    viable_models = 0
    skipped_low = 0
    
    for idx, fname in enumerate(files, 1):
        base = fname.replace(".csv", "")
        parts = base.split("_")
        tf = parts[-1]
        name = "_".join(parts[:-1])
        
        df = pd.read_csv(f"{PROC_DIR}/{fname}")
        feat_cols = get_features(df)
        
        valid_targets = []
        for t in TARGETS:
            if t in df.columns and df[t].mean() > 0.01:  # pelo menos 1% de ocorrencia
                valid_targets.append(t)
        
        # Split temporal 80/20
        split = int(len(df) * 0.8)
        train_df = df.iloc[:split]
        val_df = df.iloc[split:]
        
        X_train = train_df[feat_cols].values
        X_val = val_df[feat_cols].values
        
        combos = {}
        
        for target in valid_targets:
            y_train = train_df[target].values
            y_val = val_df[target].values
            
            if y_train.sum() < 10 or (1 - y_train).sum() < 10:
                skipped_low += 1
                continue
            
            model, metrics = train_one(X_train, y_train, X_val, y_val)
            model._feat_names = feat_cols
            
            # Salvar
            dir_name = f"{name}_{tf}"
            dir_path = f"{MODEL_DIR}/{dir_name}"
            os.makedirs(dir_path, exist_ok=True)
            
            model_name = target.replace("target_", "")
            model_path = f"{dir_path}/{model_name}.json"
            joblib.dump(model, model_path)
            
            total_models += 1
            
            # Log
            wr70 = metrics.get("exp_th0.7", -1)
            if wr70 > 0:
                status = "✅"
                viable_models += 1
            else:
                status = "⚠️"
            
            print(f"  [{idx:3d}/{len(files)}] {name:10s} {tf:4s} {model_name:10s}: "
                  f"acc={metrics['accuracy']:.1%} | "
                  f"th0.7: WR={metrics.get('wr_th0.7',0):.1%} trades={metrics.get('trades_th0.7',0):>4d} "
                  f"exp={metrics.get('exp_th0.7',0):.1%} {status}")
            
            combos[target] = metrics
        
        if combos:
            results[base] = combos
    
    # Salvar resultados
    with open(f"{MODEL_DIR}/results.json", "w") as f:
        json.dump(results, f, indent=2)
    
    # Resumo final
    print(f"\n{'='*65}")
    print(f"  ✅ TREINO V2 CONCLUIDO!")
    print(f"  📊 {total_models} modelos treinados, {viable_models} viaveis (exp>0 th=0.7)")
    print(f"  📁 {MODEL_DIR}/")
    print(f"{'='*65}")
    
    # TOP 20
    print(f"\n  🏆 TOP 20 MODELOS (th=0.7, exp>0):")
    best = []
    for base, combos in results.items():
        for target, m in combos.items():
            exp = m.get("exp_th0.7", -1)
            if exp > 0 and m.get("trades_th0.7", 0) >= 10:
                best.append((exp, m["wr_th0.7"], m["trades_th0.7"], base, target))
    
    best.sort(reverse=True)
    for exp, wr, trades, base, target in best[:20]:
        model_name = target.replace("target_", "")
        print(f"    {base:20s} {model_name:10s}: WR={wr:.1%} trades={trades:>4d} exp={exp:.1%} ✅")
    
    # POR CATEGORIA
    print(f"\n  📊 RESUMO POR CATEGORIA:")
    cripto = [b for b in results if any(c in b for c in ["BTC","ETH","SOL","LTC","BNB"])]
    forex_major = [b for b in results if any(c in b for c in ["EUR_","JPY_","GBP_","CHF_","CAD_"])]
    forex_cross = [b for b in results if any(c in b for c in ["AUD","NZD","BRL","EURJPY","EURGBP","GBPJPY","EURAUD","EURCAD","GBPAUD","GBPCAD","AUDJPY","CADJPY","CHFJPY","AUDCAD"]) and b not in forex_major]
    normal = [b for b in results if "_N_" in b]
    
    for label, bases in [("CRIPTO", cripto), ("FOREX MAJOR", forex_major), ("FOREX CROSS", forex_cross), ("NORMAL", normal)]:
        models = []
        for b in bases:
            for t, m in results[b].items():
                exp = m.get("exp_th0.7", -1)
                if exp > 0 and m.get("trades_th0.7", 0) >= 10:
                    models.append(m)
        if models:
            wr_medio = np.mean([m["wr_th0.7"] for m in models])
            print(f"    {label:16s}: {len(models)} modelos viaveis | WR medio th0.7 = {wr_medio:.1%}")

if __name__ == "__main__":
    from datetime import datetime as dt
    now = dt.now()
    globals()['datetime'] = dt
    main()
