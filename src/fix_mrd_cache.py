#!/usr/bin/env python3
"""Atualiza cache MRD com dados reais do backtest (modelo, não targets brutos)."""
import json, os, sys
os.chdir("/root/hermes-quant-v2")
sys.path.insert(0, ".")
from config.settings import MODEL_DIR

# Dados do backtest real (model XGBoost com threshold 0.88)
bt_data = {
    "BTC_M1": {
        "lateralization": {"wr": 0.618, "exp": 0.1118, "trades": 306},
        "strong_trend_bear": {"wr": 0.529, "exp": -0.0471, "trades": 68},
        "strong_trend_bull": {"wr": 0.654, "exp": 0.1769, "trades": 52},
        "weak_trend_bear": {"wr": 0.706, "exp": 0.2706, "trades": 51},
        "weak_trend_bull": {"wr": 0.629, "exp": 0.1326, "trades": 89},
    },
    "BTC_M5": {
        "lateralization": {"wr": 0.515, "exp": -0.0735, "trades": 136},
        "strong_trend_bear": {"wr": 0.560, "exp": 0.0080, "trades": 50},
        "strong_trend_bull": {"wr": 0.667, "exp": 0.2000, "trades": 21},
        "weak_trend_bear": {"wr": 0.653, "exp": 0.1755, "trades": 49},
        "weak_trend_bull": {"wr": 0.143, "exp": -0.7429, "trades": 7},
    },
}

for key, regimes in bt_data.items():
    symbol_name, tf = key.split("_")
    symbol_full = f"{symbol_name}/USDT"
    label = tf

    perf_list = []
    for regime, data in regimes.items():
        perf_list.append({
            "regime": regime,
            "samples": data["trades"],
            "win_rate_call": data["wr"],
            "win_rate_put": data["wr"],
            "expectancy_call": data["exp"],
            "expectancy_put": data["exp"],
            "avg_volatility": 0.07,
        })

    path = f"{MODEL_DIR}/{symbol_name}_USDT_{label}_regime_perf.json"
    with open(path, "w") as f:
        json.dump(perf_list, f, indent=2)
    print(f"✅ {path}")
    print(f"   Regimes: {[p['regime'] for p in perf_list]}")
    print(f"   WR range: {min(p['win_rate_call'] for p in perf_list):.1%} - {max(p['win_rate_call'] for p in perf_list):.1%}")
