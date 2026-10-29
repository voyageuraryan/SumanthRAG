"""Web interface: FastAPI service + a minimal page.

  python -m uvicorn src.api:app --port 8000      then open http://127.0.0.1:8000
Endpoints: GET /health, POST /query {"question": str, "doc_filter": "GC2627"|"SH2026"|null, "condition": "A"|"0"|"B"}
"""
from pathlib import Path
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from .pipeline import Pipeline
from .ask import log_query

app = FastAPI(title="PolicyRAG", version="m3")
_pipes = {}

def pipe(cond):
    if cond not in _pipes:
        _pipes[cond] = Pipeline(cond)
    return _pipes[cond]

class Query(BaseModel):
    question: str = Field(min_length=1, max_length=500)
    doc_filter: str | None = None
    condition: str = "A"

@app.get("/")
def index():
    return FileResponse(Path(__file__).parent / "static/index.html")

@app.get("/health")
def health():
    v = pipe("A").versions()
    return {"ok": not v["generator"].get("error"), "generator": v["generator"], "chunks_sha256": v["chunks_sha256"],
            "code_sha": v["code_sha"], "git_commit": v["git_commit"], "prompt": v["prompt_version"]}

@app.post("/query")
def query(q: Query):
    if q.condition not in ("A", "0", "B"):
        raise HTTPException(400, "condition must be A, 0 or B")
    if q.doc_filter not in (None, "", "GC2627", "SH2026"):
        raise HTTPException(400, "doc_filter must be GC2627, SH2026 or empty")
    p = pipe(q.condition); v = p.versions()
    if v["generator"].get("error"):
        raise HTTPException(503, v["generator"]["error"])
    r = p.answer(q.question, q.doc_filter or None); log_query(r, v)
    r["versions"] = {k: v[k] for k in ("condition", "prompt_version", "chunks_sha256", "code_sha", "git_commit")}
    r["versions"]["model"] = v["generator"].get("model"); r["versions"]["digest"] = (v["generator"].get("digest") or "")[:12]
    return r
