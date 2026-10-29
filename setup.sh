#!/usr/bin/env bash
# One-command setup for macOS and Linux. Run from this folder:   bash setup.sh
# Options:  --model llama3.2:3b   smaller model for 8 GB machines
#           --dense               also install Condition B (dense retrieval) dependencies
#           --skip-model          do not install/start Ollama or pull the model (tests + corpus only)
#           --no-smoke            skip the final end-to-end question
# Anything missing (uv, Python, Ollama, the model, the corpus PDFs) is downloaded automatically.
# Safe to re-run: finished steps are detected and skipped.
set -euo pipefail
cd "$(dirname "$0")"
MODEL="llama3.1:8b"; DENSE=0; SKIP_MODEL=0; SMOKE=1
while [ $# -gt 0 ]; do
  case "$1" in
    --model) MODEL="$2"; shift ;;
    --dense) DENSE=1 ;;
    --skip-model) SKIP_MODEL=1 ;;
    --no-smoke) SMOKE=0 ;;
    *) echo "unknown option: $1"; exit 2 ;;
  esac; shift
done
export PYTHONUTF8=1 PYTHONIOENCODING=utf-8 PATH="$HOME/.local/bin:$HOME/.cargo/bin:/opt/homebrew/bin:/usr/local/bin:$PATH"
step() { printf '\n\033[36m=== %s ===\033[0m\n' "$1"; }
have() { command -v "$1" >/dev/null 2>&1; }
ollama_up() { curl -fsS --max-time 3 http://127.0.0.1:11434/api/version >/dev/null 2>&1; }

step "1. uv (Python package + version manager)"
if ! have uv; then
  echo "uv not found - installing"
  curl -LsSf https://astral.sh/uv/install.sh | sh
  export PATH="$HOME/.local/bin:$PATH"
fi
have uv || { echo "uv installation failed. See https://docs.astral.sh/uv/ and re-run."; exit 1; }
uv --version

step "2. Python 3.12 + dependencies (uv downloads Python itself if needed)"
if [ "$DENSE" = 1 ]; then uv sync --frozen --extra dense; else uv sync --frozen; fi

if [ "$SKIP_MODEL" = 0 ]; then
  step "3. Ollama (local model server)"
  if ! have ollama; then
    echo "Ollama not found - installing"
    if [ "$(uname)" = "Darwin" ] && have brew; then
      brew install ollama
    else
      curl -fsSL https://ollama.com/install.sh | sh
    fi
  fi
  have ollama || { echo "Ollama installation failed. See https://ollama.com/download and re-run."; exit 1; }
  if ! ollama_up; then
    echo "starting Ollama server"
    nohup ollama serve >/tmp/ollama-policyrag.log 2>&1 &
    for _ in $(seq 1 30); do ollama_up && break; sleep 2; done
    ollama_up || { echo "Ollama server did not start (see /tmp/ollama-policyrag.log)."; exit 1; }
  fi
  ollama --version

  step "4. Model $MODEL (one-time download, about 5 GB for llama3.1:8b)"
  if ollama list | grep -q "^${MODEL}[[:space:]]"; then echo "already installed"; else ollama pull "$MODEL"; fi
  export POLICYRAG_MODEL="$MODEL"
fi

step "5. Corpus (frozen ATU PDFs, hash-verified) and chunks"
uv run python scripts/fetch_corpus.py
uv run python -m src.ingest
uv run python -m src.chunk

step "6. Tests"
uv run python -m pytest -q tests

if [ "$SKIP_MODEL" = 0 ] && [ "$SMOKE" = 1 ]; then
  step "7. Smoke test: one real question (the first answer can take a minute while the model loads)"
  uv run python -m src.ask "How many graduate credit hours can I transfer in from another university?"
fi

printf '\n\033[32mSetup complete.\033[0m\n'
echo 'Ask a question :  uv run python -m src.ask "your question"'
echo 'Web UI         :  uv run python -m uvicorn src.api:app --port 8000   (then open http://127.0.0.1:8000)'
echo 'Baseline runs  :  uv run python -m src.run_eval --split dev --conditions A,0 --tag m3-baseline'
