#!/usr/bin/env bash
set -e

# ═══════════════════════════════════════════════════════════
#  HERMES QUANT V2 — Restore Automático
#  Uso: chmod +x restore.sh && ./restore.sh
# ═══════════════════════════════════════════════════════════

COR_VERDE='\033[0;32m'
COR_AMARELO='\033[1;33m'
COR_VERMELHO='\033[0;31m'
COR_AZUL='\033[0;34m'
COR_RESET='\033[0m'

info()  { echo -e "${COR_AZUL}[INFO]${COR_RESET} $1"; }
ok()    { echo -e "${COR_VERDE}[OK]${COR_RESET} $1"; }
aviso() { echo -e "${COR_AMARELO}[AVISO]${COR_RESET} $1"; }
erro()  { echo -e "${COR_VERMELHO}[ERRO]${COR_RESET} $1"; }

PROJETO_DIR="$(cd "$(dirname "$0")" && pwd)"
VENV_DIR="$PROJETO_DIR/venv_quotex"

echo ""
echo "╔═══════════════════════════════════════════════════╗"
echo "║   🤖 HERMES QUANT V2 — RESTORE AUTOMÁTICO       ║"
echo "║   $(date '+%d/%m/%Y %H:%M')                            ║"
echo "╚═══════════════════════════════════════════════════╝"
echo ""

# ─── 1. VERIFICAR PYTHON ───
info "Verificando Python..."
PYTHON_CMD=""
for cmd in python3.12 python3 python; do
    if command -v $cmd &>/dev/null; then
        VER=$($cmd --version 2>&1 | grep -oP '\d+\.\d+')
        MAJOR=$(echo $VER | cut -d. -f1)
        MINOR=$(echo $VER | cut -d. -f2)
        if [ "$MAJOR" -ge 3 ] && [ "$MINOR" -ge 10 ]; then
            PYTHON_CMD=$cmd
            ok "$cmd versão $VER encontrado"
            break
        fi
    fi
done

if [ -z "$PYTHON_CMD" ]; then
    erro "Python 3.10+ não encontrado. Instale com: sudo apt install python3.12 python3.12-venv"
    exit 1
fi

# ─── 2. CRIAR VENV ───
info "Criando ambiente virtual..."
if [ -d "$VENV_DIR" ]; then
    aviso "venv já existe, recriando..."
    rm -rf "$VENV_DIR"
fi

$PYTHON_CMD -m venv "$VENV_DIR"
source "$VENV_DIR/bin/activate"
ok "venv criada em $VENV_DIR"

# ─── 3. ATUALIZAR PIP ───
info "Atualizando pip..."
pip install --upgrade pip -q
ok "pip atualizado"

# ─── 4. INSTALAR DEPENDÊNCIAS ───
info "Instalando dependências..."
if [ -f "$PROJETO_DIR/requirements.txt" ]; then
    pip install -r "$PROJETO_DIR/requirements.txt" -q
    ok "Dependências instaladas"
else
    aviso "requirements.txt não encontrado, instalando manualmente..."
    pip install xgboost pandas numpy ta joblib scikit-learn pyquotex -q
    ok "Dependências instaladas manualmente"
fi

# ─── 5. VERIFICAR ESTRUTURA ───
info "Verificando estrutura do projeto..."

CHECK_OK=0
CHECK_TOTAL=0

check_file() {
    CHECK_TOTAL=$((CHECK_TOTAL + 1))
    if [ -f "$PROJETO_DIR/$1" ]; then
        ok "  ✅ $1"
        CHECK_OK=$((CHECK_OK + 1))
    else
        aviso "  ⚠️  $1 (não encontrado - pode ser opcional)"
    fi
}

check_dir() {
    CHECK_TOTAL=$((CHECK_TOTAL + 1))
    if [ -d "$PROJETO_DIR/$1" ]; then
        QTD=$(find "$PROJETO_DIR/$1" -type f 2>/dev/null | wc -l)
        ok "  ✅ $1 ($QTD arquivos)"
        CHECK_OK=$((CHECK_OK + 1))
    else
        aviso "  ⚠️  $1 (diretório não encontrado)"
    fi
}

check_file "src/papertrade_quotex.py"
check_file "src/train_quotex_v2.py"
check_file "src/process_quotex_v2_all.py"
check_file "src/collect_quotex_data.py"
check_file "config/quotex_spreads.json"
check_file "backup_snapshot.json"
check_dir  "models/quotex_v2"
check_dir  "data/processed/quotex_v2"
check_dir  "data/raw/quotex"
check_dir  "src"

# ─── 6. CRIAR DIRETÓRIOS NECESSÁRIOS ───
mkdir -p "$PROJETO_DIR/logs/papertrade"
mkdir -p "$PROJETO_DIR/data/raw"
mkdir -p "$PROJETO_DIR/data/processed"
mkdir -p "$PROJETO_DIR/models"

# ─── RESUMO ───
echo ""
echo "╔═══════════════════════════════════════════════════╗"
echo "║   ✅ RESTORE CONCLUÍDO!                          ║"
echo "╚═══════════════════════════════════════════════════╝"
echo ""
echo "  📁 Projeto:    $PROJETO_DIR"
echo "  🐍 Python:     $PYTHON_CMD"
echo "  🔧 Venv:       $VENV_DIR"
echo "  📦 Arquivos:   $CHECK_OK/$CHECK_TOTAL OK"
echo ""

if [ "$CHECK_OK" -lt 5 ]; then
    aviso "Alguns arquivos estão faltando. Pode ser necessário clonar novamente:"
    echo "  git clone https://github.com/contatoevertonoliveira/obs.git"
    echo ""
fi

# ─── INSTRUÇÕES FINAIS ───
echo "╔═══════════════════════════════════════════════════╗"
echo "║   🚀 PRÓXIMOS PASSOS                            ║"
echo "╚═══════════════════════════════════════════════════╝"
echo ""
echo "  1️⃣  Ativar ambiente:"
echo "      source $VENV_DIR/bin/activate"
echo ""
echo "  2️⃣  Configurar credenciais Quotex:"
echo "      export QUOTEX_EMAIL=\"seu@email.com\""
echo "      export QUOTEX_PASSWORD=\"sua_senha\""
echo ""
echo "  3️⃣  Rodar paper trade:"
echo "      python3 src/papertrade_quotex.py"
echo ""
echo "  4️⃣  Coletar mais dados (opcional):"
echo "      python3 src/collect_quotex_data.py"
echo ""
echo "  5️⃣  Re-treinar modelos (opcional):"
echo "      python3 src/process_quotex_v2_all.py"
echo "      python3 src/train_quotex_v2.py"
echo ""
echo "  📊  Snapshot completo: backup_snapshot.json"
echo "  📘  Documentação:     README.md"
echo ""

# ─── VERIFICAÇÃO EXTRA ───
if [ "$CHECK_OK" -eq "$CHECK_TOTAL" ]; then
    ok "Tudo pronto! Ambiente restaurado com sucesso! 🚀"
else
    aviso "$((CHECK_TOTAL - CHECK_OK)) arquivo(s) faltando. Alguns recursos podem não funcionar."
fi

echo ""
