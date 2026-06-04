#!/usr/bin/env python3
"""
Hermes Quant V2 — Fase 11+12: Ensemble Master + Filtro de Confluência
Treina modelos XGBoost para prever CALL/PUT em M1, M5, M15.
Gera sinais com score de confiança.
"""
import os, sys, warnings, json
warnings.filterwarnings("ignore")

import pandas as pd
import numpy as np

os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ".")
from config.settings import (
    SYMBOLS, INPUT_TFS, CONTEXT_TFS, TF_LABEL,
    PROCESSED_DIR, MIN_CALL_PROB, MIN_PUT_PROB,
)

# ── XGBoost ──────────────────────────────────────────────
try:
    import xgboost as xgb
    HAS_XGB = True
except ImportError:
    HAS_XGB = False

try:
    import lightgbm as lgb
    HAS_LGB = True
except ImportError:
    HAS_LGB = False

from sklearn.model_selection import train_test_split, TimeSeriesSplit
from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score
import joblib

MODEL_DIR = "models"
os.makedirs(MODEL_DIR, exist_ok=True)


def load_features(symbol, tf):
    """Carrega dataset com features."""
    label = TF_LABEL.get(tf, tf)
    path = os.path.join(PROCESSED_DIR, f"{symbol.replace('/', '_')}_{label}_features.parquet")
    if not os.path.exists(path):
        return None
    return pd.read_parquet(path)


def prepare_features(df, target_col="target_call", test_size=0.2):
    """
    Prepara features para treinamento.
    Separa features numéricas, remove colunas indesejadas.
    """
    # Colunas a remover
    drop_cols = [
        "timestamp", "datetime", "symbol",
        "target_call", "target_put",
        "target_call_3", "target_put_3",
        "target_call_5", "target_put_5",
        "struct_market",  # string
    ]

    feature_cols = [c for c in df.columns
                    if c not in drop_cols
                    and not c.startswith("target_")
                    and df[c].dtype in ["float64", "float32", "int64", "int32"]]

    X = df[feature_cols].copy()
    y = df[target_col].copy()

    # Remove linhas com NaN
    mask = X.isna().any(axis=1) | y.isna()
    X = X[~mask]
    y = y[~mask]

    if len(X) == 0:
        return None, None, None, None, None

    # Split temporal (não aleatório!)
    split_idx = int(len(X) * (1 - test_size))
    X_train, X_test = X.iloc[:split_idx], X.iloc[split_idx:]
    y_train, y_test = y.iloc[:split_idx], y.iloc[split_idx:]

    # Validação: último 10% do treino
    val_idx = int(len(X_train) * 0.9)
    X_train, X_val = X_train.iloc[:val_idx], X_train.iloc[val_idx:]
    y_train, y_val = y_train.iloc[:val_idx], y_train.iloc[val_idx:]

    return X_train, X_val, X_test, y_train, y_val, y_test, feature_cols


def train_xgboost(X_train, y_train, X_val, y_val):
    """Treina XGBoost com early stopping."""
    if not HAS_XGB:
        print("    ⚠ XGBoost não instalado. Pulando.")
        return None

    model = xgb.XGBClassifier(
        n_estimators=500,
        max_depth=6,
        learning_rate=0.05,
        subsample=0.8,
        colsample_bytree=0.8,
        min_child_weight=3,
        reg_alpha=0.1,
        reg_lambda=1.0,
        scale_pos_weight=sum(y_train == 0) / max(sum(y_train == 1), 1),
        random_state=42,
        n_jobs=-1,
        eval_metric="logloss",
        early_stopping_rounds=50,
        verbosity=0,
    )

    model.fit(
        X_train, y_train,
        eval_set=[(X_val, y_val)],
        verbose=False,
    )

    return model


def train_lightgbm(X_train, y_train, X_val, y_val):
    """Treina LightGBM com early stopping."""
    if not HAS_LGB:
        print("    ⚠ LightGBM não instalado. Pulando.")
        return None

    model = lgb.LGBMClassifier(
        n_estimators=500,
        max_depth=6,
        learning_rate=0.05,
        subsample=0.8,
        colsample_bytree=0.8,
        min_child_samples=20,
        reg_alpha=0.1,
        reg_lambda=1.0,
        class_weight="balanced",
        random_state=42,
        n_jobs=-1,
        verbosity=-1,
    )

    model.fit(
        X_train, y_train,
        eval_set=[(X_val, y_val)],
        callbacks=[lgb.early_stopping(50), lgb.log_evaluation(0)],
    )

    return model


def evaluate_model(model, X_test, y_test):
    """Avalia o modelo no teste."""
    y_pred = model.predict(X_test)
    y_prob = model.predict_proba(X_test)[:, 1]

    metrics = {
        "accuracy": float(accuracy_score(y_test, y_pred)),
        "precision": float(precision_score(y_test, y_pred, zero_division=0)),
        "recall": float(recall_score(y_test, y_pred, zero_division=0)),
        "f1": float(f1_score(y_test, y_pred, zero_division=0)),
        "samples": int(len(y_test)),
        "pos_rate": float(y_test.mean()),
        "pred_pos_rate": float(y_pred.mean()),
        "mean_prob": float(y_prob.mean()),
    }

    return metrics, y_prob


def generate_signals(model, X_test, y_prob, timestamps=None, threshold=0.65):
    """
    Gera sinais CALL/PUT baseados na probabilidade.
    """
    signals = []
    for i in range(len(y_prob)):
        prob = y_prob[i]

        if prob >= threshold:
            sig_type = "CALL"
            confidence = prob
        elif prob <= (1 - threshold):
            sig_type = "PUT"
            confidence = 1 - prob
        else:
            continue  # Neutro, ignora

        signal = {
            "type": sig_type,
            "confidence": round(float(confidence), 4),
            "prob_call": round(float(prob), 4),
            "prob_put": round(float(1 - prob), 4),
        }

        if timestamps is not None:
            signal["timestamp"] = int(timestamps[i])

        signals.append(signal)

    return signals


# ═══════════════════════════════════════════════════════════
# TREINAMENTO
# ═══════════════════════════════════════════════════════════

def train_symbol(symbol, tf):
    """Treina modelos para um símbolo + timeframe."""
    label = TF_LABEL.get(tf, tf)
    symbol_short = symbol.replace("/USDT", "")

    print(f"  🎯 {symbol_short:6s} {label:4s} | Carregando dados...", end="")
    df = load_features(symbol, tf)
    if df is None or len(df) < 5000:
        print("  dados insuficientes")
        return

    print(f" {len(df):,} candles")

    results = {}
    feature_names = None

    for target_name, target_col in [
        ("call_1", "target_call"),
        ("put_1", "target_put"),
        ("call_5", "target_call_5"),
        ("put_5", "target_put_5"),
    ]:
        result = train_target(symbol, tf, df, target_name, target_col)
        if result:
            results[target_name] = result
            if feature_names is None:
                feature_names = result.get("features", [])

    # Salvar resultados
    report = {
        "symbol": symbol,
        "timeframe": tf,
        "results": results,
        "feature_count": len(feature_names) if feature_names else 0,
    }

    report_path = os.path.join(MODEL_DIR, f"{symbol.replace('/', '_')}_{label}_report.json")
    with open(report_path, "w") as f:
        json.dump(report, f, indent=2, default=str)

    print(f"  ✅ {symbol_short:6s} {label:4s} → relatório salvo")

    return report


def train_target(symbol, tf, df, target_name, target_col):
    """Treina modelo para um target específico."""
    label = TF_LABEL.get(tf, tf)
    result = prepare_features(df, target_col=target_col)

    if result is None:
        return None

    X_train, X_val, X_test, y_train, y_val, y_test, feature_cols = result

    if len(X_train) < 1000:
        return None

    print(f"    📊 {target_name:8s} | Treino: {len(X_train):,} | Val: {len(X_val):,} | Teste: {len(X_test):,}")

    # Treinar XGBoost
    model_xgb = train_xgboost(X_train, y_train, X_val, y_val)
    if model_xgb is not None:
        metrics_xgb, y_prob = evaluate_model(model_xgb, X_test, y_test)
        print(f"      XGBoost → Acc: {metrics_xgb['accuracy']:.2%} | Prec: {metrics_xgb['precision']:.2%} | Rec: {metrics_xgb['recall']:.2%} | F1: {metrics_xgb['f1']:.2%}")

        # Salvar modelo
        model_path = os.path.join(MODEL_DIR, f"{symbol.replace('/', '_')}_{label}_{target_name}_xgb.json")
        joblib.dump(model_xgb, model_path)

        # Gerar sinais
        signals = generate_signals(model_xgb, X_test, y_prob,
                                    timestamps=df["timestamp"].iloc[-len(y_test):].values,
                                    threshold=MIN_CALL_PROB)

        result_dict = {
            "target": target_name,
            "model": "xgboost",
            "metrics": metrics_xgb,
            "signals_test": len(signals),
            "feature_importance": dict(zip(feature_cols, model_xgb.feature_importances_.tolist())),
        }

        # Feature importance top 10
        fi = sorted(zip(feature_cols, model_xgb.feature_importances_.tolist()),
                    key=lambda x: x[1], reverse=True)
        result_dict["top_features"] = [{"feature": f, "importance": round(i, 4)} for f, i in fi[:10]]

        return result_dict

    return None


def train_all():
    """Treina todos os símbolos."""
    print("=" * 62)
    print("  🧠 HERMES QUANT V2 — ENSEMBLE MASTER (XGBoost/LightGBM)")
    print("=" * 62)

    if not HAS_XGB and not HAS_LGB:
        print("  ⚠ Nenhum framework ML instalado. Instale com:")
        print("    pip install xgboost lightgbm")
        print("=" * 62)
        return

    print(f"  XGBoost: {'✅' if HAS_XGB else '❌'}")
    print(f"  LightGBM: {'✅' if HAS_LGB else '❌'}")
    print("=" * 62)

    for symbol in SYMBOLS:
        print(f"\n{'─' * 40}")
        for tf in INPUT_TFS:
            train_symbol(symbol, tf)

    print(f"\n{'=' * 62}")
    print(f"  ✅ TREINAMENTO CONCLUÍDO!")
    print(f"  📁 Modelos em: {os.path.abspath(MODEL_DIR)}")
    print(f"{'=' * 62}")


def generate_signal_file():
    """Gera arquivo consolidado de sinais."""
    print("\n📊 Consolidando sinais...")
    all_signals = []

    for symbol in SYMBOLS:
        for tf in INPUT_TFS:
            label = TF_LABEL.get(tf, tf)
            report_path = os.path.join(MODEL_DIR, f"{symbol.replace('/', '_')}_{label}_report.json")
            if not os.path.exists(report_path):
                continue

            with open(report_path) as f:
                report = json.load(f)

            for target_name, result in report.get("results", {}).items():
                if result and "metrics" in result:
                    all_signals.append({
                        "symbol": symbol,
                        "timeframe": tf,
                        "target": target_name,
                        "accuracy": result["metrics"]["accuracy"],
                        "precision": result["metrics"]["precision"],
                        "signals": result.get("signals_test", 0),
                    })

    if all_signals:
        df_signals = pd.DataFrame(all_signals)
        df_signals.to_csv(os.path.join(MODEL_DIR, "signal_summary.csv"), index=False)
        print(f"  ✅ {len(all_signals)} sinais consolidados em models/signal_summary.csv")
    else:
        print("  ⚠ Nenhum sinal para consolidar")


if __name__ == "__main__":
    train_all()
    generate_signal_file()
