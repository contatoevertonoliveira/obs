"""
Hermes Quant V2 — PocketOption Integration
Integração com PocketOption API (ByJhonesDev)
VENV: source venv_pocket/bin/activate
"""
import os, sys, asyncio, json
from datetime import datetime

# ─── CONFIG ───
SSID = os.environ.get("POCKET_SSID", "")
IS_DEMO = True

# Ativos padrao (mapeamento Hermes -> PocketOption)
ASSET_MAP = {
    "EURUSD": "EURUSD_otc",
    "GBPUSD": "GBPUSD_otc",
    "USDJPY": "USDJPY_otc",
    "USDCAD": "USDCAD_otc",
    "USDCHF": "USDCHF_otc",
    "GBPJPY": "GBPJPY_otc",
    "BTCUSD": "BTCUSD_otc",
    "ETHUSD": "ETHUSD_otc",
    "LTCUSD": "LTCUSD_otc",
    "BNBUSD": "BNBUSD_otc",
    "SOLUSD": "SOLUSD_otc",
}

TIMEFRAME_MAP = {
    60: "1m",
    300: "5m",
    900: "15m",
    1800: "30m",
    3600: "1h",
    14400: "4h",
    86400: "1d",
}

class PocketIntegration:
    """
    Cliente PocketOption para Hermes Quant V2.
    Uso:
        from src.pocketoption_integration import PocketIntegration
        pi = PocketIntegration(ssid)
        await pi.connect()
        bal = await pi.get_balance()
        candles = await pi.get_candles("EURUSD_otc", 60, 100)
        order = await pi.buy(1.0, "EURUSD_otc", "call", 60)
        await pi.disconnect()
    """

    def __init__(self, ssid: str = None, is_demo: bool = True):
        self.ssid = ssid or SSID
        self.is_demo = is_demo
        self.client = None
        self.connected = False

    async def connect(self):
        """Conecta na PocketOption."""
        from pocketoptionapi_async.client import AsyncPocketOptionClient

        self.client = AsyncPocketOptionClient(
            ssid=self.ssid,
            is_demo=self.is_demo,
            persistent_connection=True,
            auto_reconnect=True,
            enable_logging=False
        )
        self.connected = await self.client.connect()
        return self.connected

    async def get_balance(self):
        if not self.client:
            return None
        try:
            bal = await self.client.get_balance()
            return bal.balance if hasattr(bal, 'balance') else bal
        except:
            return None

    async def get_candles(self, asset: str, timeframe: int, count: int = 100):
        if not self.client:
            return None
        try:
            return await self.client.get_candles(asset, timeframe, count)
        except Exception as e:
            print(f"  ⚠️ Erro candles {asset}: {e}")
            return None

    async def buy(self, amount: float, asset: str, direction: str, duration: int):
        if not self.client:
            return None
        try:
            return await self.client.buy(amount, asset, direction, duration)
        except Exception as e:
            print(f"  ⚠️ Erro buy: {e}")
            return None

    async def disconnect(self):
        if self.client:
            await self.client.disconnect()
            self.connected = False

    def asset_map(self, hermes_asset: str) -> str:
        """Mapeia nome Hermes -> PocketOption."""
        return ASSET_MAP.get(hermes_asset, hermes_asset)

    def tf_to_seconds(self, tf: str) -> int:
        """Converte 'M1', 'M5', 'M15' -> segundos."""
        inv = {v: k for k, v in TIMEFRAME_MAP.items()}
        return inv.get(tf, 60)
