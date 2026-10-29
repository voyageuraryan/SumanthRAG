"""End-to-end path: question -> retrieval -> gate 1 -> generator (gate 2) -> citations + support diagnostic -> response.

    from src.pipeline import Pipeline
    Pipeline("A").answer("How many graduate credit hours can I transfer?")

Outcomes (what the user sees):
  answered  the system states an answer with citations
  referred  it says the detail is not in the documents and points to where it is published (cites that passage)
  refused   it says the documents do not answer the question (gate 1 or gate 2)
"""
import time
from .common import load_json, read_jsonl, sha256_file, ROOT, config_hash, code_revision
from .retrievers import get_retriever
from .generator import OllamaGenerator, load_prompt, build_user_message, parse_reply
from .support_check import check_answer, CITE

ADVISORY = "Advisory only. Verify against the official ATU document before acting."


class Pipeline:
    def __init__(self, condition="A", generator=None, cfg=None):
        self.cfg = cfg or load_json("configs/generation.json")
        self.condition = condition
        self.chunks = read_jsonl("data/processed/chunks.jsonl")
        self.by_id = {c["chunk_id"]: c for c in self.chunks}
        self.retriever = get_retriever(condition, self.chunks)
        self.gen = generator or OllamaGenerator(self.cfg)
        pv = self.cfg["prompts"]["closed_book" if condition == "0" else "grounded"]
        self.prompt_version = pv
        self.system_prompt, self.prompt_sha = load_prompt(pv)
        self.tau = self.cfg["gates"]["gate1_retrieval_tau"].get(condition, 0.0)
        self.k = self.cfg["retrieval"]["top_k"]

    def versions(self):
        """Everything needed to reproduce a response: data, code, config, prompt, retriever, model build."""
        return {"condition": self.condition, "generation_config_id": self.cfg["config_id"],
                "generation_config_hash": config_hash(self.cfg),
                "pipeline_config_hash": config_hash(load_json("configs/pipeline.json")),
                "chunks_sha256": sha256_file(ROOT / "data/processed/chunks.jsonl")[:16],
                "prompt_version": self.prompt_version, "prompt_sha": self.prompt_sha,
                "retriever": self.retriever.describe(), "generator": self.gen.info(), **code_revision()}

    def answer(self, question, doc_filter=None):
        t0 = time.time()
        question = (question or "").strip()
        if not question or len(question) > 500:
            raise ValueError("question must be 1-500 characters")
        hits = self.retriever.search(question, self.k, doc_filter)
        top_norm = hits[0]["score_norm"] if hits else None
        gate1_pass = self.condition == "0" or (top_norm is not None and top_norm >= self.tau)
        resp = {"question": question, "condition": self.condition, "doc_filter": doc_filter,
                "retrieved": [{k: h[k] for k in ("rank", "chunk_id", "score", "score_norm", "doc_id", "heading", "pages")} for h in hits],
                "gate1": {"top_score_norm": top_norm, "tau": self.tau, "passed": gate1_pass}}
        if not gate1_pass:
            resp.update(status="insufficient", outcome="refused", refused_by="gate1",
                        answer="I could not find this in the ATU policy documents I have access to.",
                        citations=[], generation=None, support=None)
        else:
            g = self.gen.generate(self.system_prompt, build_user_message(question, hits))
            parsed = parse_reply(g["raw"])
            status = parsed["status"]
            resp["generation"] = {**g, "parse_ok": parsed["parse_ok"]}
            supplied = {h["chunk_id"]: h["body"] for h in hits}
            cited = list(dict.fromkeys(CITE.findall(parsed["answer"])))
            resp["citations"] = [{"chunk_id": c, "supplied": c in supplied, "doc": self.by_id[c]["doc_title"] if c in self.by_id else None,
                                  "section": " > ".join(self.by_id[c]["heading_path"]) if c in self.by_id else None,
                                  "pages": [self.by_id[c]["page_start"], self.by_id[c]["page_end"]] if c in self.by_id else None}
                                 for c in cited]
            resp["support"] = check_answer(parsed["answer"], supplied) if (status != "insufficient" and hits) else None
            resp.update(status=status, answer=parsed["answer"],
                        outcome={"answer": "answered", "refer": "referred", "insufficient": "refused"}[status],
                        refused_by="gate2" if status == "insufficient" else None)
        resp["abstained"] = resp["outcome"] != "answered"
        resp["passages"] = [{"chunk_id": h["chunk_id"], "doc_title": h["doc_title"], "heading": h["heading"],
                             "pages": h["pages"], "score": h["score"], "body": h["body"]} for h in hits]
        resp["advisory"] = ADVISORY
        resp["latency_ms"] = round((time.time() - t0) * 1000)
        return resp
