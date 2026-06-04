#!/usr/bin/env python3.12
"""Treina modelos XGBoost para todos os ativos+TF da Quotex."""
import os, sys, warnings, json, time
import pandas as pd
import numpy as np
import joblib
import xgboost as xgb
from sklearn.metrics import accuracy_score
warnings.filterwarnings("ignore")

os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.getcwd())

PROC_DIR = "data/processed/quotex"
MODEL_DIR = "models/quotex"
os.makedirs(MODEL_DIR, exist_ok=True)

# Feature columns (excluir metadados e targets)
EXCLUDE = {
    "symbol_id", "timestamp", "open", "high", "low", "close",
    "volume", "last_tick", "asset"
}
TARGETS = ["target_call_1", "target_put_1", "target_call_5", "target_put_5"]

def get_feature_cols(df):
    return [c for c in df.columns if c not in EXCLUDE and c not in TARGETS]

def train_model(X_train, y_train, X_val, y_val, name):
    """Treina XGBoost e retorna modelo + métricas."""
    # Calcular scale_pos_weight para balanceamento
    neg = (y_train == 0).sum()
    pos = (y_train == 1).sum()
    scale = neg / max(pos, 1)
    
    model = xgb.XGBClassifier(
        n_estimators=300,
        max_depth=6,
        learning_rate=0.05,
        subsample=0.8,
        colsample_bytree=0.8,
        scale_pos_weight=scale,
        eval_metric="logloss",
        use_label_encoder=False,
        verbosity=0,
    )
    
    model.fit(
        X_train, y_train,
        eval_set=[(X_val, y_val)],
        verbose=False,
    )
    
    # Métricas
    y_pred = model.predict(X_val)
    y_prob = model.predict_proba(X_val)[:, 1]
    acc = accuracy_score(y_val, y_pred)
    
    # Calcular WR por threshold
    metrics = {"accuracy": float(acc)}
    for th in [0.5, 0.6, 0.7, 0.8, 0.9]:
        mask = y_prob >= th
        if mask.sum() > 0:
            wr = (y_val[mask] == 1).mean()
            metrics[f"wr_th{th:.1f}"] = float(wr)
            metrics[f"trades_th{th:.1f}"] = int(mask.sum())
        else:
            metrics[f"wr_th{th:.1f}"] = 0.0
            metrics[f"trades_th{th:.1f}"] = 0
    
    # Payout simulado 80%
    for th in [0.5, 0.6, 0.7, 0.8, 0.9]:
        mask = y_prob >= th
        if mask.sum() > 0:
            wr = (y_val[mask] == 1).mean()
            exp = (wr * 0.80) - ((1 - wr) * 1)
            metrics[f"exp_th{th:.1f}"] = float(exp)
        else:
            metrics[f"exp_th{th:.1f}"] = -1.0
    
    return model, metrics


def main():
    files = sorted([f for f in os.listdir(PROC_DIR) if f.endswith(".csv")])
    results = {}
    total = len(files)
    
    print(f"{'='*60}")
    print(f"  🧠 TREINANDO MODELOS QUOTEX")
    print(f"  {total} combinações ativo+TF")
    print(f"{'='*60}")
    
    for idx, fname in enumerate(files, 1):
        base = fname.replace(".csv", "")
        print(f"\n[{idx}/{total}] {base}")
        
        df = pd.read_csv(f"{PROC_DIR}/{fname}")
        feat_cols = get_feature_cols(df)
        
        # Split: 80% treino (dados mais antigos), 20% val (mais recentes)
        split = int(len(df) * 0.8)
        train_df = df.iloc[:split]
        val_df = df.iloc[split:]
        
        X_train = train_df[feat_cols].values
        X_val = val_df[feat_cols].values
        
        combos = {}
        
        for target in TARGETS:
            if target not in df.columns:
                continue
            
            y_train = train_df[target].values
            y_val = val_df[target].values
            
            # Pular targets com pouca variação
            if y_train.sum() < 10 or (1 - y_train).sum() < 10:
                print(f"  ⏭️  {target:15s}: dados insuficientes")
                continue
            
            model, metrics = train_model(X_train, y_train, X_val, y_val, f"{base}_{target}")
            
            # Salvar feature names como atributo customizado
            model._feat_names = feat_cols
            
            # Salvar modelo
            model_name = f"{base}_{target.replace('target_', '')}_xgb"
            model_path = f"{MODEL_DIR}/{model_name}.json"
            joblib.dump(model, model_path)
            
            # Log
            wr70 = metrics.get("wr_th0.7", 0)
            exp70 = metrics.get("exp_th0.7", 0)
            trades70 = metrics.get("trades_th0.7", 0)
            wr80 = metrics.get("wr_th0.8", 0)
            
            status = "✅" if exp70 > 0 else "⚠️"
            print(f"  {status} {target:15s}: acc={metrics['accuracy']:.1%}"
                  f" | th0.7: WR={wr70:.1%} trades={trades70:>3d} exp={exp70:.1%}"
                  f" | th0.8: WR={wr80:.1%}")
            
            combos[target] = metrics
        
        results[base] = combos
    
    # Salvar resultados
    res_path = f"{MODEL_DIR}/training_results.json"
    with open(res_path, "w") as f:
        json.dump(results, f, indent=2)
    
    # Resumo final
    print(f"\n{'='*60}")
    print(f"  ✅ TREINO CONCLUÍDO!")
    print(f"  📁 Modelos em: {MODEL_DIR}/")
    print(f"  📊 Resultados: {res_path}")
    print(f"{'='*60}")
    
    # Mostrar melhores
    print(f"\n  🏆 MELHORES RESULTADOS (th=0.7, exp>0):")
    best = []
    for base, combos in results.items():
        for target, m in combos.items():
            exp = m.get("exp_th0.7", -1)
            if exp > 0:
                best.append((exp, base, target, m["wr_th0.7"], m["trades_th0.7"]))
    
    best.sort(reverse=True)
    for exp, base, target, wr, trades in best[:20]:
        print(f"    {base:20s} {target:15s}: WR={wr:.1%} trades={trades:>3d} exp={exp:.1%} ✅" if exp > 0 else f"    {base:20s} {target:15s}: exp={exp:.1%} ❌")


if __name__ == "__main__":
    main()
