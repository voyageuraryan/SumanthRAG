"""Does the lexical support check actually separate supported from unsupported sentences?

Cases (all checked against the passage they claim to come from):
  handwritten  eval/diagnostics/support_cases_handwritten.jsonl
               paraphrase      correct, reworded            -> should PASS
               wrong_condition wrong meaning, similar words -> should be FLAGGED
  generated    from passages NOT used by the evaluation plan (seed 13):
               verbatim        a real sentence              -> should PASS
               number_changed  one number altered           -> should be FLAGGED
               negation_flip   'not' inserted / removed     -> should be FLAGGED
               topic_swap      sentence from another section -> should be FLAGGED
Usage: python -m src.checks.support_check_eval   -> reports/support_check_diagnostic.json
"""
import csv, json, random, re
from collections import defaultdict
from ..common import ROOT, read_jsonl, load_json, log_run
from ..support_check import check_sentence, split_sentences, NUMWORDS

MODALS = re.compile(r"\b(must|may|will|can|should|is|are|shall)\b")


def flip_negation(s):
    if re.search(r"\bnot\b", s): return re.sub(r"\s*\bnot\b", "", s, count=1)
    if re.match(r"No\s", s): return re.sub(r"^No\s", "A ", s)
    return MODALS.sub(lambda m: m.group(1) + " not", s, count=1) if MODALS.search(s) else None


def change_number(s):
    m = re.search(r"\b\d+\b", s)
    if m:
        n = int(m.group()); return s[:m.start()] + str(n + 3 if n < 50 else n * 2) + s[m.end():]
    for w, v in NUMWORDS.items():
        if re.search(rf"\b{w}\b", s, re.I):
            new = next(k for k, x in NUMWORDS.items() if x == (v + 3 if v + 3 in NUMWORDS.values() else 10))
            return re.sub(rf"\b{w}\b", new, s, count=1, flags=re.I)
    return None


def main():
    seed = load_json("configs/pipeline.json")["seed"]; rng = random.Random(seed)
    chunks = {c["chunk_id"]: c for c in read_jsonl("data/processed/chunks.jsonl")}
    assigned = set()
    for f in ("eval/authoring_plan.csv", "eval/authoring_spares.csv"):
        for r in csv.DictReader(open(ROOT / f, encoding="utf-8")):
            assigned |= {r["source_chunk_1"], r["source_chunk_2"]}
    free = sorted(c for c in chunks if c not in assigned and chunks[c]["n_words"] >= 40)
    rng.shuffle(free)
    cases = []
    for r in read_jsonl("eval/diagnostics/support_cases_handwritten.jsonl"):
        cases.append({"id": r["case_id"], "kind": r["kind"], "supported": r["supported"], "sentence": r["sentence"], "chunk": r["chunk_id"]})
    k = 0
    for cid in free:
        sents = [s for s in split_sentences(chunks[cid]["body"]) if 8 <= len(s.split()) <= 45 and not s.startswith("-")]
        if not sents: continue
        s = rng.choice(sents); k += 1
        cases.append({"id": f"V{k:02d}", "kind": "verbatim", "supported": True, "sentence": s, "chunk": cid})
        if (nc := change_number(s)): cases.append({"id": f"N{k:02d}", "kind": "number_changed", "supported": False, "sentence": nc, "chunk": cid})
        if (nf := flip_negation(s)) and nf != s: cases.append({"id": f"G{k:02d}", "kind": "negation_flip", "supported": False, "sentence": nf, "chunk": cid})
        other = next(o for o in free if chunks[o]["heading_path"][:1] != chunks[cid]["heading_path"][:1])
        cases.append({"id": f"X{k:02d}", "kind": "topic_swap", "supported": False, "sentence": s, "chunk": other})
        if k == 25: break
    res = defaultdict(lambda: defaultdict(int))
    for c in cases:
        r = check_sentence(c["sentence"], [chunks[c["chunk"]]["body"]])
        c["flags"] = r["flags"]
        bucket = res[c["kind"]]; bucket["n"] += 1
        for f in ("low_overlap", "number_not_in_source", "negation_mismatch"):
            bucket[f] += f in r["flags"]
        bucket["any_flag"] += bool(r["flags"])
    table = {k: dict(v) for k, v in res.items()}
    sup = [c for c in cases if c["supported"]]; uns = [c for c in cases if not c["supported"]]
    summary = {"n_cases": len(cases), "by_kind": table,
               "supported_passed_rate": round(sum(not c["flags"] for c in sup) / len(sup), 3),
               "unsupported_flagged_rate": round(sum(bool(c["flags"]) for c in uns) / len(uns), 3)}
    out = {"summary": summary, "cases": cases}
    json.dump(out, open(ROOT / "reports/support_check_diagnostic.json", "w"), indent=1)
    print(json.dumps(summary, indent=1))
    print("run_id:", log_run("support_check_diagnostic", summary))


if __name__ == "__main__":
    main()
