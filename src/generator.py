"""Generator: a local LLM served by Ollama (no API keys, nothing leaves the machine).

The prompt asks for JSON {"status": answer|refer|insufficient, "answer": "..."}; Ollama's structured-output
`format` (a JSON schema) makes the reply parseable. Every call returns the exact model digest, prompt version,
options and timing so a result can be traced to the model build that produced it.
"""
import json, os, time, urllib.error, urllib.request
from .common import ROOT, sha256_text

SCHEMA = {"type": "object", "properties": {"status": {"type": "string", "enum": ["answer", "refer", "insufficient"]},
                                           "answer": {"type": "string"}}, "required": ["status", "answer"]}


def load_prompt(version):
    text = (ROOT / f"prompts/{version}.txt").read_text(encoding="utf-8")
    return text, sha256_text(text)[:12]


def build_user_message(question, passages):
    if not passages:
        return f"Question: {question}"
    blocks = []
    for p in passages:
        blocks.append(f'<passage id="{p["chunk_id"]}" source="{p["doc_title"]}" section="{p["heading"]}" '
                      f'pages="{p["pages"][0]}-{p["pages"][1]}">\n{p["body"]}\n</passage>')
    return "Passages:\n" + "\n\n".join(blocks) + f"\n\nQuestion: {question}"


def parse_reply(raw):
    """Tolerant parse: JSON object if possible, else treat the text as an answer and flag it."""
    try:
        start, end = raw.index("{"), raw.rindex("}") + 1
        obj = json.loads(raw[start:end])
        status = str(obj.get("status", "")).strip().lower()
        if status not in ("answer", "refer", "insufficient"):
            return {"status": "answer", "answer": str(obj.get("answer", raw)), "parse_ok": False}
        return {"status": status, "answer": str(obj.get("answer", "")).strip(), "parse_ok": True}
    except (ValueError, json.JSONDecodeError):
        up = raw.strip().upper()
        status = "insufficient" if up.startswith("INSUFFICIENT") else "answer"
        return {"status": status, "answer": raw.strip(), "parse_ok": False}


class OllamaGenerator:
    def __init__(self, cfg):
        g = cfg["generator"]
        self.host = os.environ.get(g["host_env"], g["host_default"]).rstrip("/")
        self.model = os.environ.get("POLICYRAG_MODEL", g["model"])
        self.options = g["options"]; self.timeout = g["timeout_s"]
        self._info = None

    def _post(self, path, body, timeout=None):
        req = urllib.request.Request(self.host + path, json.dumps(body).encode(), {"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=timeout or self.timeout) as r:
            return json.load(r)

    def info(self):
        """Model digest + quantisation, read from the local Ollama server (recorded in every run)."""
        if self._info is None:
            try:
                with urllib.request.urlopen(self.host + "/api/tags", timeout=10) as r:
                    tags = json.load(r)["models"]
                m = next((t for t in tags if t["name"] == self.model or t["model"] == self.model), None)
                if m is None:
                    raise StopIteration(f"model {self.model} is not installed")
                ver = json.load(urllib.request.urlopen(self.host + "/api/version", timeout=10)).get("version")
                self._info = {"backend": "ollama", "model": self.model, "ollama_version": ver,
                              "digest": m and m.get("digest"), "details": m and m.get("details")}
            except (urllib.error.URLError, OSError, StopIteration) as e:
                self._info = {"backend": "ollama", "model": self.model, "error": f"ollama not ready: {e}"}
        return self._info

    def generate(self, system, user):
        body = {"model": self.model, "stream": False, "format": SCHEMA, "options": self.options,
                "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}
        t = time.time()
        r = self._post("/api/chat", body)
        raw = r["message"]["content"]
        return {"raw": raw, "latency_ms": round((time.time() - t) * 1000),
                "eval_count": r.get("eval_count"), "prompt_eval_count": r.get("prompt_eval_count"),
                "tokens_per_s": round(r["eval_count"] / (r["eval_duration"] / 1e9), 1) if r.get("eval_duration") else None}


class ScriptedGenerator:
    """Deterministic stand-in used ONLY by the unit tests (no model). Never used for reported results."""
    def __init__(self, replies):
        self.replies = list(replies); self.model = "scripted-test-double"
    def info(self):
        return {"backend": "scripted", "model": self.model}
    def generate(self, system, user):
        return {"raw": self.replies.pop(0), "latency_ms": 0, "eval_count": 0, "prompt_eval_count": 0, "tokens_per_s": None}
