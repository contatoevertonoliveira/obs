"""Configurações do Hermes Quant V2 — Opções Binárias M1/M5/M15"""

# ═══════════════════════════════════════════════════
# ATIVOS
# ═══════════════════════════════════════════════════
SYMBOLS = [
    "BTC/USDT",
    "ETH/USDT",
    "SOL/USDT",
    "BNB/USDT",
    "XRP/USDT",
    "ADA/USDT",
    "DOGE/USDT",
    "LINK/USDT",
    "AVAX/USDT",
    "DOT/USDT",
]

# ═══════════════════════════════════════════════════
# TIMEFRAMES
# ═══════════════════════════════════════════════════
# Timeframes de entrada (para gerar sinais CALL/PUT)
INPUT_TFS = ["1m", "3m", "5m", "15m", "30m"]

# Timeframes de contexto macro (para filtrar sinais)
CONTEXT_TFS = ["1h", "4h"]

# Todos os timeframes combinados
ALL_TFS = INPUT_TFS + CONTEXT_TFS

# Label amigável
TF_LABEL = {"1m": "M1", "3m": "M3", "5m": "M5", "10m": "M10", "15m": "M15", "30m": "M30", "1h": "H1", "4h": "H4"}

# Duração em ms
TF_MS = {"1m": 60000, "3m": 180000, "5m": 300000, "10m": 600000, "15m": 900000, "30m": 1800000, "1h": 3600000, "4h": 14400000}

# ═══════════════════════════════════════════════════
# COLETA
# ═══════════════════════════════════════════════════
LIMIT = 1000                     # Candles por request (max Binance)
MIN_HISTORY_DAYS = 365 * 3       # 3 anos mínimo
PRIORITY_SYMBOLS = ["BTC/USDT", "ETH/USDT", "SOL/USDT"]  # Coletar primeiro

# ═══════════════════════════════════════════════════
# DIREÇÕES
# ═══════════════════════════════════════════════════
RAW_DIR = "data/raw"
PROCESSED_DIR = "data/processed"
CHECKPOINT_FILE = "data/raw/.checkpoints.json"
MODEL_DIR = "models"

# ═══════════════════════════════════════════════════
# ESTRATÉGIA — Opções Binárias
# ═══════════════════════════════════════════════════
# Exchanges alvo para execução
TARGET_EXCHANGES = ["IQOption", "Quotex", "PocketOption", "Deriv"]

# Janelas de previsão (em candles)
FORECAST_WINDOWS = {
    "1m":  1,   # Prever 1 candle à frente (expiração 1 min)
    "5m":  1,   # Prever 1 candle à frente (expiração 5 min)
    "10m": 1,   # Prever 1 candle à frente (expiração 10 min)
    "15m": 1,   # Prever 1 candle à frente (expiração 15 min)
}

# Meta de acerto mínima para entrada
MIN_CALL_PROB = 0.70   # 70%
MIN_PUT_PROB = 0.70    # 70%

# ═══════════════════════════════════════════════════
# TARGETS — Opções Binárias (ajustados)
# ═══════════════════════════════════════════════════
# Spread mínimo para considerar CALL/PUT (em %)
# Ex: 0.05 = 0.05% de movimento necessário
# M1 precisa de spread menor (pouco tempo), M5/M15 maior
TARGET_SPREAD_PCT = {
    "1m": 0.05,   # 0.05% (~US$30 no BTC)
    "3m": 0.08,   # 0.08%
    "5m": 0.10,   # 0.10%
    "15m": 0.15,  # 0.15%
    "30m": 0.20,  # 0.20%
}

# Multiplicador para targets multi-candle
TARGET_SPREAD_MULT = 1.5  # call_5: spread * 1.5

# Payload simulado (IQOption/Quotex padrão)
PAYOUT_RATE = 0.80  # 80% de retorno

# ═══════════════════════════════════════════════════
# USER SETTINGS (capital, cycles, API keys)
# ═══════════════════════════════════════════════════
import os, json

_USER_SETTINGS_PATH = os.path.join(os.path.dirname(__file__), "user_settings.json")

def load_user_settings():
    if os.path.exists(_USER_SETTINGS_PATH):
        try:
            with open(_USER_SETTINGS_PATH) as f:
                return json.load(f)
        except:
            pass
    return {}

USER_SETTINGS = load_user_settings()

# Capital
INITIAL_CAPITAL = USER_SETTINGS.get("capital", {}).get("initial", 100.0)
CURRENCY = USER_SETTINGS.get("capital", {}).get("currency", "BRL")

# Cycles
CYCLES = USER_SETTINGS.get("cycles", {})

def update_user_setting(key_path, value):
    """Atualiza uma configuração e salva."""
    settings = load_user_settings()
    keys = key_path.split(".")
    target = settings
    for k in keys[:-1]:
        target = target.setdefault(k, {})
    target[keys[-1]] = value
    with open(_USER_SETTINGS_PATH, "w") as f:
        json.dump(settings, f, indent=2)
    return settings
