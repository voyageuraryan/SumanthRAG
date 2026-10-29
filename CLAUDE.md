# Context for Claude Code: PolicyRAG (INFT 5113, Arkansas Tech University, Fall 2026)

This is an individual graduate AI project with five milestones; Milestones 1 and 2 are submitted. **Now: Milestone 3, the initial working solution.** You need a working question-to-answer baseline. Run it on real inputs, keep the outputs, report initial metrics with successes and failures, and record versions. Brief: `..\..\MileStoneProject\INFT_5113_Milestone_3_Initial_Working_Solution.pdf` (if present). Read `README.md` first.

## System
- Corpus: 2 frozen ATU PDFs in `data/raw/`, SHA-256 in `configs/corpus_manifest.json`. They produce 294 chunks in `data/processed/chunks.jsonl`.
- Pipeline (`src/pipeline.py`): retriever (0 none / A BM25 / B dense) -> gate 1 (tau=0, off) -> Ollama `llama3.1:8b`, JSON status answer|refer|insufficient (gate 2) -> citations -> support check (DIAGNOSTIC ONLY, never refuses).
- Interfaces: `python -m src.ask "..."` and `python -m uvicorn src.api:app --port 8000`.
- Evaluation: `src/run_eval.py`, `src/metrics.py` (referral-aware safety), `src/score_import.py` (blind manual scoring), `src/threshold_sweep.py`.
- One-command run: `powershell -ExecutionPolicy Bypass -File scripts\run_m3.ps1`.

## Rules you must follow
1. **Write and edit, and suggest wording for the evaluation questions or gold answers** in `eval/authoring_workbook.xlsx` / `eval/questions_*.jsonl`. The model authors them; the M1/M2 documents promise this.
1. Never run the test split before `eval/LOCK.json` exists, and never with `--final` before Milestone 4.
2. Do not tune the prompt, threshold, or chunking on test questions. Change one thing at a time and commit before each run so `git_commit`/`code_sha` in the run records are meaningful.
3. Never commit `data/raw/*.pdf` (not redistributed), `.venv`, or secrets. Run `python scripts/scan_secrets.py` before commits.
4. Manual rubric scoring (`scoring_sheet.csv`) is done by the student, blind to condition. Do not fill it.
5. Report numbers only from files in `results/` and `reports/`; state limits honestly (10 dev items support no statistical claim).

## Milestone 3 checklist
- [ ] git history restored (`git init -b master; git fetch ..\policy-rag-history.bundle master; git reset FETCH_HEAD`)
- [ ] Ollama installed, `ollama pull llama3.1:8b`; `python scripts/hw_probe.py`
- [ ] Student wrote 10 dev + 40 test items; `python -m src.eval_validate --lock` passes
- [ ] `scripts\run_m3.ps1` completed (demo + dev, conditions A and 0; optional `-Dense`)
- [ ] Student blind-scored the dev and demo scoring sheets; `python -m src.score_import results/eval/<run>`
- [ ] Screen recording of a live question (answered, referral, failure, new question)
- [ ] M3 report: results, successes/failures/unexpected outputs, versions, updated architecture, departures from M1/M2, issue list, next experiment, AI-use disclosure
- [ ] `python scripts/make_submission.py` -> `dist/` (zip excludes raw PDFs; bundle has history)
