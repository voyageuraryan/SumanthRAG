"""Package the repository for submission: dist/policy-rag-m3.zip (+ dist/policy-rag.bundle with full git history).
Excludes the raw ATU PDFs (not redistributed - scripts/fetch_corpus.py rebuilds them), virtualenvs, caches, model indexes."""
import subprocess, zipfile
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
SKIP_DIRS = {".venv", "venv", "__pycache__", ".pytest_cache", "indexes", "dist", ".git"}
dist = ROOT / "dist"; dist.mkdir(exist_ok=True)
out = dist / "policy-rag-m3.zip"; n = 0
with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
    for p in sorted(ROOT.rglob("*")):
        rel = p.relative_to(ROOT)
        if p.is_dir() or SKIP_DIRS & set(rel.parts): continue
        if rel.parts[:2] == ("data", "raw") and p.suffix.lower() == ".pdf": continue
        z.write(p, Path("policy-rag") / rel); n += 1
print(f"wrote {out} ({n} files, {out.stat().st_size/1e6:.1f} MB) - raw PDFs excluded")
try:
    subprocess.check_call(["git", "bundle", "create", str(dist / "policy-rag.bundle"), "--all"], cwd=ROOT)
    print("wrote dist/policy-rag.bundle (clone with: git clone policy-rag.bundle)")
except Exception as e:
    print("git bundle skipped:", e)
