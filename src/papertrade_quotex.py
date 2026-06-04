#!/usr/bin/env python3.12
"""
Hermes Quant V2 — Paper Trade AO VIVO na Quotex DEMO.
Escaneia 5 modelos simultaneamente e executa CALL/PUT automaticamente.
"""
import os, sys, asyncio, json, csv, time
from datetime import datetime, timedelta
import pandas as pd
import numpy as np
import joblib

os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.getcwd())

# ─── CONFIG ───
QUOTEX_EMAIL = os.environ.get("QUOTEX_EMAIL", "")
QUOTEX_PASSWORD = os.environ.get("QUOTEX_PASSWORD", "")
MODEL_DIR = "models/quotex_v2"
LOG_DIR = "logs/papertrade"
os.makedirs(LOG_DIR, exist_ok=True)

LOG_FILE = f"{LOG_DIR}/papertrade_{datetime.now().strftime('%Y%m%d_%H%M')}.csv"
BALANCE_FILE = f"{LOG_DIR}/balance_history.csv"

# ─── SETUPS ATIVOS ───
SETUPS = [
    # (nome, asset_code, tf, target, threshold, stake%, martingale)
    ("BNB_M5_call_5",     "BNBUSD_otc", 300, "call_5", 0.70, 2.0, True),
    ("GBPJPY_M15_call_5", "GBPJPY_otc", 900, "call_5", 0.70, 1.5, True),
    ("BTC_M15_call_1",    "BTCUSD_otc", 900, "call_1", 0.70, 1.5, False),
    ("BRLUSD_M1_put_5",   "BRLUSD_otc", 60,  "put_5",  0.70, 1.0, False),
    ("LTC_M15_call_1",    "LTCUSD_otc", 900, "call_1", 0.65, 1.0, False),
]

# Tempo de espera entre scans (segundos)
SCAN_INTERVAL = {"60": 10, "300": 30, "900": 45}  # M1, M5, M15
MAX_RUNTIME = 30 * 60  # 30 minutos

MARTINGALE_MULT = [1.0, 2.5, 6.0]

class PaperTrader:
    def __init__(self, client):
        self.client = client
        self.balance = 0.0
        self.trades_log = []
        self.balance_log = []
        self.martingale_level = {}  # setup_name -> level
        self.last_trade_time = {}   # setup_name -> timestamp
        self.streak_loss = {}       # setup_name -> consecutive losses
        
        # Carregar modelos
        self.models = {}
        self.load_models()
        
        # Inicializar log
        with open(LOG_FILE, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["timestamp", "setup", "direction", "confidence",
                            "stake", "martingale_level", "result", "balance_after",
                            "duration_sec", "entry_price", "exit_price"])
        
        # Inicializar balance history
        if not os.path.exists(BALANCE_FILE):
            with open(BALANCE_FILE, "w", newline="") as f:
                writer = csv.writer(f)
                writer.writerow(["timestamp", "balance", "change_pct"])
    
    def load_models(self):
        for setup in SETUPS:
            name = setup[0]
            parts = name.split("_")
            ativo = parts[0]
            tf = parts[1]
            target = "_".join(parts[2:])
            
            # Procurar modelo no diretorio
            dir_path = f"{MODEL_DIR}/{ativo}_{tf}"
            model_file = f"{dir_path}/{target}.json"
            
            if os.path.exists(model_file):
                try:
                    model = joblib.load(model_file)
                    self.models[name] = model
                    self.martingale_level[name] = 0
                    self.streak_loss[name] = 0
                    self.last_trade_time[name] = 0
                    print(f"  ✅ Modelo carregado: {name}")
                except Exception as e:
                    print(f"  ❌ Erro ao carregar {name}: {e}")
            else:
                print(f"  ⚠️ Modelo nao encontrado: {model_file}")
        
        print(f"  📊 {len(self.models)}/{len(SETUPS)} modelos carregados")
    
    async def update_balance(self):
        try:
            self.balance = await self.client.get_balance()
            return self.balance
        except:
            return self.balance
    
    def get_features(self, name, df):
        """Extrai features no formato que o modelo espera."""
        if name not in self.models:
            return None
        
        model = self.models[name]
        if hasattr(model, "_feat_names"):
            feat_cols = model._feat_names
        elif hasattr(model, "feature_names_in_"):
            feat_cols = list(model.feature_names_in_)
        else:
            return None
        
        # Verificar se temos as colunas necessarias
        missing = [c for c in feat_cols if c not in df.columns]
        if missing:
            # Preencher colunas faltantes com 0
            for c in missing:
                df[c] = 0.0
        
        return df[feat_cols].fillna(0).iloc[-1:].values
    
    async def scan_and_trade(self):
        """Escaneia todos os setups e executa trades."""
        for setup in SETUPS:
            name, asset_code, period, target, threshold, stake_pct, use_martingale = setup
            direction = target.split("_")[0]  # "call" ou "put"
            
            # Verificar se modelo existe
            if name not in self.models:
                continue
            
            # Cooldown: evitar re-entradas no mesmo candle
            now = time.time()
            cooldown = max(SCAN_INTERVAL.get(str(period), 30), 60)
            if now - self.last_trade_time.get(name, 0) < cooldown:
                continue
            
            # Buscar candles recentes
            try:
                candles = await asyncio.wait_for(
                    self.client.get_historical_candles(
                        asset_code,
                        amount_of_seconds=period * 250,  # ~250 candles
                        period=period,
                        max_workers=3
                    ),
                    timeout=30
                )
            except:
                continue
            
            if not candles or len(candles) < 50:
                continue
            
            # Criar DataFrame e calcular features rapidas
            df = pd.DataFrame(candles)
            df.rename(columns={"time": "timestamp", "ticks": "volume"}, inplace=True)
            df["timestamp"] = pd.to_datetime(df["timestamp"], unit="s")
            df = df.sort_values("timestamp").reset_index(drop=True)
            
            # Features basicas
            df["return_1"] = df["close"].pct_change()
            df["return_5"] = df["close"].pct_change(5)
            df["return_10"] = df["close"].pct_change(10)
            df["range"] = (df["high"] - df["low"]) / df["close"]
            
            try:
                from ta.momentum import RSIIndicator
                from ta.trend import MACD, EMAIndicator, ADXIndicator
                from ta.volatility import BollingerBands, AverageTrueRange
                
                df["rsi_14"] = RSIIndicator(df["close"], 14).rsi()
                macd = MACD(df["close"])
                df["macd"] = macd.macd()
                df["macd_signal"] = macd.macd_signal()
                df["macd_hist"] = macd.macd_diff()
                
                for p in [7, 14, 21, 50]:
                    df[f"ema_{p}"] = EMAIndicator(df["close"], p).ema_indicator()
                    df[f"dist_ema_{p}"] = (df["close"] - df[f"ema_{p}"]) / df[f"ema_{p}"]
                
                bb = BollingerBands(df["close"])
                df["bb_width"] = (bb.bollinger_hband() - bb.bollinger_lband()) / df["close"]
                
                adx = ADXIndicator(df["high"], df["low"], df["close"])
                df["adx"] = adx.adx()
                df["plus_di"] = adx.adx_pos()
                df["minus_di"] = adx.adx_neg()
                
                df["atr_pct"] = AverageTrueRange(df["high"], df["low"], df["close"]).average_true_range() / df["close"]
                df["volatility_5"] = df["return_1"].rolling(5).std()
                df["volatility_10"] = df["return_1"].rolling(10).std()
            except:
                # Preencher features faltantes
                pass
            
            # Preencher NaN
            df = df.fillna(0)
            
            if len(df) < 20:
                continue
            
            # Fazer predicao
            X = self.get_features(name, df)
            if X is None:
                continue
            
            model = self.models[name]
            y_prob = model.predict_proba(X)[:, 1][0]
            
            # Inverter confianca se for PUT
            confidence = y_prob if direction == "call" else (1 - y_prob)
            
            if confidence < threshold:
                continue
            
            # EXECUTAR TRADE
            swing = MARTINGALE_MULT[self.martingale_level[name]] if use_martingale else 1.0
            stake = self.balance * stake_pct / 100 * swing
            stake = min(max(stake, 1.0), self.balance * 0.3)  # limites
            
            duration = period  # duracao em segundos
            
            print(f"\n  🎯 {name:25s} | conf={confidence:.1%} | stake=R${stake:.2f} | "
                  f"dir={direction.upper()} | nivel={self.martingale_level[name]}")
            
            try:
                success, result_data = await asyncio.wait_for(
                    self.client.buy(
                        amount=stake,
                        asset=asset_code,
                        direction=direction.upper(),
                        duration=duration,
                    ),
                    timeout=15
                )
                
                if not success:
                    print(f"     ❌ Ordem rejeitada: {result_data}")
                    continue
                
                print(f"     ✅ Ordem aceita: {result_data}")
                
                # Aguardar resultado (duracao do trade + margem)
                await asyncio.sleep(duration + 5)
                
                # Atualizar saldo
                old_balance = self.balance
                await self.update_balance()
                
                won = self.balance > old_balance
                
                if won:
                    self.martingale_level[name] = 0
                    self.streak_loss[name] = 0
                else:
                    self.martingale_level[name] = min(self.martingale_level[name] + 1, 2)
                    self.streak_loss[name] += 1
                
                self.last_trade_time[name] = time.time()
                
                entry_price = float(df["close"].iloc[-1])
                
                self.log_trade(name, direction, confidence, stake,
                              self.martingale_level[name] if not won else 0,
                              won, period, entry_price)
                
            except asyncio.TimeoutError:
                print(f"     ⏱️ Timeout na ordem")
            except Exception as e:
                print(f"     ❌ Erro: {str(e)[:60]}")
    
    def log_trade(self, name, direction, confidence, stake, mg_level, won, duration, entry_price):
        """Registra trade no CSV."""
        with open(LOG_FILE, "a", newline="") as f:
            writer = csv.writer(f)
            writer.writerow([
                datetime.now().isoformat(), name, direction,
                f"{confidence:.4f}", f"{stake:.2f}", mg_level,
                "WIN" if won else "LOSS", f"{self.balance:.2f}",
                duration, f"{entry_price:.5f}", ""
            ])
        
        # Balance history
        with open(BALANCE_FILE, "a", newline="") as f:
            writer = csv.writer(f)
            writer.writerow([datetime.now().isoformat(),
                           f"{self.balance:.2f}", ""])
        
        status = "✅ GANHOU" if won else "❌ PERDEU"
        print(f"     {status} | saldo=R$ {self.balance:.2f}")
    
    async def run(self):
        """Loop principal."""
        await self.update_balance()
        print(f"\n  💰 Saldo inicial: R$ {self.balance:.2f}")
        print(f"  📝 Log: {LOG_FILE}")
        print(f"  🔄 Iniciando scan...\n")
        
        scan_count = 0
        start_time = time.time()
        while time.time() - start_time < MAX_RUNTIME:
            try:
                scan_count += 1
                
                if scan_count % 10 == 0:
                    await self.update_balance()
                    print(f"\n  📊 Scan #{scan_count} | Saldo: R$ {self.balance:.2f}")
                    
                    # Relatorio periodico
                    if os.path.exists(LOG_FILE):
                        df_log = pd.read_csv(LOG_FILE)
                        if len(df_log) > 0:
                            wins = (df_log["result"] == "WIN").sum()
                            total = len(df_log)
                            wr = wins / total * 100 if total > 0 else 0
                            print(f"  📈 Trades: {total} | Wins: {wins} | WR: {wr:.1f}%")
                
                await self.scan_and_trade()
                await asyncio.sleep(10)  # scan a cada 10s
                
            except KeyboardInterrupt:
                print(f"\n\n  🛑 Paper trade encerrado!")
                break
            except Exception as e:
                print(f"  ⚠️ Erro no loop: {str(e)[:60]}")
                await asyncio.sleep(30)
    
async def main():
    from pyquotex.stable_api import Quotex
    
    print(f"{'='*60}")
    print(f"  🤖 HERMES QUANT V2 — PAPER TRADE")
    print(f"  {datetime.now().strftime('%d/%m/%Y %H:%M')} UTC")
    print(f"{'='*60}")
    print(f"  📡 Conectando Quotex...")
    
    client = Quotex(email=QUOTEX_EMAIL, password=QUOTEX_PASSWORD, lang="pt")
    await client.connect()
    
    trader = PaperTrader(client)
    await trader.run()
    
    await client.close()

if __name__ == "__main__":
    asyncio.run(main())
