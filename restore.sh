#!/usr/bin/env bash
# ===============================================================
#  🚀 Hermes Quant V2 — Restore Completo
#  Uso: git clone https://github.com/contatoevertonoliveira/obs.git
#       cd obs && chmod +x restore.sh && ./restore.sh
# ===============================================================
set -e

echo "═══════════════════════════════════════════════════════"
echo "  🚀 HERMES QUANT V2 — RESTAURANDO AMBIENTE"
echo "═══════════════════════════════════════════════════════"

DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$DIR"

# 1. Verificar Python
echo ""
echo "📋 [1/5] Verificando Python..."
if command -v python3.12 &> /dev/null; then
    PY=python3.12
elif command -v python3 &> /dev/null; then
    PY=python3
else
    echo "❌ Python não encontrado. Instale Python 3.12+"
    exit 1
fi
echo "   ✅ Python: $($PY --version)"

# 2. Criar virtualenv
echo ""
echo "📋 [2/5] Criando virtualenv..."
if [ ! -d "venv_quotex" ]; then
    $PY -m venv venv_quotex
    echo "   ✅ virtualenv criado"
else
    echo "   ⏭️  virtualenv já existe"
fi

source venv_quotex/bin/activate

# 3. Instalar dependências
echo ""
echo "📋 [3/5] Instalando dependências..."
pip install --upgrade pip -q
pip install -r requirements.txt -q
echo "   ✅ Dependências instaladas"

# 4. Configurar credenciais
echo ""
echo "📋 [4/5] Configurando credenciais..."
if [ -z "$QUOTEX_EMAIL" ] || [ -z "$QUOTEX_PASSWORD" ]; then
    echo "   ⚠️  Variáveis QUOTEX_EMAIL/QUOTEX_PASSWORD não definidas."
    echo "   📝 Exporte-as antes de rodar o paper trade:"
    echo ""
    echo "       export QUOTEX_EMAIL=\"seu@email.com\""
    echo "       export QUOTEX_PASSWORD=\"sua_senha\""
    echo ""
else
    echo "   ✅ Credenciais encontradas"
fi

# 5. Verificar arquivos
echo ""
echo "📋 [5/5] Verificando arquivos..."
FILES_OK=0
FILES_TOTAL=0

check_file() {
    FILES_TOTAL=$((FILES_TOTAL + 1))
    if [ -f "$1" ]; then
        FILES_OK=$((FILES_OK + 1))
    else
        echo "   ❌ Faltando: $1"
    fi
}

check_dir() {
    FILES_TOTAL=$((FILES_TOTAL + 1))
    if [ -d "$1" ]; then
        local count=$(find "$1" -type f 2>/dev/null | wc -l)
        FILES_OK=$((FILES_OK + 1))
        echo "   ✅ $1 ($count arquivos)"
    else
        echo "   ❌ Diretório faltando: $1"
    fi
}

check_dir "src"
check_dir "config"
check_dir "models/quotex_v2"
check_dir "data/processed/quotex_v2"
check_dir "data/raw/quotex"
check_file "requirements.txt"
check_file "README.md"

echo ""
echo "   📊 $FILES_OK/$FILES_TOTAL componentes OK"

echo ""
echo "═══════════════════════════════════════════════════════"
echo "  ✅ AMBIENTE RESTAURADO COM SUCESSO!"
echo "═══════════════════════════════════════════════════════"
echo ""
echo "  📌 Para rodar o paper trade:"
echo ""
echo "    source venv_quotex/bin/activate"
echo "    export QUOTEX_EMAIL=\"seu@email.com\""
echo "    export QUOTEX_PASSWORD=\"sua_senha\""
echo "    python3 src/papertrade_quotex.py"
echo ""
echo "  📌 Para re-treinar modelos:"
echo ""
echo "    source venv_quotex/bin/activate"
echo "    python3 src/process_quotex_v2_all.py   # features"
echo "    python3 src/train_quotex_v2.py          # treino"
echo ""
echo "  📌 Para backtest:"
echo ""
echo "    source venv_quotex/bin/activate"
echo "    python3 src/backtest_quotex_models.py"
echo ""
echo "═══════════════════════════════════════════════════════"
