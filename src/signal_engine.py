#!/usr/bin/env python3
"""
Hermes Quant V2 — Motor de Sinais Final
=========================================
Combina:
  - XGBoost Ensemble (predição CALL/PUT com probabilidade)
  - MRD Regime Filter (só opera em regimes com expectativa positiva)
  - Filtro de Confluência (multi-TF + estrutura)
  - Calibração de probabilidade (acuracia histórica por nível de confiança)

Saída: sinais CALL/PUT com score de confiança calibrado + filtro de regime.
"""
import os, sys, warnings, json
warnings.filterwarnings("ignore")

import pandas as pd
import numpy as np
import joblib

os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ".")
from config.settings import (
    SYMBOLS, INPUT_TFS, TF_LABEL, PROCESSED_DIR, MODEL_DIR,
    PAYOUT_RATE,
)
from src.market_regime import classify_regime, RegimeFilter


# ═══════════════════════════════════════════════════════════
# 1. CARREGAR MODELOS
# ═══════════════════════════════════════════════════════════

def load_models(symbol, tf):
    """Carrega modelos XGBoost treinados."""
    label = TF_LABEL.get(tf, tf)
    models = {}
    for target in ["call_1", "put_1", "call_5", "put_5"]:
        path = os.path.join(MODEL_DIR, f"{symbol.replace('/', '_')}_{label}_{target}_xgb.json")
        if os.path.exists(path):
            models[target] = joblib.load(path)
    return models


def load_latest_data(symbol, tf):
    """Carrega os dados processados mais recentes."""
    label = TF_LABEL.get(tf, tf)
    path = os.path.join(PROCESSED_DIR, f"{symbol.replace('/', '_')}_{label}_features.parquet")
    if not os.path.exists(path):
        return None
    return pd.read_parquet(path)


def load_mrd_cache(symbol, tf):
    """Carrega tabela de performance MRD."""
    label = TF_LABEL.get(tf, tf)
    path = os.path.join(MODEL_DIR, f"{symbol.replace('/', '_')}_{label}_regime_perf.json")
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return None


# ═══════════════════════════════════════════════════════════
# 2. CALIBRADOR DE PROBABILIDADE
# ═══════════════════════════════════════════════════════════

def calibrate_probabilities(y_true, y_prob, bins=20):
    """
    Calcula a calibração do modelo: para cada faixa de probabilidade,
    qual a precisão real observada.
    
    Retorna DataFrame com:
      - prob_bin: faixa de probabilidade
      - count: amostras na faixa
      - precision: acuracia real na faixa
      - expectancy: (precision * payout) - ((1-precision) * 1)
    """
    cal_df = pd.DataFrame({"true": y_true, "prob": y_prob})
    cal_df["prob_bin"] = pd.cut(cal_df["prob"], bins=np.linspace(0, 1, bins + 1))

    results = []
    for bin_name, group in cal_df.groupby("prob_bin", observed=True):
        n = len(group)
        if n < 10:
            continue
        precision = group["true"].mean()
        expectancy = (precision * PAYOUT_RATE) - ((1 - precision) * 1)

        results.append({
            "prob_bin": str(bin_name),
            "prob_mid": (bin_name.left + bin_name.right) / 2,
            "count": n,
            "precision": round(float(precision), 4),
            "expectancy": round(float(expectancy), 4),
            "tradable": expectancy > 0,
        })

    return pd.DataFrame(results)


def build_calibration(symbol, tf, model_key="call_1"):
    """
    Constrói tabela de calibração a partir dos dados de teste.
    """
    df = load_latest_data(symbol, tf)
    if df is None or len(df) < 10000:
        return None

    model = load_models(symbol, tf)
    if model_key not in model:
        return None

    # Pegar features iguais ao treinamento
    feature_cols = [c for c in df.columns
                    if c not in ["timestamp", "datetime", "symbol",
                                  "target_call", "target_put",
                                  "target_call_3", "target_put_3",
                                  "target_call_5", "target_put_5",
                                  "struct_market"]
                    and df[c].dtype in ["float64", "float32", "int64", "int32"]]

    target_col = model_key.replace("call_", "target_call_").replace("put_", "target_put_")
    if target_col.endswith("_"):
        target_col = target_col[:-1]

    X = df[feature_cols].copy()
    y = df[target_col] if target_col in df.columns else None

    if y is None:
        return None

    # Remover NaN
    mask = X.isna().any(axis=1) | y.isna()
    X = X[~mask]
    y = y[~mask]

    # Últimos 20% como calibração
    split_idx = int(len(X) * 0.8)
    X_cal, y_cal = X.iloc[split_idx:], y.iloc[split_idx:]

    if len(X_cal) < 100:
        return None

    y_prob = model.predict_proba(X_cal)[:, 1]

    cal = calibrate_probabilities(y_cal.values, y_prob)
    return cal


# ═══════════════════════════════════════════════════════════
# 3. GERADOR DE SINAIS COM MRD
# ═══════════════════════════════════════════════════════════

def generate_signals(symbol, tf, min_prob=0.65, use_mrd=True):
    """
    Gera sinais CALL/PUT com filtros:
      1. Modelo XGBoost → probabilidade
      2. Calibração → precisão real para aquela faixa
      3. MRD → regime atual
      4. Expectancy calculada
    
    Retorna lista de sinais com metadados de qualidade.
    """
    label = TF_LABEL.get(tf, tf)
    symbol_short = symbol.replace("/USDT", "")

    # 1. Carregar dados e modelos
    df = load_latest_data(symbol, tf)
    models = load_models(symbol, tf)

    if df is None or not models:
        return [], "sem dados ou modelos"

    # 2. Último candle (tempo real)
    last_candle = df.iloc[-1:]

    # 3. Preparar features
    feature_cols = [c for c in df.columns
                    if c not in ["timestamp", "datetime", "symbol",
                                  "target_call", "target_put",
                                  "target_call_3", "target_put_3",
                                  "target_call_5", "target_put_5",
                                  "struct_market"]
                    and df[c].dtype in ["float64", "float32", "int64", "int32"]]

    X_last = last_candle[feature_cols].copy()
    # Remover NaN
    if X_last.isna().any(axis=1).any():
        return [], "NaN nas features do último candle"

    # 4. Predizer
    signals = []
    for model_key, model in models.items():
        target_dir = "call" if "call" in model_key else "put"
        target_period = model_key.split("_")[-1]  # "1" ou "5"

        y_prob = model.predict_proba(X_last)[0, 1]
        confidence = float(y_prob)

        if target_dir == "put":
            confidence = 1 - confidence  # probabilidade de PUT

        if confidence < min_prob:
            continue

        try:
            # 5. MRD: verificar regime
            effective_mrd = use_mrd
            regime_name = "unknown"
            wr = 0
            exp = -999
            
            if use_mrd:
                regime = classify_regime(df)
                regime_name = regime["regime"]
                perf = load_mrd_cache(symbol, tf)

                if perf is not None:
                    reg_perf = {r["regime"]: r for r in perf}
                    
                    # Check if ANY regime has positive expectancy
                    has_positive_regime = any(
                        r.get("expectancy_call", -999) > 0 or r.get("expectancy_put", -999) > 0
                        for r in perf
                    )
                    
                    if regime_name in reg_perf:
                        wr = reg_perf[regime_name].get(f"win_rate_{target_dir}", 0)
                        exp = reg_perf[regime_name].get(f"expectancy_{target_dir}", 0)
                    else:
                        wr = 0
                        exp = -999
                    
                    # If no regime has positive expectancy, fall back to model-only
                    if not has_positive_regime:
                        effective_mrd = False
                        exp = 0  # Neutralize MRD filter

            # 6. Expectancy combinada (modelo × regime)
            cal_exp = (confidence * PAYOUT_RATE) - ((1 - confidence) * 1)

            # 7. Tradable: model + optional MRD filter
            if effective_mrd:
                tradable = cal_exp > 0 and exp > -0.5
            else:
                tradable = cal_exp > 0

            signal = {
                "symbol": symbol,
                "timeframe": tf,
                "type": target_dir.upper(),
                "period": target_period,
                "confidence": round(confidence, 4),
                "raw_prob": round(float(y_prob), 4),
                "regime": regime_name,
                "regime_wr": round(float(wr), 4),
                "regime_exp": round(float(exp), 4),
                "model_exp": round(float(cal_exp), 4),
                "tradable": tradable,
                "timestamp": int(df["timestamp"].iloc[-1]),
            }

            signals.append(signal)

        except Exception as e:
            continue

    return signals, f"{len(signals)} sinais gerados"


# ═══════════════════════════════════════════════════════════
# 4. MODO SCAN (todos os símbolos)
# ═══════════════════════════════════════════════════════════

def scan_all():
    """Escaneia todos os símbolos + timeframes e mostra sinais."""
    print("=" * 62)
    print("  📡 HERMES QUANT V2 — MOTOR DE SINAIS")
    print("=" * 62)
    print(f"  Filtros: XGBoost + MRD + Calibração")
    print(f"  Payout simulado: {PAYOUT_RATE:.0%}")
    print("=" * 62)

    all_signals = []

    for symbol in SYMBOLS:
        for tf in INPUT_TFS:
            label = TF_LABEL.get(tf, tf)
            signals, msg = generate_signals(symbol, tf, min_prob=0.60)

            if signals:
                all_signals.extend(signals)
                for sig in signals:
                    trade = "✅" if sig["tradable"] else "⛔"
                    print(
                        f"  {trade} {sig['symbol']:9s} {sig['timeframe']:4s} "
                        f"{sig['type']:4s} M{sig['period']} | "
                        f"Conf: {sig['confidence']:.1%} | "
                        f"Regime: {sig['regime']:20s} | "
                        f"Exp: {sig['model_exp']:.2%}"
                    )

    if not all_signals:
        print("  ⚠ Nenhum sinal gerado (dados insuficientes)")
        return

    # Salvar sinais
    df_sig = pd.DataFrame(all_signals)
    df_sig.to_csv(os.path.join(MODEL_DIR, "live_signals.csv"), index=False)
    print(f"\n  📊 {len(all_signals)} sinais salvos em models/live_signals.csv")


# ═══════════════════════════════════════════════════════════
# 5. MODO BACKTEST (avaliar performance histórica)
# ═══════════════════════════════════════════════════════════

def backtest_strategy(symbol="BTC/USDT", tf="1m", min_prob=0.65, use_mrd=True):
    """
    Backtesting completo: aplica a estratégia em todo o histórico
    e calcula métricas de performance.
    """
    df = load_latest_data(symbol, tf)
    models = load_models(symbol, tf)

    if df is None or not models:
        print(f"  ⚠ Dados ou modelos insuficientes")
        return None

    # Preparar features
    feature_cols = [c for c in df.columns
                    if c not in ["timestamp", "datetime", "symbol",
                                  "target_call", "target_put",
                                  "target_call_3", "target_put_3",
                                  "target_call_5", "target_put_5",
                                  "struct_market"]
                    and df[c].dtype in ["float64", "float32", "int64", "int32"]]

    X = df[feature_cols].copy()
    mask = X.isna().any(axis=1)
    X = X[~mask]
    df_clean = df[~mask].copy()

    if len(X) < 10000:
        return None

    # Split temporal: treino = antigo, teste = recente
    split = int(len(X) * 0.8)
    X_test = X.iloc[split:]
    df_test = df_clean.iloc[split:].copy()

    # MAPEAMENTO: modelo → coluna target real
    MODEL_TARGET_MAP = {
        "call_1": "target_call",
        "put_1": "target_put",
        "call_5": "target_call_5",
        "put_5": "target_put_5",
    }

    print(f"  Backtesting {symbol} {tf}: {len(df_test):,} candles de teste")

    # PREDIÇÃO EM LOTE
    print(f"  Predizendo em lote...")
    batch_preds = {}
    for model_key, model in models.items():
        y_prob = model.predict_proba(X_test)[:, 1]
        # y_prob É a probabilidade do target positivo para este modelo
        # call_1: y_prob = P(target_call=1)  → conf para CALL
        # put_1:  y_prob = P(target_put=1)   → conf para PUT
        batch_preds[model_key] = y_prob

    print(f"  Gerando trades (melhor sinal por candle)...")

    trades = []
    for i in range(len(X_test)):
        ts = int(df_test["timestamp"].iloc[i])

        # Encontrar o MELHOR sinal para este candle
        best_signal = None
        best_conf = 0

        for model_key in models:
            target_dir = "call" if "call" in model_key else "put"
            target_col = MODEL_TARGET_MAP[model_key]
            conf = float(batch_preds[model_key][i])

            # Threshold adaptativo por timeframe
            # M1 precisa >0.88, M5 >0.85 (calibração empírica)
            tf_thresholds = {"1m": 0.88, "5m": 0.85, "15m": 0.82}
            effective_min = tf_thresholds.get(tf, 0.85)
            if conf < effective_min:
                continue

            # Só aceita se melhor que o atual
            if conf > best_conf:
                best_conf = conf
                # MRD amostrado
                regime_name = "nosignal"
                if use_mrd and i % 10 == 0:
                    window = df_clean.iloc[:split + i]
                    regime = classify_regime(window)
                    regime_name = regime["regime"]
                elif use_mrd and trades:
                    regime_name = trades[-1]["regime"]

                actual = int(df_test[target_col].iloc[i]) if target_col in df_test.columns else 0

                best_signal = {
                    "timestamp": ts,
                    "type": target_dir.upper(),
                    "confidence": conf,
                    "regime": regime_name,
                    "actual": actual,
                    "won": actual == 1,
                }

        if best_signal:
            trades.append(best_signal)

    if not trades:
        print(f"  ⚠ Nenhum trade gerado (aumente min_prob)")
        return None

    # Métricas
    df_trades = pd.DataFrame(trades)
    total = len(df_trades)
    wins = df_trades["won"].sum()
    losses = total - wins
    wr = wins / total if total > 0 else 0

    # Por regime
    print(f"\n  📊 Resultados ({total} trades):")
    print(f"     Win Rate: {wr:.1%} ({wins}/{total})")
    print(f"     Payoff:   {PAYOUT_RATE:.0%}")

    expectancy = (wr * PAYOUT_RATE) - ((1 - wr) * 1)
    print(f"     Expectancy: {expectancy:.2%}")

    if expectancy > 0:
        print(f"     Lucro/100 trades: ${expectancy * 100:.2f}")

    print()
    print(f"     Performance por Regime:")
    for regime, group in df_trades.groupby("regime"):
        n = len(group)
        if n < 5:
            continue
        w = group["won"].sum()
        wr_g = w / n
        exp_g = (wr_g * PAYOUT_RATE) - ((1 - wr_g) * 1)
        print(f"       {regime:25s}: {n:>5d} trades | WR {wr_g:.1%} | Exp {exp_g:.2%}")

    return df_trades


# ═══════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "backtest":
        backtest_strategy("BTC/USDT", "1m", min_prob=0.60, use_mrd=True)
        print("\n" + "=" * 40)
        backtest_strategy("BTC/USDT", "5m", min_prob=0.60, use_mrd=True)
    else:
        scan_all()
