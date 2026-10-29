#!/usr/bin/env bash
# Rebuilds every Milestone 2 artifact from the frozen PDFs. Each step logs to results/runs.jsonl.
set -euo pipefail
cd "$(dirname "$0")/.."
"${PYTHON:-python}" -m src.ingest
"${PYTHON:-python}" -m src.chunk
"${PYTHON:-python}" -m src.data_quality
"${PYTHON:-python}" -m src.checks.normalization_effect
"${PYTHON:-python}" -m src.eval_sampler
"${PYTHON:-python}" -m pytest -q tests
"${PYTHON:-python}" -m src.bm25_retriever "How many graduate credit hours can I transfer in from another university?" --tag demo
"${PYTHON:-python}" scripts/scan_secrets.py
