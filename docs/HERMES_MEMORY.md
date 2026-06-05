# 🧠 HERMES QUANT V2 — Dump Completo de Memória e Expertise

> **Gerado em:** 05/06/2026
> **Propósito:** Replicar todo o conhecimento, configurações e memórias do assistente OB para o ambiente local do usuário.
> **Instruções:** Colocar este arquivo no ambiente local e referenciar para que o Hermes local carregue todo o contexto.

---

## 👤 PERFIL DO USUÁRIO

| Campo | Valor |
|-------|-------|
| **Nome** | Everton Oliveira |
| **Idioma** | PT-BR (comunicação direta, sem rodeios) |
| **Perfil** | Desenvolvedor e trader de opções binárias |
| **Estilo** | Prefere ação a teoria ("manda bala") |
| **Plataformas** | Telegram (DM) |

### Trader Persona

- **Opera:** IQOption, Quotex, PocketOption, Deriv
- **Timeframes principais:** M1 (principal), M5, M15
- **Timeframes contexto:** H1, H4 (só contexto superior)
- **Filosofia:** Mercado é fractal — entrada M1 validada por contexto H4→H1→M15→M5→M1
- **Qualidade > Quantidade:** 5 trades de alta confiança > 20 de baixa
- **Filtro obrigatório:** Market Regime Detection (regime-based trading)
- **Gosta de:** Métricas concretas, dashboards visuais, passo a passo sequencial
- **Meta financeira:** R$100 → R$50.000 via 4 ciclos (Seed → Growth → Scale → Legacy)

---

## 🏗️ PROJETO: HERMES QUANT V2

| Item | Valor |
|------|-------|
| **Repositório** | https://github.com/contatoevertonoliveira/obs |
| **Branch** | master |
| **Tamanho** | ~575 MB |
| **Local original** | `/root/hermes-quant-v2/` |
| **Licença** | MIT |

### Estrutura de diretórios

```
hermes-quant-v2/
├── src/                      # Scripts Python
│   ├── papertrade_quotex.py  # Paper trade ao vivo (Quotex)
│   ├── train_quotex_v2.py    # Treinamento XGBoost
│   ├── process_quotex_v2_all.py  # Processamento V2
│   ├── collect_quotex_data.py    # Coleta de dados
│   ├── collect_more_pairs.py     # +19 pares
│   ├── analyze_volatility.py     # Análise volatilidade
│   ├── backtest_quotex_models.py # Backtest
│   ├── dashboard.py              # Dashboard interativo
│   ├── quotex_integration.py     # Classe Quotex
│   ├── pocketoption_integration.py  # Classe PocketOption
│   ├── iqoption_integration.py      # Classe IQOption
│   └── deriv_integration.py         # Classe Deriv
├── config/
│   ├── quotex_spreads.json     # Spreads calibrados
│   ├── active_setups.json      # Setups ativos
│   ├── user_settings.json      # Configurações usuário
│   └── exchanges.env           # Credenciais (IGNORADO pelo git)
├── models/quotex_v2/           # 299 modelos XGBoost (~119MB)
├── data/
│   ├── raw/quotex/             # 86 pares, 315k candles (~166MB)
│   └── processed/quotex_v2/    # Features + targets (~289MB)
├── logs/papertrade/            # Logs do paper trade
├── restore.sh                  # Script de restore automático
├── backup_snapshot.json        # Snapshot completo do projeto
└── docs/HERMES_MEMORY.md       # ← ESTE ARQUIVO
```

---

## 🔌 EXCHANGES CONFIGURADAS

### 1. Quotex ✅ (Principal)

| Item | Detalhe |
|------|---------|
| **Biblioteca** | `pyquotex` |
| **Venv** | `venv_quotex` |
| **Autenticação** | email + senha |
| **Arquivo** | `src/quotex_integration.py` |
| **Classe** | `QuotexIntegration` (dentro do papertrade) |
| **Status** | Funcional, IP bloqueado no VPS (HTTP 429) |

**Credenciais:**
```
QUOTEX_EMAIL="averdadesemfim@gmail.com"
QUOTEX_PASSWORD="Eve@91253425"
```

**Uso básico:**
```python
from pyquotex.stable_api import Quotex
client = Quotex(email, password, lang="pt")
await client.connect()
balance = await client.get_balance()
```

### 2. PocketOption ⏸️

| Item | Detalhe |
|------|---------|
| **Biblioteca** | `ByJhonesDev/PocketOptionAPI` (git) |
| **Venv** | `venv_pocket` |
| **Autenticação** | SSID (Socket.IO auth string do navegador) |
| **Arquivo** | `src/pocketoption_integration.py` |
| **Classe** | `PocketIntegration` |

**Como obter SSID:**
1. Abrir PocketOption DEMO no navegador
2. F12 → Network → filtro WS
3. Recarregar página (F5)
4. Clicar na conexão WebSocket
5. Aba Messages → copiar mensagem `42["auth",{...}]`

**Uso básico:**
```python
from src.pocketoption_integration import PocketIntegration
pi = PocketIntegration(ssid="42[\"auth\",{...}]")
await pi.connect()
bal = await pi.get_balance()
```

### 3. IQOption ✅ (Falta senha)

| Item | Detalhe |
|------|---------|
| **Biblioteca** | `Lu-Yi-Hsun/iqoptionapi` (git) |
| **Venv** | `venv_iqoption` |
| **Autenticação** | email + senha |
| **Arquivo** | `src/iqoption_integration.py` |
| **Classe** | `IQIntegration` |

**Credenciais:**
```
IQOPTION_EMAIL="averdadesemfim@gmail.com"
IQOPTION_PASSWORD=""  # ← PENDENTE: usuário precisa preencher
```

**Uso básico:**
```python
from src.iqoption_integration import IQIntegration
iq = IQIntegration(email, password)
iq.connect()  # Síncrono
iq.set_demo()  # Muda pra conta DEMO
bal = iq.get_balance()
```

**API:**
```python
iq.buy(amount, asset, direction, expiration)  # direction="call"/"put"
iq.get_candles(asset, timeframe, count)       # timeframe=60 (M1)
iq.check_win_v3(order_id)
iq.change_balance("PRACTICE")  # Demo
iq.change_balance("REAL")      # Real
```

### 4. Deriv ✅ (Falta token)

| Item | Detalhe |
|------|---------|
| **Biblioteca** | WebSocket direto (websockets) |
| **Venv** | `venv_deriv` |
| **Autenticação** | PAT (Personal Access Token) |
| **Arquivo** | `src/deriv_integration.py` |
| **Classe** | `DerivIntegration` |
| **App ID** | `1089` (dev default) |

**Como obter token:**
1. https://app.deriv.com → Settings → API Token
2. Create → escopo: Read + Trade

**Uso básico:**
```python
from src.deriv_integration import DerivIntegration
d = DerivIntegration(token="seu_token_aqui")
await d.connect()
bal = await d.get_balance()
df = await d.get_candles("EURUSD", 60, 100)  # Pandas DataFrame
proposal = await d.get_proposal("EURUSD", "call", 1, 10)
contract = await d.buy(proposal["id"], 10)
await d.disconnect()
```

---

## 🎯 MODELOS ATIVOS (5 VIÁVEIS)

### Top 5 — Threshold 0.70

| # | Setup | Par | TF | Sinal | WR | Trades | Stake | Martingale |
|:-:|:---|---|:---:|:---:|:---:|:---:|:---:|:---:|
| 1 | **BNB_M5_call_5** 🥇 | BNBUSD_otc | M5 | CALL 5min | **69.6%** | 23 | 2.0% | ✅ |
| 2 | **BRLUSD_M1_put_5** 🥈 | BRLUSD_otc | M1 | PUT 5min | **63.6%** | 11 | 1.0% | ❌ |
| 3 | **BTC_M15_call_1** 🥉 | BTCUSD_otc | M15 | CALL 1min | **63.2%** | 19 | 1.5% | ❌ |
| 4 | **GBPJPY_M15_call_5** | GBPJPY_otc | M15 | CALL 5min | **62.1%** | 66 | 1.5% | ✅ |
| 5 | **LTC_M15_call_1** | LTCUSD_otc | M15 | CALL 1min | **58.8%** | 17 | 1.0% | ❌ |

### Estrutura dos modelos

```
models/quotex_v2/BNB_M5/
├── call_1.json    → CALL 1 minuto
├── call_5.json    → CALL 5 minutos
├── put_1.json     → PUT 1 minuto
└── put_5.json     → PUT 5 minutos
```

**Total:** 77 pastas (par+TF) × 4 modelos = ~299 modelos XGBoost
- Parâmetros: 200 iterações, max_depth=5, scale_pos_weight
- Formato: joblib (`.json`)

### Ativos cobertos (86 pares)

| Categoria | Pares | Qtd |
|-----------|-------|:---:|
| 🪙 Cripto OTC | BTC, ETH, SOL, LTC, BNB | 5 |
| 💱 Forex OTC | EUR, JPY, GBP, CHF, CAD | 5 |
| 🔄 Forex Cross | EURJPY, EURGBP, GBPJPY, AUDUSD, NZDUSD, EURAUD, EURCAD, GBPAUD, GBPCAD, AUDJPY, CADJPY, CHFJPY, AUDCAD, BRLUSD | 14 |
| 📊 Forex Normal | EURUSD_N, USDJPY_N, USDCAD_N, USDCHF_N | 4 |

---

## ⚙️ PAPER TRADE CONFIG (Quotex)

### Setups ativos no papertrade_quotex.py (linha 26-33)

```python
SETUPS = [
    ("BNB_M5_call_5",     "BNBUSD_otc", 300, "call_5", 0.70, 2.0, True),
    ("GBPJPY_M15_call_5", "GBPJPY_otc", 900, "call_5", 0.70, 1.5, True),
    ("BTC_M15_call_1",    "BTCUSD_otc", 900, "call_1", 0.70, 1.5, False),
    ("BRLUSD_M1_put_5",   "BRLUSD_otc", 60,  "put_5",  0.70, 1.0, False),
    ("LTC_M15_call_1",    "LTCUSD_otc", 900, "call_1", 0.65, 1.0, False),
]
```

**Formato:** `(nome, asset_code, tf_segundos, target, threshold, stake%, martingale)`

### Gestão de Risco

- **Stake máximo:** 2% por trade
- **Martingale:** 2 níveis (1× → 2.5× → 6×) — ativo nos setups 1 e 4
- **Cooldown:** 1 minuto entre re-entradas no mesmo setup
- **Scan:** 10 segundos entre varreduras completas
- **Tempo máximo:** 30 minutos por sessão

### Spreads calibrados (config/quotex_spreads.json)

| Classe | Exemplo | M1 | M5 | M15 |
|--------|---------|:---:|:---:|:---:|
| 🚀 Cripto | BTC | 0.00080 | 0.00080 | 0.00080 |
| 🇪🇺 Forex Major | EUR | 0.00032 | 0.00072 | 0.00131 |
| 🇬🇧 Forex Major | GBP | 0.00003 | 0.00007 | 0.00014 |
| 🇨🇭 Forex Major | CHF | 0.00032 | 0.00072 | 0.00126 |
| 🇨🇦 Forex Major | CAD | 0.00020 | 0.00048 | 0.00084 |

---

## 🧪 PIPELINE COMPLETO (8 FASES)

| Fase | Script | Descrição |
|:----:|--------|-----------|
| 1 | `collect_quotex_data.py` | Coleta 10 ativos principais |
| 2 | `collect_more_pairs.py` | +19 pares adicionais |
| 3 | `analyze_volatility.py` | Calibra spreads por volatilidade |
| 4 | `process_quotex_v2_all.py` | Feature engineering + targets calibrados |
| 5 | `train_quotex_v2.py` | Treina 299 modelos XGBoost |
| 6 | `backtest_quotex_models.py` | Validação anti-look-ahead |
| 7 | `papertrade_quotex.py` | Paper trade ao vivo |
| 8 | `dashboard.py` | Dashboard interativo |

---

## 💻 INSTALAÇÃO

### Linux (Debian/Ubuntu) — Máquina de casa

```bash
# 1. Clonar
git clone https://github.com/contatoevertonoliveira/obs.git
cd obs

# 2. Restore automático (cria 4 venvs)
chmod +x restore.sh
./restore.sh

# 3. Configurar credenciais
nano config/exchanges.env

# 4. Ativar e rodar
source venv_quotex/bin/activate
python3 src/papertrade_quotex.py
```

### Windows 11 Business — Notebook de trabalho

```powershell
# 1. Clonar
git clone https://github.com/contatoevertonoliveira/obs.git
cd obs

# 2. Criar venvs manualmente
python -m venv venv_quotex
python -m venv venv_pocket
python -m venv venv_iqoption
python -m venv venv_deriv

# 3. Instalar Quotex
venv_quotex\Scripts\activate
pip install xgboost pandas numpy ta joblib scikit-learn pyquotex

# 4. Instalar PocketOption
venv_pocket\Scripts\activate
pip install pandas numpy
pip install git+https://github.com/ByJhonesDev/PocketOptionAPI.git

# 5. Instalar IQOption
venv_iqoption\Scripts\activate
pip install git+https://github.com/Lu-Yi-Hsun/iqoptionapi.git

# 6. Instalar Deriv
venv_deriv\Scripts\activate
pip install websockets pandas numpy

# 7. Configurar credenciais
notepad config\exchanges.env

# 8. Rodar
venv_quotex\Scripts\activate
python src\papertrade_quotex.py
```

---

## 📋 COMANDOS ÚTEIS (Hermes Agent)

### Memórias do OB

```bash
# Ver memórias atuais
cat ~/.hermes/profiles/ob/memory.json 2>/dev/null

# Ver perfil do usuário
cat ~/.hermes/profiles/ob/user_profile.json 2>/dev/null

# Ver skills instaladas
hermes skills

# Ver cron jobs ativos
hermes cron list
```

### Verificar modelos

```bash
# Listar modelos viáveis
python3 -c "
import json
with open('backup_snapshot.json') as f:
    d = json.load(f)
for s in d['viable_setups']:
    print(f\"{s['name']:25s} WR={s['wr']:.1f}%  Trades={s['trades']:3d}\")
"
```

### Coletar dados (caso precise recriar)

```bash
source venv_quotex/bin/activate
python3 src/collect_quotex_data.py
python3 src/collect_more_pairs.py
python3 src/analyze_volatility.py
python3 src/process_quotex_v2_all.py
python3 src/train_quotex_v2.py
```

---

## 🔑 CREDENCIAIS (PROTEGIDAS — NÃO COMMITAR)

As credenciais estão em `config/exchanges.env` (ignorado pelo .gitignore):

```
QUOTEX_EMAIL="averdadesemfim@gmail.com"
QUOTEX_PASSWORD="Eve@91253425"
IQOPTION_EMAIL="averdadesemfim@gmail.com"
IQOPTION_PASSWORD=""  # ← PENDENTE
POCKET_SSID='42["auth",{...}]'  # ← EXPIRADO, refresh no navegador
DERIV_API_TOKEN=""  # ← PENDENTE (app.deriv.com → Settings → API Token)
DERIV_APP_ID="1089"
```

---

## ✅ STATUS ATUAL (05/06/2026)

| Item | Status |
|------|--------|
| Código no GitHub | ✅ Commit 1bfa4f9 |
| 4 exchanges configuradas | ✅ Quotex, Pocket, IQOption, Deriv |
| 299 modelos XGBoost | ✅ Treinados |
| 5 viáveis (th=0.7) | ✅ BNB 69.6%, BRLUSD 63.6%, BTC 63.2%, GBPJPY 62.1%, LTC 58.8% |
| Spreads calibrados | ✅ 86 pares |
| Paper trade Quotex | ✅ Funcional (IP bloqueado VPS) |
| restore.sh | ✅ 4 venvs automático |
| README | ✅ Win11 + Linux |
| IQOption senha | 🔴 Pendente |
| Deriv Token | 🔴 Pendente |
| PocketOption SSID | 🔴 Refresh no navegador |
| Testes ao vivo | 🔴 Pendente (fazer na máquina local) |

---

## 🚀 PRÓXIMOS PASSOS (Recomendação)

1. **No ambiente local:** clonar repo + rodar restore.sh
2. **Configurar credenciais:** preencher exchanges.env
3. **Testar conexão** de cada exchange
4. **Rodar paper trade** Quotex ao vivo
5. **Validar modelos** em tempo real
6. **Expandir** para PocketOption, IQOption, Deriv
7. **Implementar** Market Regime Detection
8. **Ciclo Seed:** R$100 → alvos graduais

---

> 📌 **Para o Hermes local:** Ao carregar este arquivo, o assistente OB terá todo o contexto necessário para continuar exatamente de onde parou — incluindo perfil do usuário, configurações das 4 exchanges, modelos ativos, pipeline completo e tom de comunicação preferido.
