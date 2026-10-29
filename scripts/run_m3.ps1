# Milestone 3 baseline run on Windows (PowerShell). From the policy-rag folder:
#   powershell -ExecutionPolicy Bypass -File scripts\run_m3.ps1            # demo + dev, conditions A and 0
#   powershell -ExecutionPolicy Bypass -File scripts\run_m3.ps1 -Dense     # also condition B (downloads bge-small)
# Everything printed is also saved to reports\run_m3_console.txt as evidence.
param([switch]$Dense, [string]$Model = "llama3.1:8b")
$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot)
$env:PYTHONUTF8 = "1"; $env:PYTHONIOENCODING = "utf-8"   # Windows: read/write all text as UTF-8
New-Item -ItemType Directory -Force reports | Out-Null
Start-Transcript -Path reports\run_m3_console.txt -Force | Out-Null
function Step($t) { Write-Host "`n=== $t ===" -ForegroundColor Cyan }
function Run($cmd) { Write-Host "> $cmd"; Invoke-Expression $cmd; if ($LASTEXITCODE -ne 0) { throw "failed: $cmd" } }
try {
  Step "1. Python environment"
  if (-not (Test-Path .venv)) { Run "python -m venv .venv" }
  . .\.venv\Scripts\Activate.ps1
  Run "python --version"
  Run "python -m pip install -q --upgrade pip"
  Run "python -m pip install -q -r requirements.txt"
  if ($Dense) { Run "python -m pip install -q -r requirements-dense.txt" }
  python -m pip freeze | Out-File -Encoding utf8 reports\environment_freeze.txt

  Step "2. Ollama + model"
  Run "ollama --version"
  Run "ollama pull $Model"
  $env:POLICYRAG_MODEL = $Model

  Step "3. Corpus (frozen snapshot, hash-verified)"
  Run "python scripts/fetch_corpus.py"
  Run "python -m src.ingest"
  Run "python -m src.chunk"
  $h = (Get-FileHash data\processed\chunks.jsonl -Algorithm SHA256).Hash.ToLower()
  Write-Host "chunks.jsonl sha256 $h  (M2 value: 809dd620cdc90e83...)"

  Step "4. Tests + hardware"
  Run "python -m pytest -q tests"
  Run "python scripts/hw_probe.py"
  Run "python -m src.checks.support_check_eval"

  Step "5. Baseline on the 6 demonstration queries"
  $conds = "A,0"; if ($Dense) { $conds = "A,0,B" }
  Run "python -m src.run_eval --split demo --conditions $conds --tag m3-baseline"

  Step "6. Baseline on the 10 dev (pilot) questions"
  python -m src.eval_validate --split dev
  if ($LASTEXITCODE -eq 0) {
    Run "python -m src.run_eval --split dev --conditions $conds --tag m3-baseline"
    $dev = Get-ChildItem results\eval -Directory | Where-Object Name -like "*-dev-*" | Sort-Object Name | Select-Object -Last 1
    Run "python -m src.threshold_sweep results/eval/$($dev.Name) --condition A"
  } else { Write-Host "Dev questions not complete yet - skipped (write them in eval\authoring_workbook.xlsx, then: python -m src.eval_import --split dev)" -ForegroundColor Yellow }

  Step "7. Secret scan + submission bundle"
  Run "python scripts/scan_secrets.py"
  Run "python scripts/make_submission.py"
  Write-Host "`nDONE. Next: score results\eval\<run>\scoring_sheet.csv by hand, then python -m src.score_import results/eval/<run>" -ForegroundColor Green
} finally { Stop-Transcript | Out-Null }
