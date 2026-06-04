#!/usr/bin/env python3
"""Treina ETH (M1/M5/M15) com downsample para evitar OOM."""
import os, sys, json, warnings
warnings.filterwarnings("ignore")
os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ".")

import pandas as pd
import numpy as np
from config.settings import TF_LABEL, PROCESSED_DIR, MODEL_DIR, MIN_CALL_PROB

import xgboost as xgb
from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score
import joblib

SYMBOL = "ETH/USDT"
SHORT = "ETH"

def load_subset(tf, max_rows=None):
    """Carrega dados com downsample opcional."""
    label = TF_LABEL.get(tf, tf)
    path = f"{PROCESSED_DIR}/{SYMBOL.replace('/', '_')}_{label}_features.parquet"
    if not os.path.exists(path):
        print(f"  ⚠ Arquivo não encontrado: {path}")
        return None
    print(f"  📂 Carregando {SHORT} {label}...", end=" ", flush=True)
    df = pd.read_parquet(path)
    print(f"{len(df):,} candles")
    if max_rows and len(df) > max_rows:
        df = df.tail(max_rows)
        print(f"     → Downsample para {max_rows:,} (mais recentes)")
    return df

def prepare_features(df, target_col="target_call"):
    """Prepara features (mesma lógica do ensemble_master)."""
    drop_cols = [
        "timestamp", "datetime", "symbol",
        "target_call", "target_put",
        "target_call_3", "target_put_3",
        "target_call_5", "target_put_5",
        "struct_market",
    ]
    feature_cols = [c for c in df.columns
                    if c not in drop_cols
                    and not c.startswith("target_")
                    and df[c].dtype in ["float64", "float32", "int64", "int32"]]
    X = df[feature_cols].copy()
    y = df[target_col].copy()
    mask = X.isna().any(axis=1) | y.isna()
    X, y = X[~mask], y[~mask]
    if len(X) == 0:
        return None
    split_idx = int(len(X) * 0.8)
    X_train, X_test = X.iloc[:split_idx], X.iloc[split_idx:]
    y_train, y_test = y.iloc[:split_idx], y.iloc[split_idx:]
    val_idx = int(len(X_train) * 0.9)
    X_train, X_val = X_train.iloc[:val_idx], X_train.iloc[val_idx:]
    y_train, y_val = y_train.iloc[:val_idx], y_train.iloc[val_idx:]
    return X_train, X_val, X_test, y_train, y_val, y_test, feature_cols

def train_target(df, tf, target_name, target_col):
    """Treina um target específico."""
    label = TF_LABEL.get(tf, tf)
    result = prepare_features(df, target_col=target_col)
    if result is None:
        return None
    X_train, X_val, X_test, y_train, y_val, y_test, feature_cols = result
    if len(X_train) < 1000:
        return None
    print(f"    {target_name:8s} | Treino: {len(X_train):,} | Val: {len(X_val):,} | Teste: {len(X_test):,}", end=" ", flush=True)
    
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
    
    metrics = {
        "accuracy": float(accuracy_score(y_test, y_pred)),
        "precision": float(precision_score(y_test, y_pred, zero_division=0)),
        "recall": float(recall_score(y_test, y_pred, zero_division=0)),
        "f1": float(f1_score(y_test, y_pred, zero_division=0)),
        "samples": int(len(y_test)),
        "pos_rate": float(y_test.mean()),
    }
    
    print(f"Acc: {metrics['accuracy']:.2%} | Prec: {metrics['precision']:.2%} | Rec: {metrics['recall']:.2%}")
    
    model_path = f"{MODEL_DIR}/{SYMBOL.replace('/', '_')}_{label}_{target_name}_xgb.json"
    joblib.dump(model, model_path)
    print(f"      💾 Salvo: {model_path}")
    
    return {"target": target_name, "model": "xgboost", "metrics": metrics}

def train_eth():
    print("=" * 60)
    print("  🧠 TREINANDO ETH — XGBoost Ensemble")
    print("=" * 60)
    
    configs = [
        ("1m", 200_000),
        ("5m", None),   # 314k — cabe na RAM
        ("15m", None),  # 104k — cabe na RAM
    ]
    
    for tf, max_rows in configs:
        label = TF_LABEL.get(tf, tf)
        print(f"\n{'─' * 40}")
        print(f"  🎯 {SHORT} {label} (M{label})")
        print(f"{'─' * 40}")
        
        df = load_subset(tf, max_rows)
        if df is None:
            continue
        
        results = {}
        for t_name, t_col in [
            ("call_1", "target_call"),
            ("put_1", "target_put"),
            ("call_5", "target_call_5"),
            ("put_5", "target_put_5"),
        ]:
            result = train_target(df, tf, t_name, t_col)
            if result:
                results[t_name] = result
        
        # Salvar relatório
        report = {
            "symbol": SYMBOL,
            "timeframe": tf,
            "results": results,
        }
        report_path = f"{MODEL_DIR}/{SYMBOL.replace('/', '_')}_{label}_report.json"
        with open(report_path, "w") as f:
            json.dump(report, f, indent=2, default=str)
        print(f"  ✅ {SHORT} {label} → Relatório salvo")
    
    print(f"\n{'=' * 60}")
    print(f"  ✅ ETH TREINADO COM SUCESSO!")
    print(f"{'=' * 60}")

if __name__ == "__main__":
    train_eth()
