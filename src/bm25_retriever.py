"""Condition A baseline: BM25 (Okapi) lexical retrieval over the frozen chunks.

Usage:  python -m src.bm25_retriever "How many graduate credit hours can I transfer?" [--k 5]
Every query is appended to results/runs.jsonl with config + corpus hashes.
"""
import argparse, json, re
from rank_bm25 import BM25Okapi
from .common import load_json, read_jsonl, log_run, config_hash, sha256_file, ROOT

STOP = set("""a an and are as at be by can do does for from has have how i if in is it its my
of on or our shall should that the their them then there these this to was we what when where
which who will with you your""".split())

def tokenize(text, cfg):
    t = text.lower() if cfg["lowercase"] else text
    toks = re.findall(cfg["token_pattern"], t)
    return [w for w in toks if w not in STOP] if cfg["remove_stopwords"] else toks

class BM25Retriever:
    name = "A_bm25"
    def __init__(self, chunks=None, cfg=None):
        self.cfg = cfg or load_json("configs/pipeline.json")
        self.chunks = chunks if chunks is not None else read_jsonl("data/processed/chunks.jsonl")
        b = self.cfg["bm25"]
        # Index the heading path + body: headings carry much of the policy vocabulary.
        self.index = BM25Okapi([tokenize(c["text"], b) for c in self.chunks], k1=b["k1"], b=b["b"])

    def max_score(self, q_tokens):
        """Upper bound of the BM25 score for this query: each term contributes at most idf*(k1+1).
        Dividing by it puts queries of different length/rarity on one 0-1 scale (gate 1)."""
        import math
        k1 = self.cfg["bm25"]["k1"]
        n = self.index.corpus_size
        oov = math.log((n + 0.5) / 0.5)   # idf of a term that occurs in no chunk: it counts against the query
        return sum(max(self.index.idf.get(t, oov), 0.0) * (k1 + 1) for t in q_tokens)

    def search(self, query, k=5, doc_filter=None):
        q = tokenize(query, self.cfg["bm25"])
        scores = self.index.get_scores(q)
        if doc_filter:
            scores = [s if self.chunks[i]["doc_id"] == doc_filter else float("-inf") for i, s in enumerate(scores)]
        order = sorted(range(len(scores)), key=lambda i: (-scores[i], self.chunks[i]["chunk_id"]))[:k]
        return [{"rank": r + 1, "chunk_id": self.chunks[i]["chunk_id"], "score": round(float(scores[i]), 3),
                 "doc_id": self.chunks[i]["doc_id"], "pages": [self.chunks[i]["page_start"], self.chunks[i]["page_end"]],
                 "heading": " > ".join(self.chunks[i]["heading_path"]), "preview": self.chunks[i]["body"][:160]}
                for r, i in enumerate(order)], q

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("query"); ap.add_argument("--k", type=int, default=5)
    ap.add_argument("--tag", default="adhoc", help="e.g. demo, dev, test (test only in Milestone 4)")
    a = ap.parse_args()
    r = BM25Retriever(); hits, qtok = r.search(a.query, a.k)
    rid = log_run("retrieve", {"condition": r.name, "tag": a.tag, "query": a.query, "query_tokens": qtok,
                               "config_hash": config_hash(r.cfg),
                               "chunks_sha256": sha256_file(ROOT / "data/processed/chunks.jsonl")[:16],
                               "results": [{k: h[k] for k in ("rank", "chunk_id", "score")} for h in hits]})
    print(f"query tokens: {qtok}\nrun_id: {rid}")
    for h in hits:
        print(f'[{h["rank"]}] {h["score"]:>7}  {h["chunk_id"]}  p.{h["pages"][0]}  {h["heading"][:80]}\n      {h["preview"][:150]}')

if __name__ == "__main__":
    main()
