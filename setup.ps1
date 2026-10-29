# One-command setup for Windows 10/11 (PowerShell 5.1+). Run from this folder:
#   powershell -ExecutionPolicy Bypass -File setup.ps1
# Options:  -Model llama3.2:3b   smaller model for 8 GB machines
#           -Dense               also install Condition B (dense retrieval) dependencies
#           -SkipModel           do not install/start Ollama or pull the model (tests + corpus only)
#           -NoSmoke             skip the final end-to-end question
# Anything missing (uv, Python, Ollama, the model, the corpus PDFs) is downloaded automatically.
# Safe to re-run: finished steps are detected and skipped.
param([string]$Model = "llama3.1:8b", [switch]$Dense, [switch]$SkipModel, [switch]$NoSmoke)
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
$env:PYTHONUTF8 = "1"; $env:PYTHONIOENCODING = "utf-8"
function Step($t) { Write-Host "`n=== $t ===" -ForegroundColor Cyan }
function Have($c) { [bool](Get-Command $c -ErrorAction SilentlyContinue) }
function RefreshPath {
  $m = [Environment]::GetEnvironmentVariable("Path", "Machine"); $u = [Environment]::GetEnvironmentVariable("Path", "User")
  $env:Path = "$m;$u;$env:USERPROFILE\.local\bin;$env:LOCALAPPDATA\Programs\Ollama"
}
function Run($exe, [string[]]$a) {
  Write-Host "> $exe $($a -join ' ')"
  $prev = $ErrorActionPreference; $ErrorActionPreference = "Continue"   # PS 5.1 treats native stderr (uv progress) as an error otherwise
  & $exe @a
  $code = $LASTEXITCODE; $ErrorActionPreference = $prev
  if ($code -ne 0) { throw "failed (exit $code): $exe $($a -join ' ')" }
}
function OllamaUp { try { Invoke-RestMethod "http://127.0.0.1:11434/api/version" -TimeoutSec 3 | Out-Null; $true } catch { $false } }

Step "1. uv (Python package + version manager)"
RefreshPath
if (-not (Have uv)) {
  Write-Host "uv not found - installing"
  Invoke-RestMethod https://astral.sh/uv/install.ps1 | Invoke-Expression
  RefreshPath
}
if (-not (Have uv)) { throw "uv installation failed. Install it from https://docs.astral.sh/uv/ and re-run." }
uv --version

Step "2. Python 3.12 + dependencies (uv downloads Python itself if needed)"
$extra = @(); if ($Dense) { $extra = @("--extra", "dense") }
Run uv (@("sync", "--frozen") + $extra)

if (-not $SkipModel) {
  Step "3. Ollama (local model server)"
  if (-not (Have ollama)) {
    Write-Host "Ollama not found - installing"
    $done = $false
    if (Have winget) {
      winget install -e --id Ollama.Ollama --silent --accept-package-agreements --accept-source-agreements
      RefreshPath; $done = Have ollama
    }
    if (-not $done) {
      $inst = Join-Path $env:TEMP "OllamaSetup.exe"
      Invoke-WebRequest https://ollama.com/download/OllamaSetup.exe -OutFile $inst
      Start-Process $inst -ArgumentList "/SILENT" -Wait
      RefreshPath
    }
  }
  if (-not (Have ollama)) { throw "Ollama installation failed. Install it from https://ollama.com/download and re-run." }
  if (-not (OllamaUp)) {
    Write-Host "starting Ollama server"
    Start-Process ollama -ArgumentList "serve" -WindowStyle Hidden
    for ($i = 0; $i -lt 30 -and -not (OllamaUp); $i++) { Start-Sleep 2 }
    if (-not (OllamaUp)) { throw "Ollama server did not start. Open the Ollama app once and re-run." }
  }
  ollama --version

  Step "4. Model $Model (one-time download, about 5 GB for llama3.1:8b)"
  if ((ollama list) -match [regex]::Escape($Model)) { Write-Host "already installed" } else { Run ollama @("pull", $Model) }
  $env:POLICYRAG_MODEL = $Model
}

Step "5. Corpus (frozen ATU PDFs, hash-verified) and chunks"
Run uv @("run", "python", "scripts/fetch_corpus.py")
Run uv @("run", "python", "-m", "src.ingest")
Run uv @("run", "python", "-m", "src.chunk")

Step "6. Tests"
Run uv @("run", "python", "-m", "pytest", "-q", "tests")

if (-not $SkipModel -and -not $NoSmoke) {
  Step "7. Smoke test: one real question (the first answer can take a minute while the model loads)"
  Run uv @("run", "python", "-m", "src.ask", "How many graduate credit hours can I transfer in from another university?")
}

Write-Host "`nSetup complete." -ForegroundColor Green
Write-Host "Ask a question :  uv run python -m src.ask `"your question`""
Write-Host "Web UI         :  uv run python -m uvicorn src.api:app --port 8000   (then open http://127.0.0.1:8000)"
Write-Host "Baseline runs  :  uv run python -m src.run_eval --split dev --conditions A,0 --tag m3-baseline"
