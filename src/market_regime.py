#!/usr/bin/env python3
"""
Hermes Quant V2 — Market Regime Detection (MRD)
================================================
Classifica continuamente o mercado em regimes:
  - Strong Trend (Bull/Bear)
  - Weak Trend
  - Lateralization (Range)
  - High Volatility
  - Low Volatility
  - Erratic Market

Filtra operações: só libera quando o regime histórico mostra
expectativa positiva para aquele setup.

Fluxo:
  MRD classifica regime → consulta tabela histórica de performance
  por regime → libera/bloqueia operação.
"""
import os, sys, warnings, json
warnings.filterwarnings("ignore")

import pandas as pd
import numpy as np

os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ".")
from config.settings import (
    SYMBOLS, INPUT_TFS, CONTEXT_TFS, TF_LABEL,
    PROCESSED_DIR, MODEL_DIR,
)


# ═══════════════════════════════════════════════════════════
# 1. CLASSIFICADOR DE REGIME
# ═══════════════════════════════════════════════════════════

def classify_regime(df, lookback=50):
    """
    Classifica o regime de mercado atual baseado nos últimos N candles.
    Retorna dict com regime principal e scores.
    """
    window = df.iloc[-lookback:] if len(df) > lookback else df

    # ── Trend Strength (ADX) ──────────────────────────────
    adx_mean = window["adx"].mean() if "adx" in window.columns else 15
    plus_di = window["plus_di"].mean() if "plus_di" in window.columns else 25
    minus_di = window["minus_di"].mean() if "minus_di" in window.columns else 25

    # ── Volatility (ATR) ──────────────────────────────────
    atr_mean = window["atr_pct"].mean() if "atr_pct" in window.columns else 0.5
    atr_long = window["atr_pct"].iloc[-lookback*3:].mean() if len(df) > lookback*3 else atr_mean
    vol_ratio = atr_mean / atr_long if atr_long > 0 else 1.0

    # ── Range / Lateralização ─────────────────────────────
    price_range = (window["high"].max() - window["low"].min()) / window["close"].mean()
    body_ratio = (abs(window["close"] - window["open"])).mean() / (window["high"] - window["low"]).mean()

    # ── Direcionalidade ───────────────────────────────────
    direction = "bull" if plus_di > minus_di else "bear"
    di_spread = abs(plus_di - minus_di)

    # ── Erratic: whipsaw detection ────────────────────────
    # Alta volatilidade + corpos pequenos + mudanças frequentes de direção
    direction_changes = sum(
        1 for i in range(1, len(window))
        if (window["close"].iloc[i] > window["close"].iloc[i-1]) !=
           (window["close"].iloc[i-1] > window["close"].iloc[i-2])
    )
    erratic_score = direction_changes / max(len(window), 1)

    # ── Score de continuidade (candles na mesma direção) ──
    recent = window.tail(10)
    same_dir = sum(
        1 for i in range(1, len(recent))
        if (recent["close"].iloc[i] > recent["open"].iloc[i]) ==
           (recent["close"].iloc[i-1] > recent["open"].iloc[i-1])
    )

    # ═══════════════════════════════════════════════════════
    # CLASSIFICAÇÃO EM CAMADAS
    # ═══════════════════════════════════════════════════════

    # Camada 1: Volatilidade
    if vol_ratio > 1.5:
        vol_regime = "high_vol"
    elif vol_ratio < 0.6:
        vol_regime = "low_vol"
    else:
        vol_regime = "normal_vol"

    # Camada 2: Erratic (whipsaw)
    if erratic_score > 0.5 and vol_ratio > 1.3:
        primary_regime = "erratic"
        secondary = vol_regime
    # Camada 3: Tendência forte
    elif adx_mean > 30 and di_spread > 15:
        primary_regime = f"strong_trend_{direction}"
        secondary = vol_regime
    # Camada 4: Tendência fraca
    elif adx_mean > 20 and di_spread > 10:
        primary_regime = f"weak_trend_{direction}"
        secondary = vol_regime
    # Camada 5: Lateralização
    elif adx_mean < 20:
        primary_regime = "lateralization"
        secondary = vol_regime
    else:
        primary_regime = "lateralization"
        secondary = vol_regime

    # Scores numéricos para comparação
    scores = {
        "adx": round(float(adx_mean), 2),
        "di_spread": round(float(di_spread), 2),
        "vol_ratio": round(float(vol_ratio), 2),
        "erratic_score": round(float(erratic_score), 4),
        "same_dir_pct": round(same_dir / 10, 2),
        "direction": direction,
    }

    result = {
        "regime": primary_regime,
        "vol_regime": vol_regime,
        "secondary": secondary,
        "scores": scores,
    }

    return result


# ═══════════════════════════════════════════════════════════
# 2. TABELA DE EXPECTATIVA HISTÓRICA POR REGIME
# ═══════════════════════════════════════════════════════════

def vectorized_regime(df, lookback=50):
    """
    Classifica regime para TODOS os candles de uma vez usando
    operações vetorizadas (rolling windows C-otimizadas).
    Retorna array com regime de cada candle.
    """
    n = len(df)
    regimes = np.full(n, "unknown", dtype=object)

    def classify_window(slice_df):
        """Classifica regime de um slice (rolling apply)."""
        adx_m = slice_df["adx"].mean() if "adx" in slice_df.columns else 15
        pd_m = slice_df["plus_di"].mean() if "plus_di" in slice_df.columns else 25
        md_m = slice_df["minus_di"].mean() if "minus_di" in slice_df.columns else 25
        atr = slice_df["atr_pct"].mean() if "atr_pct" in slice_df.columns else 0.5
        dir_spread = abs(pd_m - md_m)
        direction = "bull" if pd_m > md_m else "bear"

        # Erratic score
        closes = slice_df["close"].values
        up_down = np.diff(np.sign(np.diff(closes)))
        erratic = np.sum(up_down != 0) / max(len(closes), 1)

        if erratic > 0.5 and atr > (slice_df["atr_pct"].mean() * 1.3 if len(slice_df) > 1 else 0):
            return f"erratic"
        elif adx_m > 30 and dir_spread > 15:
            return f"strong_trend_{direction}"
        elif adx_m > 20 and dir_spread > 10:
            return f"weak_trend_{direction}"
        else:
            return "lateralization"

    # Processar em blocos: rolling de 50 em 50 (amostragem)
    # Para performance total usamos stride sampling
    stride = max(1, lookback // 5)
    for i in range(lookback, n, stride):
        window = df.iloc[i - lookback : i]
        regimes[i] = classify_window(window)

    # Preencher gaps entre as amostras
    last_valid = "unknown"
    for i in range(n):
        if regimes[i] == "unknown":
            regimes[i] = last_valid
        else:
            last_valid = regimes[i]

    return regimes


def build_regime_performance(df, lookback=50, min_samples=30):
    """
    Para cada ponto no histórico, classifica o regime usando
    método vetorizado e calcula a performance dos sinais.
    """
    print(f"  Classificando regimes em {len(df):,} candles (vetorizado)...")

    # Regime vetorizado
    df = df.copy()
    df["regime"] = vectorized_regime(df, lookback)

    # Remover primeiros lookback candles (sem regime)
    df_regime = df.iloc[lookback:].copy()

    # Calcular performance por regime
    results = []
    for regime, group in df_regime.groupby("regime"):
        n = len(group)
        if n < min_samples:
            continue

        call_win = group["target_call"].mean() if "target_call" in group.columns else 0
        put_win = group["target_put"].mean() if "target_put" in group.columns else 0

        payout = 0.80  # Payout típico IQOption
        expectancy_call = (call_win * payout) - ((1 - call_win) * 1)
        expectancy_put = (put_win * payout) - ((1 - put_win) * 1)

        vol = group["atr_pct"].mean() if "atr_pct" in group.columns else 0

        results.append({
            "regime": regime,
            "samples": n,
            "win_rate_call": round(float(call_win), 4),
            "win_rate_put": round(float(put_win), 4),
            "expectancy_call": round(float(expectancy_call), 4),
            "expectancy_put": round(float(expectancy_put), 4),
            "avg_volatility": round(float(vol), 4),
        })

    return pd.DataFrame(results)


def load_regime_performance_cache(symbol, tf):
    """Carrega cache de performance por regime."""
    label = TF_LABEL.get(tf, tf)
    path = os.path.join(MODEL_DIR, f"{symbol.replace('/', '_')}_{label}_regime_perf.json")
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return None


def save_regime_performance_cache(symbol, tf, data):
    """Salva cache de performance por regime."""
    label = TF_LABEL.get(tf, tf)
    path = os.path.join(MODEL_DIR, f"{symbol.replace('/', '_')}_{label}_regime_perf.json")
    with open(path, "w") as f:
        json.dump(data, f, indent=2)


# ═══════════════════════════════════════════════════════════
# 3. FILTRO DE OPERAÇÃO
# ═══════════════════════════════════════════════════════════

class RegimeFilter:
    """
    Filtro que só libera operações quando o regime atual tem
    expectativa histórica positiva.
    """

    def __init__(self, performance_table=None):
        """
        performance_table: dict {regime: {expectancy_call, expectancy_put, ...}}
        """
        self.performance = performance_table or {}

    def load_from_cache(self, symbol, tf):
        """Carrega tabela de performance do cache."""
        data = load_regime_performance_cache(symbol, tf)
        if data:
            self.performance = {r["regime"]: r for r in data}
            return True
        return False

    def is_tradable(self, regime, signal_type="call", min_expectancy=0.0):
        """
        Verifica se o regime atual permite operar.
        
        Args:
            regime: dict do classify_regime()
            signal_type: "call" ou "put"
            min_expectancy: expectativa mínima para liberar
        
        Returns:
            (bool, reason, expectancy)
        """
        regime_name = regime["regime"]

        if regime_name not in self.performance:
            return (False, f"regime '{regime_name}' sem dados históricos", 0.0)

        perf = self.performance[regime_name]
        exp_key = f"expectancy_{signal_type}"
        wr_key = f"win_rate_{signal_type}"

        expectancy = perf.get(exp_key, 0.0)
        win_rate = perf.get(wr_key, 0.0)

        if expectancy < min_expectancy:
            return (
                False,
                f"{regime_name}: expectativa {expectancy:.2%} < mínimo {min_expectancy:.2%}",
                expectancy
            )

        return (
            True,
            f"{regime_name}: WR {win_rate:.1%} | Exp {expectancy:.2%} ✅",
            expectancy
        )

    def get_best_setup(self, regime):
        """
        Para o regime atual, qual setup tem melhor expectativa?
        Retorna "call", "put", ou None.
        """
        regime_name = regime["regime"]
        if regime_name not in self.performance:
            return None

        perf = self.performance[regime_name]
        exp_call = perf.get("expectancy_call", -999)
        exp_put = perf.get("expectancy_put", -999)

        if exp_call > exp_put and exp_call > 0:
            return "call"
        elif exp_put > exp_call and exp_put > 0:
            return "put"
        return None

    def summary(self):
        """Resumo textual dos regimes disponíveis."""
        lines = ["📊 Regime Performance Table:"]
        for regime, perf in sorted(self.performance.items()):
            if isinstance(perf, dict):
                wr_c = perf.get("win_rate_call", 0)
                wr_p = perf.get("win_rate_put", 0)
                exp_c = perf.get("expectancy_call", 0)
                exp_p = perf.get("expectancy_put", 0)
                n = perf.get("samples", 0)
                lines.append(
                    f"  {regime:25s} | n={n:>6,d} | CALL WR={wr_c:.1%} Exp={exp_c:.2%} | "
                    f"PUT WR={wr_p:.1%} Exp={exp_p:.2%}"
                )
        return "\n".join(lines)


# ═══════════════════════════════════════════════════════════
# 4. MÓDULO EXECUTÁVEL
# ═══════════════════════════════════════════════════════════

def process_symbol_mrd(symbol, tf, max_rows=None):
    """Processa Market Regime Detection para um símbolo."""
    label = TF_LABEL.get(tf, tf)
    symbol_short = symbol.replace("/USDT", "")

    # Carregar dados processados
    feat_path = os.path.join(PROCESSED_DIR, f"{symbol.replace('/', '_')}_{label}_features.parquet")
    if not os.path.exists(feat_path):
        print(f"  ⚠ {symbol_short:6s} {label:4s} → sem dados processados")
        return

    df = pd.read_parquet(feat_path)
    if len(df) < 500:
        return

    # Downsample para evitar OOM (mantendo dados mais recentes)
    if max_rows and len(df) > max_rows:
        print(f"  🧠 {symbol_short:6s} {label:4s} | {len(df):,} candles (downsample)")
        df = df.tail(max_rows)
    else:
        print(f"  🧠 {symbol_short:6s} {label:4s} | {len(df):,} candles")
    

    # 1. Classificar regime no último candle
    latest_regime = classify_regime(df)
    print(f"      Regime atual: {latest_regime['regime']}")
    print(f"      Scores: {json.dumps(latest_regime['scores'], indent=8)}")

    # 2. Construir tabela histórica de performance por regime
    perf_df = build_regime_performance(df)

    if len(perf_df) == 0:
        print(f"      ⚠ Dados insuficientes para calcular performance por regime")
        return

    # Salvar cache
    perf_data = perf_df.to_dict("records")
    save_regime_performance_cache(symbol, tf, perf_data)

    # 3. Mostrar tabela
    print(f"\n      📊 Performance por Regime:")
    for _, row in perf_df.iterrows():
        exp_call = row["expectancy_call"]
        exp_put = row["expectancy_put"]
        call_ok = "✅" if exp_call > 0 else "❌"
        put_ok = "✅" if exp_put > 0 else "❌"
        print(f"        {row['regime']:25s} | n={row['samples']:>6,d} | "
              f"CALL WR={row['win_rate_call']:.1%} Exp={exp_call:.2%} {call_ok} | "
              f"PUT WR={row['win_rate_put']:.1%} Exp={exp_put:.2%} {put_ok}")

    # 4. Verificar se o regime atual permite operar
    filter_ = RegimeFilter(perf_data)
    direction = latest_regime["scores"]["direction"]

    for sig_type in ["call", "put"]:
        ok, reason, exp = filter_.is_tradable(latest_regime, sig_type)
        icon = "✅" if ok else "⛔"
        print(f"      {icon} {sig_type.upper():4s} → {reason}")

    return perf_df


def main():
    print("=" * 62)
    print("  🧠 HERMES QUANT V2 — MARKET REGIME DETECTION")
    print("=" * 62)
    print("  Regimes:")
    print("    • Strong Trend (Bull/Bear)")
    print("    • Weak Trend (Bull/Bear)")
    print("    • Lateralization")
    print("    • High/Low Volatility")
    print("    • Erratic Market (whipsaw)")
    print("=" * 62)

    for symbol in SYMBOLS:
        print(f"\n{'─' * 40}")
        for tf in INPUT_TFS:
            # Downsample M1/5m large datasets to avoid OOM
            limits = {"1m": 200_000, "5m": 200_000, "15m": None}
            process_symbol_mrd(symbol, tf, max_rows=limits.get(tf))

    print(f"\n{'=' * 62}")
    print(f"  ✅ MARKET REGIME DETECTION CONCLUÍDO!")
    print(f"  📁 Caches em: {os.path.abspath(MODEL_DIR)}")
    print(f"{'=' * 62}")


if __name__ == "__main__":
    main()
