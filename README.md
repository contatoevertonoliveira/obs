# Hermes Quant V2 🤖📈

Sistema automatizado de trading para opções binárias com modelos XGBoost treinados em dados Quotex.

## Características

- **5 modelos viáveis** com expectativa positiva em dados Quotex
- **Análise multi-timeframe** (M1, M5, M15)
- **Spreads calibrados** por par e timeframe
- **Martingale** automático com 2 níveis
- **Paper trade** ao vivo na Quotex Demo
- **Suporte a 86+ pares** (cripto + forex OTC)

## Modelos Ativos

| Setup | Ativo | TF | Sinal | WR | Trades | Expectativa |
|-------|-------|:--:|:-----:|:--:|:-----:|:----------:|
| BNB M5 call_5 | BNBUSD_otc | M5 | CALL 5 | 69.6% | 23 | +25.2% |
| BRLUSD M1 put_5 | BRLUSD_otc | M1 | PUT 5 | 63.6% | 11 | +14.5% |
| BTC M15 call_1 | BTCUSD_otc | M15 | CALL 1 | 63.2% | 19 | +13.7% |
| GBPJPY M15 call_5 | GBPJPY_otc | M15 | CALL 5 | 62.1% | 66 | +11.8% |
| LTC M15 call_1 | LTCUSD_otc | M15 | CALL 1 | 58.8% | 17 | +5.9% |

## Estrutura

```
src/
├── papertrade_quotex.py   # Paper trade ao vivo na Quotex
├── collect_quotex_data.py # Coleta de dados históricos
├── process_quotex_v2_all.py # Processamento de features
├── train_quotex_v2.py     # Treinamento XGBoost
├── backtest_quotex_models.py # Backtest
└── analyze_volatility.py  # Análise de volatilidade

config/
└── quotex_spreads.json    # Spreads calibrados por par/TF
```

## Requisitos

- Python 3.12+
- PyQuotex (WebSocket)
- XGBoost, pandas, numpy, ta (biblioteca técnica)
- Conta demo Quotex

## Como usar

```bash
# Coletar dados
python3 src/collect_quotex_data.py

# Processar features
python3 src/process_quotex_v2_all.py

# Treinar modelos
python3 src/train_quotex_v2.py

# Rodar paper trade
QUOTEX_EMAIL="seu@email.com" QUOTEX_PASSWORD="sua_senha" \
  python3 src/papertrade_quotex.py
```
