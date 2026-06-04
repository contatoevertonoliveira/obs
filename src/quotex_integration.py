#!/usr/bin/env python3.12
"""
HERMES QUANT V2 — Integração Quotex
=====================================
Conecta na Quotex via WebSocket (PyQuotex)
- Baixa dados históricos
- Roda backtest com modelos treinados
- Executa trades (paper primeiro)

Uso:
  python3.12 src/quotex_integration.py backtest   → Backtest com dados Quotex
  python3.12 src/quotex_integration.py scan       → Escaneia sinais ao vivo
  python3.12 src/quotex_integration.py trade      → Executa trade manual
"""
import os, sys, json, asyncio, time
from datetime import datetime, timezone, timedelta
from pathlib import Path

# Add Hermes Quant to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# ═══════════════════════════════════════════════════════
# QUOTEX ASSET NAMES (mapear símbolos Binance → Quotex)
# ═══════════════════════════════════════════════════════
QUOTEX_ASSETS = {
    "BTC/USDT": "BTCUSD",   # Verificar nome exato
    "ETH/USDT": "ETHUSD",
    "SOL/USDT": "SOLUSD",
    "BNB/USDT": "BNBUSD",
    "XRP/USDT": "XRPUSD",
}

# Period em segundos (PyQuotex) → string TF
PERIOD_MAP = {60: "1m", 180: "3m", 300: "5m", 900: "15m", 1800: "30m", 3600: "1h"}
TF_TO_PERIOD = {"1m": 60, "3m": 180, "5m": 300, "15m": 900, "30m": 1800, "1h": 3600}

# ═══════════════════════════════════════════════════════
# CREDENCIAIS (preencher ou usar var ambiente)
# ═══════════════════════════════════════════════════════
QUOTEX_EMAIL = os.environ.get("QUOTEX_EMAIL", "")
QUOTEX_PASSWORD = os.environ.get("QUOTEX_PASSWORD", "")

LOG_FILE = "logs/quotex_integration.log"
os.makedirs("logs", exist_ok=True)

def log(msg):
    with open(LOG_FILE, "a") as f:
        f.write(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}\n")
    print(msg, flush=True)

# ═══════════════════════════════════════════════════════
# 1. CONEXÃO QUOTEX
# ═══════════════════════════════════════════════════════

async def connect_quotex(email=None, password=None, demo=True):
    """Conecta na Quotex e retorna o client."""
    email = email or QUOTEX_EMAIL
    password = password or QUOTEX_PASSWORD
    
    if not email or not password:
        log("  ❌ Credenciais não fornecidas. Configure QUOTEX_EMAIL e QUOTEX_PASSWORD")
        return None
    
    try:
        from pyquotex.stable_api import Quotex
        client = Quotex(email=email, password=password, lang="pt")
        check, msg = await client.connect()
        
        if not check:
            log(f"  ❌ Falha na conexão: {msg}")
            return None
        
        log(f"  ✅ Conectado à Quotex!")
        
        # Modo Demo
        if demo:
            from pyquotex.utils.account_type import AccountType
            await client.change_account(AccountType.DEMO, tournament_id=1)
            log(f"  🎮 Modo DEMO ativado")
        
        # Saldo
        balance = await client.get_balance()
        log(f"  💰 Saldo: {balance}")
        
        return client
    except Exception as e:
        log(f"  ❌ Erro conexão: {e}")
        return None

# ═══════════════════════════════════════════════════════
# 2. COLETA DE DADOS HISTÓRICOS
# ═══════════════════════════════════════════════════════

async def fetch_quotex_data(client, asset, tf, hours=48):
    """Baixa dados históricos da Quotex para backtest."""
    period = TF_TO_PERIOD.get(tf, 60)
    amount_seconds = hours * 3600
    
    log(f"  📥 Baixando {asset} {tf} ({hours}h)...")
    
    try:
        candles = await client.get_historical_candles(
            asset,
            amount_of_seconds=amount_seconds,
            period=period,
            max_workers=5
        )
        
        if not candles:
            log(f"  ⚠ Sem dados retornados")
            return None
        
        log(f"  ✅ {len(candles)} candles recebidos")
        return candles
    except Exception as e:
        log(f"  ❌ Erro ao buscar dados: {e}")
        return None

# ═══════════════════════════════════════════════════════
# 3. BACKTEST COM DADOS QUOTEX
# ═══════════════════════════════════════════════════════

async def run_backtest(client):
    """Backtest: usa dados Quotex para validar modelos treinados."""
    from config.settings import MODEL_DIR, PROCESSED_DIR
    import pandas as pd
    import numpy as np
    import joblib
    
    log("=" * 55)
    log("  🧪 BACKTEST — DADOS QUOTEX")
    log("=" * 55)
    
    # Setups ativos que vamos testar
    setups = [
        ("BTC/USDT", "1m", 0.70),
        ("ETH/USDT", "5m", 0.65),
    ]
    
    for symbol, tf, threshold in setups:
        asset = QUOTEX_ASSETS.get(symbol, symbol.split("/")[0])
        sym_key = symbol.replace("/", "_")
        label_map = {"1m": "M1", "3m": "M3", "5m": "M5", "15m": "M15", "30m": "M30"}
        label = label_map.get(tf, tf.upper())
        
        # 1. Baixar dados da Quotex
        candles = await fetch_quotex_data(client, asset, tf, hours=48)
        if not candles or len(candles) < 100:
            log(f"  ⚠ {symbol} {tf}: dados insuficientes")
            continue
        
        # 2. Preparar dados (formato igual ao processado)
        df = pd.DataFrame(candles, columns=["timestamp", "open", "high", "low", "close", "volume"])
        df["datetime"] = pd.to_datetime(df["timestamp"], unit="ms")
        df = df.drop_duplicates(subset=["timestamp"]).sort_values("timestamp").reset_index(drop=True)
        
        # 3. Carregar modelo treinado
        models = {}
        for target in ["call_1", "put_1", "call_5", "put_5"]:
            path = f"{MODEL_DIR}/{sym_key}_{label}_{target}_xgb.json"
            if os.path.exists(path):
                try:
                    models[target] = joblib.load(path)
                except:
                    pass
        
        if not models:
            log(f"  ⚠ {symbol} {tf}: sem modelos")
            continue
        
        # 4. Calcular features (mesmo pipeline)
        from ta.momentum import RSIIndicator, StochasticOscillator
        from ta.trend import MACD, EMAIndicator, ADXIndicator, CCIIndicator
        from ta.volatility import BollingerBands, AverageTrueRange
        from ta.volume import OnBalanceVolumeIndicator
        
        for c in ["open", "high", "low", "close", "volume"]:
            if c not in df.columns: df[c] = df[c.upper()]
        
        df["returns"] = df["close"].pct_change()
        # ... features resumidas para agilizar
        for p in [7, 14, 21]:
            df[f"ema_{p}"] = EMAIndicator(df["close"], p).ema_indicator()
            df[f"rsi_{p}"] = RSIIndicator(df["close"], p).rsi()
        
        macd = MACD(df["close"])
        df["macd"] = macd.macd()
        df["macd_signal"] = macd.macd_signal()
        df["macd_diff"] = macd.macd_diff()
        
        bb = BollingerBands(df["close"])
        df["bb_width"] = (bb.bollinger_hband() - bb.bollinger_lband()) / df["close"]
        
        adx = ADXIndicator(df["high"], df["low"], df["close"])
        df["adx"] = adx.adx()
        df["plus_di"] = adx.adx_pos()
        df["minus_di"] = adx.adx_neg()
        df["di_spread"] = abs(df["plus_di"] - df["minus_di"])
        
        atr = AverageTrueRange(df["high"], df["low"], df["close"])
        df["atr_pct"] = atr.average_true_range() / df["close"]
        
        # 5. Targets (os mesmos do treino)
        spreads = {"1m": 0.0005, "3m": 0.0008, "5m": 0.0010, "15m": 0.0015, "30m": 0.0020}
        spread = spreads.get(tf, 0.001)
        df["target_call"] = ((df["close"].shift(-1) - df["close"]) / df["close"] > spread).astype(int)
        df["target_put"] = ((df["close"] - df["close"].shift(-1)) / df["close"] > spread).astype(int)
        
        # 6. Features para predição
        drop_cols = ["timestamp", "datetime", "target_call", "target_put"]
        feature_cols = [c for c in df.columns if c not in drop_cols 
                        and not c.startswith("target_")
                        and df[c].dtype in ["float64", "float32", "int64", "int32"]]
        
        # Remover NaN
        mask = df[feature_cols].isna().any(axis=1) | df["target_call"].isna()
        df = df[~mask].copy()
        
        if len(df) < 50:
            log(f"  ⚠ {symbol} {tf}: poucos dados após limpeza ({len(df)})")
            continue
        
        # 7. Predizer e comparar
        X = df[feature_cols].values
        trades = []
        
        for model_key, model in models.items():
            target_dir = "call" if "call" in model_key else "put"
            target_col = f"target_{target_dir}"
            
            if target_col not in df.columns:
                continue
            
            y_prob = model.predict_proba(X)[:, 1]
            confs = y_prob if target_dir == "call" else (1 - y_prob)
            
            for i in range(len(df)):
                conf = confs[i]
                if conf < threshold:
                    continue
                
                actual = df[target_col].iloc[i]
                won = actual == 1
                trades.append({
                    "timestamp": int(df["timestamp"].iloc[i]),
                    "type": target_dir.upper(),
                    "confidence": float(conf),
                    "actual": int(actual),
                    "won": bool(won),
                    "model": model_key,
                })
        
        # 8. Resultados
        if not trades:
            log(f"  📊 {symbol:10s} {tf:4s} | 0 trades (threshold {threshold})")
            continue
        
        df_t = pd.DataFrame(trades)
        total = len(df_t)
        wins = df_t["won"].sum()
        wr = wins / total
        payout = 0.80
        exp = (wr * payout) - ((1 - wr) * 1)
        
        log(f"  📊 {symbol:10s} {tf:4s} | {total:>5d} trades | WR {wr:.1%} | Exp {exp:.2%} | {'✅' if exp > 0 else '❌'}")
        
        # Por modelo
        for model, group in df_t.groupby("model"):
            g_wr = group["won"].mean()
            g_exp = (g_wr * payout) - ((1 - g_wr) * 1)
            log(f"      {model:10s}: {len(group):>4d} trades | WR {g_wr:.1%} | Exp {g_exp:.2%} | {'✅' if g_exp > 0 else '❌'}")
        
        # Salvar resultados
        out_dir = f"backtest/quotex"
        os.makedirs(out_dir, exist_ok=True)
        df_t.to_csv(f"{out_dir}/{sym_key}_{label}_backtest.csv", index=False)
        log(f"      💾 Salvo: {out_dir}/{sym_key}_{label}_backtest.csv")
    
    log("=" * 55)
    log("  ✅ BACKTEST CONCLUÍDO")
    log("=" * 55)

# ═══════════════════════════════════════════════════════
# 4. MAIN
# ═══════════════════════════════════════════════════════

async def main():
    action = sys.argv[1] if len(sys.argv) > 1 else "backtest"
    
    if action == "backtest":
        client = await connect_quotex()
        if client:
            await run_backtest(client)
            await client.close()
    
    elif action == "scan":
        client = await connect_quotex()
        if client:
            await scan_signals(client)
            await client.close()
    
    elif action == "login_only":
        client = await connect_quotex()
        if client:
            log(f"  ✅ Login OK! Pronto para operar")
            await client.close()
    
    else:
        log(f"  Uso: python3.12 src/quotex_integration.py [backtest|scan|login_only]")

if __name__ == "__main__":
    asyncio.run(main())
