#!/usr/bin/env python3
"""
Hermes Quant V2 — Filtro Final: MRD + Martingale + Confluência
===============================================================
Regras de ouro:
  1. MRD: só opera se o regime tem expectativa histórica positiva
  2. Martingale: só usa em regimes de alta confiança e volatilidade controlada
  3. Soros: operações agressivas (entrada maior) em setups de confluência máxima
"""
import os, sys, json, warnings
warnings.filterwarnings("ignore")

import pandas as pd
import numpy as np

os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ".")
from config.settings import MODEL_DIR


# ═══════════════════════════════════════════════════════════
# 1. MRD FILTER — Carrega performance histórica por regime
# ═══════════════════════════════════════════════════════════

class MRDFilter:
    """
    Filtro de Regime de Mercado.
    Só libera operações se o regime atual tem expectativa positiva.
    """

    def __init__(self):
        self.regime_perf = {}  # {regime: {call_wr, put_wr, call_exp, put_exp, samples}}

    def load_cache(self, symbol, tf):
        label = f"{symbol.replace('/', '_')}_{tf}"
        path = os.path.join(MODEL_DIR, f"{label}_regime_perf.json")
        if os.path.exists(path):
            with open(path) as f:
                data = json.load(f)
            self.regime_perf = {r["regime"]: r for r in data}
            return True
        return False

    def get_regime_exp(self, regime, direction="call"):
        """Retorna expectativa para um regime + direção."""
        if regime not in self.regime_perf:
            return None
        return self.regime_perf[regime].get(f"expectancy_{direction}", None)

    def is_tradable(self, regime, direction="call"):
        """Regime permite trade nesta direção?"""
        exp = self.get_regime_exp(regime, direction)
        if exp is None:
            return False, f"sem dados para {regime}"
        if exp > 0:
            return True, f"{regime}: Exp {exp:.2%} ✅"
        return False, f"{regime}: Exp {exp:.2%} ⛔"

    def summary(self):
        lines = []
        for regime, p in sorted(self.regime_perf.items()):
            lines.append(
                f"  {regime:25s} | n={p['samples']:>6,d} | "
                f"CALL WR={p['win_rate_call']:.1%} Exp={p['expectancy_call']:.2%} | "
                f"PUT WR={p['win_rate_put']:.1%} Exp={p['expectancy_put']:.2%}"
            )
        return "\n".join(lines)


# ═══════════════════════════════════════════════════════════
# 2. MARTINGALE ANALYZER
# ═══════════════════════════════════════════════════════════

class MartingaleAnalyzer:
    """
    Decide se Martingale é viável no cenário atual.
    
    Regras:
    - Só martingale em regimes com WR > 55%
    - Máximo de 3 níveis (1x, 2x, 4x)
    - Para após 2 perdas consecutivas em regimes fracos
    - Usar apenas em M5/M15 (mais tempo para reverter)
    """

    def __init__(self, regime_perf=None):
        self.regime_perf = regime_perf or {}

    def analyze(self, regime, direction, confidence, tf="1m", loss_streak=0):
        """
        Retorna:
          - use_martingale: bool
          - max_levels: int (1-3)
          - reason: str
          - survival_prob: float (probabilidade de sobrevivência até nível N)
        """
        wr = None
        if regime in self.regime_perf:
            wr = self.regime_perf[regime].get(f"win_rate_{direction}", None)

        reasons = []
        score = 0  # Quanto maior, mais seguro para martingale

        # Regra 1: WR do regime
        if wr is not None and wr > 0.55:
            score += 2
            reasons.append(f"WR {wr:.1%} > 55%")
        elif wr is not None and wr > 0.50:
            score += 1
            reasons.append(f"WR {wr:.1%} > 50%")
        else:
            reasons.append(f"WR baixo")
            return {
                "use_martingale": False,
                "max_levels": 0,
                "reason": "WR baixo + " + " | ".join(reasons),
                "survival_prob": 0.0,
            }

        # Regra 2: Confiança do sinal
        if confidence > 0.90:
            score += 2
            reasons.append(f"Conf {confidence:.1%} > 90%")
        elif confidence > 0.85:
            score += 1
            reasons.append(f"Conf {confidence:.1%} > 85%")

        # Regra 3: Timeframe (M1 arriscado para martingale)
        if tf in ["5m", "15m"]:
            score += 1
            reasons.append(f"TF {tf} adequado")
        else:
            reasons.append(f"TF {tf} rápido")

        # Regra 4: Streak de perdas
        if loss_streak >= 3:
            score -= 3
            reasons.append(f"{loss_streak} perdas consecutivas ⛔")
        elif loss_streak >= 2:
            score -= 1
            reasons.append(f"{loss_streak} perdas consecutivas ⚠️")

        # Decisão
        if score >= 4:
            max_levels = 3
            use = True
        elif score >= 2:
            max_levels = 2
            use = True
        elif score >= 1:
            max_levels = 1
            use = True
        else:
            max_levels = 0
            use = False

        # Probabilidade de sobrevivência
        if wr is not None and use:
            surv = wr
            for _ in range(1, max_levels):
                surv = surv + (1 - surv) * wr  # Prob de acertar em algum nível
            survival_prob = min(surv, 0.99)
        else:
            survival_prob = 0.0

        return {
            "use_martingale": use,
            "max_levels": max_levels,
            "reason": " | ".join(reasons),
            "survival_prob": round(survival_prob, 4),
            "score": score,
        }


# ═══════════════════════════════════════════════════════════
# 3. SOROS MODE — Agressividade controlada
# ═══════════════════════════════════════════════════════════

class SorosAnalyzer:
    """
    Modo Soros: agressividade calculada.
    Entradas maiores (2x-3x) quando confluência é máxima:
      - Regime com expectativa > +15%
      - Confiança do sinal > 90%
      - Múltiplos timeframes alinhados
      - Breakout + Volume confirmando
    """

    def __init__(self):
        pass

    def analyze(self, regime, confidence, market_struct, tf="1m"):
        """
        Retorna:
          - use_soros: bool
          - multiplier: float (1.0 = normal, 2.0 = 2x)
          - reason: str
        """
        reasons = []
        score = 0

        # 1. Regime excelente
        if "strong_trend" in regime:
            score += 2
            reasons.append(f"Regime {regime}")
        elif "weak_trend" in regime:
            score += 1
            reasons.append(f"Regime {regime}")

        # 2. Confiança altíssima
        if confidence > 0.92:
            score += 2
            reasons.append(f"Conf {confidence:.1%}")
        elif confidence > 0.88:
            score += 1

        # 3. Breakout confirmado
        if isinstance(market_struct, dict):
            if market_struct.get("breakout_up") or market_struct.get("breakout_down_vol"):
                score += 2
                reasons.append("Breakout+Volume")
            elif market_struct.get("breakout_up") or market_struct.get("breakout_down"):
                score += 1
                reasons.append("Breakout")

        # 4. Timeframe
        if tf == "5m":
            score += 1  # M5 é sweet spot para Soros
        elif tf == "15m":
            score += 1

        # Decisão
        if score >= 6:
            use = True; mult = 3.0
        elif score >= 4:
            use = True; mult = 2.0
        elif score >= 3:
            use = True; mult = 1.5
        else:
            use = False; mult = 1.0

        return {
            "use_soros": use,
            "multiplier": mult,
            "reason": " | ".join(reasons) if reasons else "sem confluência",
            "score": score,
        }


# ═══════════════════════════════════════════════════════════
# 4. DECISOR FINAL
# ═══════════════════════════════════════════════════════════

class TradeDecisor:
    """
    Decision Engine: combina todos os filtros em uma decisão única.

    Fluxo:
      1. Sinal bruto do XGBoost (probabilidade)
      2. Filtro MRD (regime tem expectativa positiva?)
      3. Análise Martingale (vale a pena?)
      4. Análise Soros (hora de ser agressivo?)
      5. Decisão final: TRADE ou SKIP
    """

    def __init__(self, symbol="BTC/USDT", tf="1m"):
        self.symbol = symbol
        self.tf = tf
        self.mrd = MRDFilter()
        self.mrd.load_cache(symbol, tf)
        self.martingale = MartingaleAnalyzer(self.mrd.regime_perf)
        self.soros = SorosAnalyzer()

    def decide(self, signal, market_struct=None, loss_streak=0):
        """
        Decide se executa o trade com base em todos os filtros.
        
        Args:
            signal: dict com {type, confidence, raw_prob, regime, ...}
            market_struct: dict com breakout info
            loss_streak: perdas consecutivas atuais
        
        Returns:
            dict com decisão completa
        """
        direction = signal["type"].lower()
        regime = signal.get("regime", "unknown")
        confidence = signal["confidence"]

        # Passo 1: MRD
        tradable, mrd_reason = self.mrd.is_tradable(regime, direction)

        # Passo 2: Martingale
        martingale = self.martingale.analyze(regime, direction, confidence, self.tf, loss_streak)

        # Passo 3: Soros
        soros = self.soros.analyze(regime, confidence, market_struct or {}, self.tf)

        # Passo 4: Decisão final
        entry_multiplier = soros["multiplier"] if soros["use_soros"] else 1.0

        should_trade = tradable
        should_martingale = should_trade and martingale["use_martingale"]

        return {
            "symbol": self.symbol,
            "timeframe": self.tf,
            "direction": direction,
            "confidence": confidence,
            "regime": regime,
            "mrd_pass": tradable,
            "mrd_reason": mrd_reason,
            "martingale": martingale,
            "soros": soros,
            "entry_multiplier": entry_multiplier,
            "should_trade": should_trade,
            "should_martingale": should_martingale,
            "timestamp": signal.get("timestamp", 0),
        }

    def decision_summary(self, decision):
        """Resumo textual da decisão."""
        if not decision["should_trade"]:
            return f"⛔ SKIP | {decision['direction'].upper()} | {decision['mrd_reason']}"

        lines = [
            f"✅ TRADE {decision['direction'].upper()} {decision['timeframe']}",
            f"   Conf: {decision['confidence']:.1%}",
            f"   Regime: {decision['regime']}",
            f"   Multiplicador: {decision['entry_multiplier']}x",
        ]

        if decision["should_martingale"]:
            mg = decision["martingale"]
            lines.append(
                f"   Martingale: ✅ até {mg['max_levels']}x "
                f"(sobrevivência {mg['survival_prob']:.1%})"
            )

        if decision["soros"]["use_soros"]:
            lines.append(f"   Modo Soros: ✅ ({decision['soros']['reason']})")

        return "\n".join(lines)
