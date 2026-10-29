#!/usr/bin/env bash
# macOS/Linux equivalent of run_m3.ps1.  usage: bash scripts/run_m3.sh [--dense]
set -euo pipefail; cd "$(dirname "$0")/.."; mkdir -p reports
exec > >(tee reports/run_m3_console.txt) 2>&1
PY=${PYTHON:-python3}; MODEL=${POLICYRAG_MODEL:-llama3.1:8b}; CONDS="A,0"
[ -d .venv ] || $PY -m venv .venv; source .venv/bin/activate
pip install -q -r requirements.txt
if [ "${1:-}" = "--dense" ]; then pip install -q -r requirements-dense.txt; CONDS="A,0,B"; fi
pip freeze > reports/environment_freeze.txt
ollama --version && ollama pull "$MODEL"; export POLICYRAG_MODEL=$MODEL
python scripts/fetch_corpus.py && python -m src.ingest && python -m src.chunk && sha256sum data/processed/chunks.jsonl
python -m pytest -q tests && python scripts/hw_probe.py && python -m src.checks.support_check_eval
python -m src.run_eval --split demo --conditions "$CONDS" --tag m3-baseline
if python -m src.eval_validate --split dev; then
  python -m src.run_eval --split dev --conditions "$CONDS" --tag m3-baseline
  python -m src.threshold_sweep "results/eval/$(ls results/eval | grep -- -dev- | sort | tail -1)" --condition A
fi
python scripts/scan_secrets.py && python scripts/make_submission.py
