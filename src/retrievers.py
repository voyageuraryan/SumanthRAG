"""Retrieval conditions behind one switch.

  0 = no retrieval (closed-book reference: what an ungrounded model does)
  A = BM25 baseline (Milestone 2)                     -- runs everywhere
  B = dense bge-small-en-v1.5, exact cosine (numpy)   -- needs `pip install -r requirements-dense.txt`
      294 chunks need no FAISS: exact search takes < 1 ms (departure from the M2 plan, recorded).
Every retriever returns hits with `score` (native scale) and `score_norm` (0-1, used by gate 1).
"""
import hashlib
import numpy as np
from .common import ROOT, load_json, read_jsonl, sha256_file
from .bm25_retriever import BM25Retriever


def chunk_view(c):
    return {"chunk_id": c["chunk_id"], "doc_id": c["doc_id"], "doc_title": c["doc_title"],
            "heading": " > ".join(c["heading_path"]), "pages": [c["page_start"], c["page_end"]], "body": c["body"]}


class NoRetrieval:
    name = "0"
    def search(self, query, k=5, doc_filter=None):
        return []
    def describe(self):
        return {"condition": "0", "retriever": "none"}


class BM25Condition:
    name = "A"
    def __init__(self, chunks):
        self.chunks = chunks; self.r = BM25Retriever(chunks=chunks)
        self.by_id = {c["chunk_id"]: c for c in chunks}
    def search(self, query, k=5, doc_filter=None):
        hits, q = self.r.search(query, k, doc_filter)
        top = self.r.max_score(q) or 1.0
        return [dict(chunk_view(self.by_id[h["chunk_id"]]), rank=h["rank"], score=h["score"],
                     score_norm=round(h["score"] / top, 4)) for h in hits]
    def describe(self):
        return {"condition": "A", "retriever": "bm25", "params": self.r.cfg["bm25"]}


class DenseCondition:
    name = "B"
    def __init__(self, chunks, model_name, query_instruction):
        from sentence_transformers import SentenceTransformer   # optional dependency
        self.chunks = chunks; self.model_name = model_name; self.qi = query_instruction
        self.model = SentenceTransformer(model_name, device="cpu")
        chunks_sha = sha256_file(ROOT / "data/processed/chunks.jsonl")[:12]
        cache = ROOT / f"indexes/dense_{model_name.replace('/', '_')}_{chunks_sha}.npy"
        if cache.exists():
            self.emb = np.load(cache)
        else:
            self.emb = self.model.encode([c["text"] for c in chunks], batch_size=16,
                                         normalize_embeddings=True, show_progress_bar=True)
            cache.parent.mkdir(exist_ok=True); np.save(cache, self.emb)
        self.cache = cache.name
    def search(self, query, k=5, doc_filter=None):
        qv = self.model.encode([self.qi + query], normalize_embeddings=True)[0]
        sims = self.emb @ qv
        if doc_filter:
            sims = np.where([c["doc_id"] == doc_filter for c in self.chunks], sims, -np.inf)
        order = sorted(range(len(sims)), key=lambda i: (-sims[i], self.chunks[i]["chunk_id"]))[:k]
        return [dict(chunk_view(self.chunks[i]), rank=r + 1, score=round(float(sims[i]), 4),
                     score_norm=round(float(sims[i]), 4)) for r, i in enumerate(order)]
    def describe(self):
        import sentence_transformers
        return {"condition": "B", "retriever": "dense", "model": self.model_name,
                "sentence_transformers": sentence_transformers.__version__, "index_cache": self.cache}


def get_retriever(condition, chunks=None):
    chunks = chunks if chunks is not None else read_jsonl("data/processed/chunks.jsonl")
    if condition == "0":
        return NoRetrieval()
    if condition == "A":
        return BM25Condition(chunks)
    if condition == "B":
        d = load_json("configs/generation.json")["dense"]
        return DenseCondition(chunks, d["model"], d["query_instruction"])
    raise ValueError(f"unknown condition {condition!r} (use 0, A or B)")
