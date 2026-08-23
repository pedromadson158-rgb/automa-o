#!/bin/bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HERMES_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
VENV_DIR="$SCRIPT_DIR/.venv"

ROUTER_PID=""
GATEWAY_PID=""

cleanup() {
    echo ""
    echo "🛑 Encerrando Router e Gateway..."

    if [ -n "${ROUTER_PID:-}" ]; then
        kill "$ROUTER_PID" 2>/dev/null || true
    fi

    if [ -n "${GATEWAY_PID:-}" ]; then
        kill "$GATEWAY_PID" 2>/dev/null || true
    fi
}

trap cleanup EXIT INT TERM

echo "🚀 Iniciando sistema..."
echo "📁 Hermes: $HERMES_DIR"

if [ ! -d "$VENV_DIR" ]; then
    echo "🐍 Criando ambiente virtual..."
    python3 -m venv "$VENV_DIR"

    source "$VENV_DIR/bin/activate"

    echo "📦 Instalando Hermes..."
    python -m pip install -e "$HERMES_DIR"

    echo "📦 Instalando Router/Gateway..."
    python -m pip install -r "$SCRIPT_DIR/requirements-router.txt"
else
    source "$VENV_DIR/bin/activate"
fi

echo "🧹 Encerrando processos antigos..."
pkill -f "uvicorn router:app" 2>/dev/null || true
pkill -f "uvicorn llm_gateway:app" 2>/dev/null || true

sleep 1

cd "$SCRIPT_DIR"

echo "🔌 Subindo Router..."
uvicorn router:app \
    --host 127.0.0.1 \
    --port 8001 \
    --no-access-log &

ROUTER_PID=$!

sleep 2

echo "🧠 Subindo Gateway..."
uvicorn llm_gateway:app \
    --host 127.0.0.1 \
    --port 8000 \
    --no-access-log &

GATEWAY_PID=$!

sleep 2

echo "🤖 Iniciando Hermes..."

export OPENAI_BASE_URL="http://127.0.0.1:8000/v1"
export OPENAI_API_KEY="local"

cd "$HERMES_DIR"

python ./hermes
