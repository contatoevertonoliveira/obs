"""
Hermes Quant V2 — IQOption Integration
Integração com IQOption API (Lu-Yi-Hsun/iqoptionapi)
VENV: source venv_iqoption/bin/activate
"""
import os, sys, time, json
from datetime import datetime

# ─── CONFIG ───
IQ_EMAIL = os.environ.get("IQOPTION_EMAIL", "")
IQ_PASSWORD = os.environ.get("IQOPTION_PASSWORD", "")
IS_DEMO = True  # PRACTICE = demo

# Ativos padrao (mapeamento Hermes -> IQOption)
ASSET_MAP = {
    "EURUSD": "EURUSD",
    "GBPUSD": "GBPUSD",
    "USDJPY": "USDJPY",
    "USDCAD": "USDCAD",
    "USDCHF": "USDCHF",
    "GBPJPY": "GBPJPY",
    "BTCUSD": "BTCUSD",
    "ETHUSD": "ETHUSD",
    "LTCUSD": "LTCUSD",
    "BNBUSD": "BNBUSD",
    "SOLUSD": "SOLUSD",
}

TIMEFRAME_MAP = {
    60: 60,
    300: 300,
    900: 900,
    1800: 1800,
    3600: 3600,
    14400: 14400,
    86400: 86400,
}

class IQIntegration:
    """
    Cliente IQOption para Hermes Quant V2.
    Uso:
        from src.iqoption_integration import IQIntegration
        iq = IQIntegration("email", "password")
        iq.connect()
        iq.set_demo()
        bal = iq.get_balance()
        candles = iq.get_candles("EURUSD", 60, 100)
        order_id = iq.buy(1.0, "EURUSD", "call", 1)
        result = iq.check_win(order_id)
        iq.disconnect()
    """

    def __init__(self, email: str = None, password: str = None):
        self.email = email or IQ_EMAIL
        self.password = password or IQ_PASSWORD
        self.api = None
        self.connected = False

    def connect(self) -> bool:
        """Conecta na IQOption."""
        from iqoptionapi.stable_api import IQ_Option

        self.api = IQ_Option(self.email, self.password)
        check, reason = self.api.connect()
        self.connected = check
        if check:
            print(f"  ✅ Conectado IQOption!")
            if IS_DEMO:
                self.api.change_balance("PRACTICE")
                print(f"  📊 Modo: DEMO (PRACTICE)")
        else:
            print(f"  ❌ Falha: {reason}")
        return check

    def set_demo(self):
        """Muda para conta DEMO (PRACTICE)."""
        if self.api:
            self.api.change_balance("PRACTICE")

    def set_real(self):
        """Muda para conta REAL."""
        if self.api:
            self.api.change_balance("REAL")

    def get_balance(self) -> float:
        """Retorna saldo atual."""
        if not self.api:
            return 0.0
        try:
            return self.api.get_balance()
        except:
            try:
                return self.api.get_balance_v2()
            except:
                return 0.0

    def get_candles(self, asset: str, timeframe: int = 60, count: int = 100):
        """Obtem velas OHLC."""
        if not self.api:
            return None
        try:
            return self.api.get_candles(asset, timeframe, count, time.time())
        except Exception as e:
            print(f"  ⚠️ Erro candles {asset}: {e}")
            return None

    def buy(self, amount: float, asset: str, direction: str, expiration: int = 1):
        """
        Compra opção binária.
        direction: "call" ou "put"
        expiration: minutos (1, 5, 15, etc)
        Retorna: (check: bool, order_id: int)
        """
        if not self.api:
            return False, None
        try:
            return self.api.buy(amount, asset, direction, expiration)
        except Exception as e:
            print(f"  ⚠️ Erro buy: {e}")
            return False, None

    def check_win(self, order_id: int, timeout: int = 10):
        """Verifica resultado de um trade."""
        if not self.api:
            return None
        try:
            return self.api.check_win_v3(order_id)
        except:
            try:
                return self.api.check_win_v2(order_id, timeout)
            except:
                return None

    def check_connect(self) -> bool:
        """Verifica se ainda está conectado."""
        if not self.api:
            return False
        return self.api.check_connect()

    def disconnect(self):
        """Desconecta."""
        if self.api:
            try:
                self.api.close()
            except:
                pass
        self.connected = False

    @staticmethod
    def asset_map(hermes_asset: str) -> str:
        """Mapeia nome Hermes -> IQOption."""
        return ASSET_MAP.get(hermes_asset, hermes_asset)

    @staticmethod
    def tf_to_seconds(tf: str) -> int:
        """Converte 'M1', 'M5', 'M15' -> segundos."""
        inv = {v: k for k, v in TIMEFRAME_MAP.items()}
        return inv.get(tf, 60)
