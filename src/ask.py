"""Ask one question from the command line (the quickest live demo).

  python -m src.ask "How many graduate credit hours can I transfer in?"            # condition A
  python -m src.ask "..." --condition 0         # closed-book reference (no retrieval)
  python -m src.ask "..." --doc GC2627 --json   # only the Graduate Catalog; print the full JSON
Every question is appended to results/queries.jsonl with all version information.
"""
import argparse, json, textwrap
from .pipeline import Pipeline
from .common import ROOT, code_revision

def log_query(resp, versions):
    with open(ROOT / "results/queries.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps({"versions": versions, "response": resp}, ensure_ascii=False) + "\n")

def show(r):
    w = lambda t: textwrap.fill(t, 100, initial_indent="  ", subsequent_indent="  ")
    head = {"answered": "ANSWER", "referred": "NOT IN THE DOCUMENTS - REFERRAL", "refused": "NO ANSWER (abstained)"}[r["outcome"]]
    print(f"\n{head}\n" + w(r["answer"]))
    if r["citations"]:
        print("\nCITATIONS")
        for c in r["citations"]:
            print(f"  [{c['chunk_id']}] {c['doc']} - {c['section']} - p.{c['pages'][0]}" + ("" if c["supplied"] else "   (!) not among retrieved passages"))
    if r["retrieved"]:
        print("\nRETRIEVED PASSAGES")
        for h in r["retrieved"]:
            print(f"  [{h['rank']}] {h['chunk_id']} score {h['score']} (normalized {h['score_norm']})  {h['heading'][:70]}")
    if r.get("support"):
        print(f"\nSUPPORT CHECK (diagnostic only): {r['support']['n_flagged']}/{r['support']['n_sentences']} sentences flagged {r['support']['flag_counts']}")
    print(f"\nABSTAINED {r['abstained']}   status={r['status']}   latency {r['latency_ms']/1000:.1f}s")
    print(f"! {r['advisory']}")

if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("question"); ap.add_argument("--condition", default="A")
    ap.add_argument("--doc", choices=["GC2627", "SH2026"]); ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    p = Pipeline(a.condition); v = p.versions()
    if v["generator"].get("error"):
        raise SystemExit(v["generator"]["error"] + "  -> start Ollama and run: ollama pull " + v["generator"]["model"])
    r = p.answer(a.question, a.doc); log_query(r, v)
    print(json.dumps(r, indent=1, ensure_ascii=False) if a.json else "", end="")
    if not a.json: show(r)
