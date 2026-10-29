"""Shared helpers: paths, config loading, hashing, normalization, run logging."""
import hashlib, json, os, re, subprocess, time, unicodedata, uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

def load_json(rel):
    with open(ROOT / rel, encoding="utf-8") as f:
        return json.load(f)

def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()

def sha256_text(s):
    return hashlib.sha256(s.encode("utf-8")).hexdigest()

def config_hash(cfg):
    return sha256_text(json.dumps(cfg, sort_keys=True))[:12]

# Characters observed in the real PDFs that break lexical matching.
_INVISIBLE = {"​": "", "‌": "", "‍": "", "﻿": "", "­": ""}
_SPACES = {" ": " ", " ": " ", " ": " ", " ": " "}

def normalize(text, form="NFKC"):
    """NFKC folds ligatures (U+FB01 'fi' -> 'fi'), then remove zero-width chars and odd spaces."""
    for k, v in _INVISIBLE.items():
        text = text.replace(k, v)
    for k, v in _SPACES.items():
        text = text.replace(k, v)
    text = unicodedata.normalize(form, text)
    text = text.replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"')
    return re.sub(r"[ \t]+", " ", text).strip()

def git_commit():
    try:
        return subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT,
                                       stderr=subprocess.DEVNULL).decode().strip()
    except Exception:
        return "no-git"

def git_dirty():
    try:
        out = subprocess.check_output(["git", "status", "--porcelain", "--", "src", "configs", "prompts"],
                                      cwd=ROOT, stderr=subprocess.DEVNULL).decode().strip()
        return bool(out)
    except Exception:
        return None

def code_sha():
    """Content hash of everything that changes behaviour: code, configs, prompts.
    Recorded in every run so a result is traceable even without git (M2 feedback)."""
    h = hashlib.sha256()
    for sub in ("src", "configs", "prompts"):
        for p in sorted((ROOT / sub).rglob("*")):
            if p.is_file() and p.suffix in {".py", ".json", ".txt"} and "__pycache__" not in p.parts:
                h.update(str(p.relative_to(ROOT)).replace("\\", "/").encode())
                h.update(p.read_bytes().replace(b"\r\n", b"\n"))
    return h.hexdigest()[:12]

def code_revision():
    return {"git_commit": git_commit(), "git_dirty": git_dirty(), "code_sha": code_sha()}

def write_jsonl(rel, rows):
    p = ROOT / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

def read_jsonl(rel):
    with open(ROOT / rel, encoding="utf-8") as f:
        return [json.loads(l) for l in f if l.strip()]

def log_run(kind, payload, rel="results/runs.jsonl"):
    """Append one experiment record. Every result in the report must trace to a run_id here."""
    rec = {"run_id": f"{time.strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:6]}",
           "kind": kind, "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
           **code_revision(), **payload}
    p = ROOT / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return rec["run_id"]
