"""Pipeline logic tests with a scripted generator and a mock Ollama HTTP server (no model needed).
They check plumbing (parsing, gates, citations, outcomes, versions) - not answer quality."""
import json, threading
from http.server import BaseHTTPRequestHandler, HTTPServer
import pytest
from src.pipeline import Pipeline
from src.generator import ScriptedGenerator, OllamaGenerator, parse_reply
from src.common import load_json

Q = "How many graduate credit hours can I transfer in from another university?"

def test_answer_with_valid_citation():
    g = ScriptedGenerator(['{"status":"answer","answer":"Up to 50% of the coursework may be transferred [GC2627-0051]."}'])
    r = Pipeline("A", generator=g).answer(Q)
    assert r["outcome"] == "answered" and not r["abstained"]
    assert r["citations"][0]["chunk_id"] == "GC2627-0051" and r["citations"][0]["supplied"]
    assert r["retrieved"][1]["chunk_id"] == "GC2627-0051"          # rank 2 for BM25, as in M2
    assert r["support"]["n_sentences"] == 1

def test_refer_and_insufficient_are_abstentions():
    g = ScriptedGenerator(['{"status":"refer","answer":"The fine is not in the documents; fines are published in the ATU parking map [GC2627-0151]."}',
                           '{"status":"insufficient","answer":"The documents do not answer this."}'])
    p = Pipeline("A", generator=g)
    r1 = p.answer("What is the parking fine for parking in a faculty space?")
    r2 = p.answer("What time does the cafeteria open on Sunday?")
    assert (r1["outcome"], r1["abstained"]) == ("referred", True)
    assert (r2["outcome"], r2["refused_by"]) == ("refused", "gate2")

def test_unsupplied_citation_is_flagged():
    g = ScriptedGenerator(['{"status":"answer","answer":"Something [SH2026-0001]."}'])
    r = Pipeline("A", generator=g).answer(Q)
    assert r["citations"][0]["supplied"] is False

def test_gate1_refuses_without_calling_generator():
    cfg = load_json("configs/generation.json"); cfg["gates"]["gate1_retrieval_tau"]["A"] = 0.99
    r = Pipeline("A", generator=ScriptedGenerator([]), cfg=cfg).answer(Q)   # empty script: a call would fail
    assert r["outcome"] == "refused" and r["refused_by"] == "gate1" and r["generation"] is None

def test_closed_book_condition_has_no_passages():
    g = ScriptedGenerator(['{"status":"answer","answer":"Usually 6 credit hours."}'])
    r = Pipeline("0", generator=g).answer(Q)
    assert r["retrieved"] == [] and r["outcome"] == "answered" and r["support"] is None

def test_doc_filter():
    g = ScriptedGenerator(['{"status":"insufficient","answer":"x"}'])
    r = Pipeline("A", generator=g).answer(Q, doc_filter="SH2026")
    assert all(h["doc_id"] == "SH2026" for h in r["retrieved"])

def test_parse_reply_tolerates_non_json():
    assert parse_reply("INSUFFICIENT_EVIDENCE")["status"] == "insufficient"
    assert parse_reply('Sure! {"status":"refer","answer":"see map"}')["status"] == "refer"
    assert parse_reply("plain text")["parse_ok"] is False

def test_input_validation():
    with pytest.raises(ValueError):
        Pipeline("A", generator=ScriptedGenerator([])).answer("   ")

class _Mock(BaseHTTPRequestHandler):
    seen = []
    def log_message(self, *a): pass
    def _send(self, obj):
        b = json.dumps(obj).encode(); self.send_response(200); self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)
    def do_GET(self):
        if self.path == "/api/tags":
            self._send({"models": [{"name": "llama3.1:8b", "model": "llama3.1:8b", "digest": "sha256:abc123", "details": {"quantization_level": "Q4_K_M"}}]})
        else:
            self._send({"version": "0.0-mock"})
    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"]))); _Mock.seen.append(body)
        self._send({"message": {"content": '{"status":"answer","answer":"Up to 50% [GC2627-0051]."}'}, "eval_count": 12, "eval_duration": 1e9})

def test_ollama_http_contract(monkeypatch):
    srv = HTTPServer(("127.0.0.1", 0), _Mock); threading.Thread(target=srv.serve_forever, daemon=True).start()
    monkeypatch.setenv("OLLAMA_HOST", f"http://127.0.0.1:{srv.server_port}")
    p = Pipeline("A", generator=OllamaGenerator(load_json("configs/generation.json")))
    v = p.versions(); r = p.answer(Q); srv.shutdown()
    assert v["generator"]["digest"] == "sha256:abc123" and r["outcome"] == "answered"
    sent = _Mock.seen[-1]
    assert sent["options"]["temperature"] == 0 and sent["options"]["seed"] == 13 and sent["format"]["required"] == ["status", "answer"]
    assert "GC2627-0051" in sent["messages"][1]["content"] and sent["messages"][0]["role"] == "system"
