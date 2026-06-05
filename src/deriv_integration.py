"""
Hermes Quant V2 — Deriv Integration
API oficial Deriv (WebSocket JSON-RPC)
Documentacao: https://developers.deriv.com/
VENV: source venv_deriv/bin/activate
"""
import os, sys, json, asyncio, time
from datetime import datetime
import pandas as pd

# ─── CONFIG ───
DERIV_TOKEN = os.environ.get("DERIV_API_TOKEN", "")
DERIV_APP_ID = os.environ.get("DERIV_APP_ID", "1089")  # 1089 = dev default
DERIV_WS_URL = f"wss://ws.deriv.com/websockets/v3?app_id={DERIV_APP_ID}"

# Ativos padrao (mapeamento Hermes -> Deriv)
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

# Contratos suportados pela Deriv (opcoes binarias)
CONTRACT_MAP = {
    "CALL": "call",      # Alta
    "PUT": "put",        # Baixa
    "RISE": "risefall",  # Sobe/Desce
    "FALL": "risefall",
}

class DerivIntegration:
    """
    Cliente Deriv API para Hermes Quant V2.
    Usa WebSocket oficial da Deriv (JSON-RPC).

    Uso:
        from src.deriv_integration import DerivIntegration
        d = DerivIntegration("seu_token_aqui")
        await d.connect()
        bal = await d.get_balance()
        ticks = await d.get_ticks("EURUSD", count=100)
        proposal = await d.get_proposal("EURUSD", "call", 1, 10)
        contract_id = await d.buy(proposal["id"], 10)
        await d.disconnect()
    """

    def __init__(self, token: str = None, app_id: str = None):
        self.token = token or DERIV_TOKEN
        self.app_id = app_id or DERIV_APP_ID
        self.ws_url = f"wss://ws.deriv.com/websockets/v3?app_id={self.app_id}"
        self.ws = None
        self.connected = False
        self.authorized = False
        self._req_id = 0
        self._pending = {}  # req_id -> Future

    async def connect(self) -> bool:
        """Conecta e autoriza na Deriv."""
        import websockets

        try:
            self.ws = await websockets.connect(self.ws_url, ping_interval=30)
            self.connected = True
            print(f"  ✅ Conectado Deriv WebSocket")

            if self.token:
                auth_ok = await self.authorize(self.token)
                self.authorized = auth_ok
                if auth_ok:
                    print(f"  ✅ Autorizado na Deriv")
                else:
                    print(f"  ❌ Falha na autorizacao")
            return True
        except Exception as e:
            print(f"  ❌ Erro conexao Deriv: {e}")
            self.connected = False
            return False

    async def authorize(self, token: str) -> bool:
        """Autoriza com token de API."""
        result = await self._send({"authorize": token})
        if result and "authorize" in result:
            self.authorized = True
            return True
        return False

    async def ping(self) -> bool:
        """Ping para manter conexao viva."""
        result = await self._send({"ping": 1})
        return result is not None

    async def get_balance(self) -> dict:
        """Retorna saldo da conta."""
        if not self.authorized:
            return None
        result = await self._send({"balance": 1})
        if result and "balance" in result:
            return result["balance"]
        return None

    async def get_active_symbols(self) -> list:
        """Lista simbolos/ativos disponiveis."""
        result = await self._send({"active_symbols": "brief"})
        if result and "active_symbols" in result:
            return result["active_symbols"]
        return []

    async def get_ticks(self, symbol: str, count: int = 100) -> list:
        """Obtem ticks historicos."""
        result = await self._send({
            "ticks_history": symbol,
            "end": "latest",
            "count": count,
            "style": "ticks"
        })
        if result and "history" in result:
            return result["history"]["prices"]
        return []

    async def get_candles(self, symbol: str, granularity: int = 60,
                          count: int = 100) -> pd.DataFrame:
        """
        Obtem velas OHLC.
        granularity: 60=1m, 300=5m, 900=15m, 3600=1h, 86400=1d
        """
        result = await self._send({
            "ticks_history": symbol,
            "end": "latest",
            "count": count,
            "style": "candles",
            "granularity": granularity
        })
        if result and "candles" in result:
            candles = []
            for c in result["candles"]:
                candles.append({
                    "timestamp": c["epoch"],
                    "open": float(c["open"]),
                    "high": float(c["high"]),
                    "low": float(c["low"]),
                    "close": float(c["close"]),
                    "volume": int(c.get("volume", 0))
                })
            df = pd.DataFrame(candles)
            df["datetime"] = pd.to_datetime(df["timestamp"], unit="s")
            return df
        return pd.DataFrame()

    async def get_proposal(self, symbol: str, direction: str,
                           duration: int = 1, amount: float = 10) -> dict:
        """
        Obtem proposta (cotacao) para uma opcao binaria.
        symbol: "EURUSD"
        direction: "call" ou "put"
        duration: minutos (1, 5, 15, etc)
        amount: valor em USD
        """
        if not self.authorized:
            return None
        result = await self._send({
            "proposal": 1,
            "amount": amount,
            "basis": "stake",
            "contract_type": direction.upper(),
            "currency": "USD",
            "duration": duration,
            "duration_unit": "m",
            "symbol": symbol
        })
        return result

    async def buy(self, proposal_id: int, price: float) -> dict:
        """
        Executa compra de um contrato.
        proposal_id: id retornado por get_proposal
        price: valor a pagar
        """
        if not self.authorized:
            return None
        result = await self._send({
            "buy": proposal_id,
            "price": price
        })
        return result

    async def get_portfolio(self) -> list:
        """Lista contratos abertos."""
        if not self.authorized:
            return []
        result = await self._send({"portfolio": 1})
        if result and "portfolio" in result:
            return result["portfolio"]["contracts"]
        return []

    async def get_profit_table(self) -> list:
        """Historico de lucros/perdas."""
        if not self.authorized:
            return []
        result = await self._send({"profit_table": 1})
        if result and "profit_table" in result:
            return result["profit_table"]
        return []

    async def _send(self, msg: dict) -> dict:
        """Envia mensagem JSON-RPC e aguarda resposta."""
        if not self.ws:
            return None

        self._req_id += 1
        msg["req_id"] = self._req_id

        try:
            await self.ws.send(json.dumps(msg))
            resp = await asyncio.wait_for(self.ws.recv(), timeout=15)
            data = json.loads(resp)

            # Verificar se tem erro
            if "error" in data:
                print(f"  ⚠️ Deriv error: {data['error'].get('message', str(data['error']))}")
                return None

            # Se for subscribe, tem que ler ate o "forget"
            # Para chamadas simples, o padrao e o echo do msg_type
            return data

        except asyncio.TimeoutError:
            print(f"  ⚠️ Deriv timeout req #{self._req_id}")
            return None
        except Exception as e:
            print(f"  ⚠️ Deriv send error: {e}")
            return None

    async def disconnect(self):
        """Desconecta."""
        if self.ws:
            await self.ws.close()
        self.connected = False
        self.authorized = False

    def asset_map(self, hermes_asset: str) -> str:
        """Mapeia nome Hermes -> Deriv."""
        return ASSET_MAP.get(hermes_asset, hermes_asset)

    def tf_to_seconds(self, tf: str) -> int:
        """Converte 'M1', 'M5', 'M15' -> segundos."""
        tf_map = {"M1": 60, "M5": 300, "M15": 900, "M30": 1800,
                  "H1": 3600, "H4": 14400, "D1": 86400}
        return tf_map.get(tf, 60)
