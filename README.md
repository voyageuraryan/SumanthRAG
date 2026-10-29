# PolicyRAG: a grounded, abstention-aware assistant for ATU graduate policy

INFT 5113 semester project (Fall 2026), Sumanth Reddy Nalla. The repository is at **Milestone 3: initial working solution**.

A question goes in. The system retrieves passages from the frozen ATU policy corpus, asks a local LLM to answer **only** from those passages, and returns one of three outcomes. It answers with citations, refers the user to where a missing detail is published, or refuses. Every response is logged with the data, code, config, prompt and model versions that produced it.

```
question -> retriever (0: none | A: BM25 | B: dense) -> gate 1 (score, off in M3 baseline)
         -> Llama 3.1 8B via Ollama, JSON {status: answer|refer|insufficient}  (gate 2)
         -> citations + support check (diagnostic only) -> answer / referral / refusal -> log
```

## One-command setup (recommended)

Nothing needs to be installed beforehand. The script installs `uv` (which fetches Python 3.12 itself), the locked dependencies, Ollama and the `llama3.1:8b` model, then fetches and hash-verifies the corpus, rebuilds the chunks, runs the tests and asks one real question. Re-running it skips finished steps.

| OS | Command |
|---|---|
| Windows 10/11 | `powershell -ExecutionPolicy Bypass -File setup.ps1` |
| macOS / Linux | `bash setup.sh` |

Options: `-Model llama3.2:3b` / `--model llama3.2:3b` (8 GB machines), `-Dense` / `--dense` (Condition B), `-SkipModel` / `--skip-model` (no Ollama; corpus and tests only). A Docker route also exists: `docker compose up -d ollama`, `docker compose --profile tools run --rm ollama-pull`, then `docker compose run --rm app python -m src.ask "..."`.

**One manual step may remain.** The graduate catalog host (`catalog.atu.edu`) sits behind bot protection that can answer scripted downloads with an empty page. If that happens, `scripts/fetch_corpus.py` says so and tells you which file to save from your browser into `data/raw/`; the SHA-256 check then confirms it is the frozen snapshot. The student handbook downloads normally.

## Quick start (Windows, PowerShell; manual route)

1. Install **Python 3.10–3.13** and **Ollama** (https://ollama.com/download). Start Ollama.
2. From this folder run:
   ```powershell
   powershell -ExecutionPolicy Bypass -File scripts\run_m3.ps1
   ```
   This creates `.venv`, installs dependencies, pulls `llama3.1:8b` (about 4.9 GB) and fetches and hash-verifies the corpus. It then rebuilds the chunks, runs the tests, records the hardware, runs the baseline on the demo and dev questions, and packages the submission. Everything printed is saved to `reports\run_m3_console.txt`.
   Add `-Dense` to include Condition B, or `-Model llama3.2:3b` on a machine with 8 GB RAM.
3. Ask your own question (activate the env first: `.venv\Scripts\Activate.ps1`):
   ```powershell
   python -m src.ask "How many graduate credit hours can I transfer in from another university?"
   python -m uvicorn src.api:app --port 8000        # then open http://127.0.0.1:8000
   ```

macOS/Linux: `bash scripts/run_m3.sh [--dense]`.

## Commands

| Purpose | Command |
|---|---|
| Fetch + verify corpus | `python scripts/fetch_corpus.py` |
| Rebuild chunks | `python -m src.ingest` then `python -m src.chunk` |
| One question (CLI) | `python -m src.ask "..." [--condition A\|0\|B] [--doc GC2627\|SH2026] [--json]` |
| Web UI + API | `python -m uvicorn src.api:app --port 8000` (`GET /health`, `POST /query`) |
| Run a question set | `python -m src.run_eval --split demo\|dev --conditions A,0[,B]` |
| Gate-1 sensitivity | `python -m src.threshold_sweep results/eval/<run> --condition A` |
| Blind manual scoring | fill `results/eval/<run>/scoring_sheet.csv`, then `python -m src.score_import results/eval/<run>` |
| Support-check diagnostic | `python -m src.checks.support_check_eval` |
| Write evaluation items | edit `eval/authoring_workbook.xlsx`, then `python -m src.eval_import [--split dev]` |
| Validate / lock eval set | `python -m src.eval_validate [--split dev]`; `python -m src.eval_validate --lock` |
| Tests | `python -m pytest -q tests` |
| Hardware + speed record | `python scripts/hw_probe.py` -> `reports/hardware.json` |
| Submission package | `python scripts/make_submission.py` -> `dist/` |

## Evaluation data and leakage rules

- `eval/authoring_plan.csv` assigns a randomly drawn passage (seed 13) to each of the 50 items: 10 dev and 40 test. The model writes every question and gold answer by hand in `eval/authoring_workbook.xlsx`.
- The validator rejects empty or wrongly sized sets, wrong type counts, unknown chunk ids, demo look-alikes and dev/test near-duplicates. `--lock` refuses unless all 50 items pass.
- `src.run_eval --split test` refuses to run without `--final` and `eval/LOCK.json` (Milestone 4 only).
- `eval/demo_queries.jsonl` holds the six Milestone 2 demonstration queries. They are labelled for demonstration and are not part of the evaluation set.

## Data and redistribution

The corpus is two public ATU PDFs, frozen 2026-10-04 and identified by SHA-256 in `configs/corpus_manifest.json`. **They are not redistributed**: `data/raw/*.pdf` is git-ignored and excluded from `dist/policy-rag-m3.zip`. `scripts/fetch_corpus.py` downloads them and refuses a file whose hash differs. (The Milestone 2 zip included them by mistake; this is corrected from Milestone 3 on.) Derived passages (`data/processed/chunks.jsonl`) are regenerated by `src.ingest` + `src.chunk`.

## Reproducibility

Each record in `results/runs.jsonl` and each `results/eval/<run>/run_config.json` stores the following:

- `git_commit`, `git_dirty` and `code_sha`, a content hash of `src/`, `configs/` and `prompts/`
- the config hashes and the chunk-file hash
- the prompt version and its hash
- the retriever settings
- the Ollama model name, **digest** and version

`reports/environment_freeze.txt` records exact package versions. Decoding is deterministic (temperature 0, seed 13). Even so, quantised models can differ slightly across CPU and GPU builds, so all outputs are saved and scoring works from the saved files.

## Secrets

None are needed: everything runs locally. `.env` is git-ignored. Run `python scripts/scan_secrets.py` before every commit.
