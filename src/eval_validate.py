"""Validate evaluation files and enforce leakage controls.

  python -m src.eval_validate                    # checks both splits; FAILS if a split is empty or the wrong size
  python -m src.eval_validate --split dev        # check only the dev split (allowed while test is being written)
  python -m src.eval_validate --check-absent "parking fine amount"   # is a topic really absent?
  python -m src.eval_validate --lock             # validate everything, then freeze the test file (SHA-256)

Milestone 2 feedback fixed here: an empty or wrongly sized set used to pass. Now the expected
composition (from src/eval_sampler.PLAN) is enforced per split and per type, every planned item_id must
be present exactly once, and --lock refuses unless both splits are complete and valid.
"""
import argparse, csv, json, re, sys
from collections import Counter
from .common import ROOT, read_jsonl, sha256_file, log_run
from .eval_sampler import PLAN

REQUIRED = {"id": str, "split": str, "type": str, "question": str, "gold_answer": str,
            "gold_chunk_ids": list, "answerable": bool, "expected_behavior": str, "written_on": str}
TYPES = {"single", "multihop", "unanswerable", "nearmiss"}
BEHAVIOR = {"answer", "abstain", "refer"}
# allowed (type -> behaviours, answerable flag)
TYPE_RULES = {"single": ({"answer"}, True), "multihop": ({"answer"}, True),
              "unanswerable": ({"abstain"}, False), "nearmiss": ({"abstain", "refer"}, False)}
DEMO_QUERIES = ["how many graduate credit hours can i transfer in from another university",
                "what is the parking fine for parking in a faculty space", "can i take a semester off",
                "what is the last day to drop a fall class with a w",
                "what gre score do i need for the mba program", "what time does the cafeteria open on sunday"]


def norm(q): return " ".join(re.findall(r"[a-z0-9]+", q.lower()))
def jacc(a, b):
    A, B = set(norm(a).split()), set(norm(b).split()); return len(A & B) / max(1, len(A | B))


def load(split):
    p = ROOT / f"eval/questions_{split}.jsonl"
    return read_jsonl(f"eval/questions_{split}.jsonl") if p.exists() and p.stat().st_size else []


def planned_ids():
    with open(ROOT / "eval/authoring_plan.csv", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    return {r["item_id"]: r for r in rows}


def check_split(split, items, chunk_ids, plan, errs):
    want = PLAN[split]; n_want = sum(want.values())
    if not items:
        errs.append(f"{split}: EMPTY (expected {n_want} items)"); return
    if len(items) != n_want:
        errs.append(f"{split}: {len(items)} items, expected exactly {n_want}")
    got = Counter(it.get("type") for it in items)
    for t, k in want.items():
        if got.get(t, 0) != k:
            errs.append(f"{split}: {got.get(t, 0)} '{t}' items, expected {k}")
    ids = Counter(it.get("id") for it in items)
    for i, c in ids.items():
        if c > 1: errs.append(f"{split}: id {i} appears {c} times")
    planned = {i for i, r in plan.items() if r["split"] == split}
    missing = planned - set(ids); extra = set(ids) - planned
    if missing: errs.append(f"{split}: planned items missing: {sorted(missing)}")
    if extra: errs.append(f"{split}: items not in authoring_plan.csv: {sorted(extra)}")
    for it in items:
        iid = it.get("id")
        for k, t in REQUIRED.items():
            if not isinstance(it.get(k), t): errs.append(f"{iid}: field '{k}' missing or wrong type")
        if it.get("split") != split: errs.append(f"{iid}: split field says {it.get('split')!r}, file is {split}")
        if not str(it.get("question", "")).strip(): errs.append(f"{iid}: empty question")
        if not str(it.get("gold_answer", "")).strip(): errs.append(f"{iid}: empty gold_answer")
        rule = TYPE_RULES.get(it.get("type"))
        if not rule:
            errs.append(f"{iid}: bad type {it.get('type')!r}"); continue
        if it.get("expected_behavior") not in rule[0]:
            errs.append(f"{iid}: type {it['type']} needs expected_behavior in {sorted(rule[0])}")
        if it.get("answerable") is not rule[1]:
            errs.append(f"{iid}: type {it['type']} must have answerable={rule[1]}")
        groups = it.get("gold_chunk_ids") or []
        for g in groups:
            if not isinstance(g, list) or not g: errs.append(f"{iid}: each gold group must be a non-empty list")
            for cid in (g if isinstance(g, list) else []):
                if cid not in chunk_ids: errs.append(f"{iid}: unknown chunk {cid}")
        if it.get("type") == "single" and len(groups) != 1: errs.append(f"{iid}: single needs exactly 1 gold group")
        if it.get("type") == "multihop" and len(groups) < 2: errs.append(f"{iid}: multihop needs >= 2 gold groups")
        if it.get("type") == "unanswerable" and groups: errs.append(f"{iid}: unanswerable must have no gold chunks")
        if it.get("expected_behavior") == "refer" and not groups:
            errs.append(f"{iid}: refer items must list the passage that says where the detail is published")
        if any(jacc(it.get("question", ""), d) > 0.6 for d in DEMO_QUERIES):
            errs.append(f"{iid}: too close to a demo query (leakage)")


def validate(only=None, quiet=False):
    chunk_ids = {c["chunk_id"] for c in read_jsonl("data/processed/chunks.jsonl")}
    plan = planned_ids(); errs = []
    splits = [only] if only else ["dev", "test"]
    data = {s: load(s) for s in ("dev", "test")}
    for s in splits:
        check_split(s, data[s], chunk_ids, plan, errs)
    if not only:
        for t in data["test"]:
            for d in data["dev"]:
                if jacc(t["question"], d["question"]) > 0.6:
                    errs.append(f'{t["id"]} ~ {d["id"]}: dev/test near-duplicate')
        lock = ROOT / "eval/LOCK.json"
        if lock.exists():
            want = json.load(open(lock, encoding="utf-8"))["test_sha256"]
            if sha256_file(ROOT / "eval/questions_test.jsonl") != want:
                errs.append("TEST SET CHANGED AFTER LOCK")
    if not quiet:
        print(" ".join(f"{s}={len(data[s])}" for s in ("dev", "test")) + f" errors={len(errs)}")
        for e in errs: print(" -", e)
    return not errs


def check_absent(phrase):
    C = read_jsonl("data/processed/chunks.jsonl")
    terms = [t for t in norm(phrase).split() if len(t) > 3]
    hits = [(c["chunk_id"], sum(t in norm(c["body"]) for t in terms)) for c in C]
    hits = sorted([h for h in hits if h[1]], key=lambda h: -h[1])[:8]
    print(f"terms={terms}\nchunks containing any term: {hits}\n"
          "Read the top chunks: if any states the answer, the item is NOT unanswerable "
          "(reclassify as near-miss/refer or answerable).")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--check-absent"); ap.add_argument("--lock", action="store_true")
    ap.add_argument("--split", choices=["dev", "test"])
    a = ap.parse_args()
    if a.check_absent:
        check_absent(a.check_absent); sys.exit()
    if a.lock and a.split:
        sys.exit("--lock validates both splits; do not combine with --split")
    ok = validate(a.split)
    if a.lock:
        if not ok: sys.exit("NOT LOCKED: fix the errors above first")
        if (ROOT / "eval/LOCK.json").exists(): sys.exit("already locked")
        rec = {"test_sha256": sha256_file(ROOT / "eval/questions_test.jsonl"),
               "dev_sha256": sha256_file(ROOT / "eval/questions_dev.jsonl")}
        json.dump(rec, open(ROOT / "eval/LOCK.json", "w"), indent=2)
        print("test set locked; run_id:", log_run("eval_lock", rec))
    sys.exit(0 if ok else 1)
