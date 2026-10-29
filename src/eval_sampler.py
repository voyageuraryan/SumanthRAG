"""Seeded, stratified assignment of source passages for evaluation-question authoring.

Why: if the author picks passages freely, the test set drifts toward easy, memorable passages
(selection bias). Here the passages are drawn at random, proportional to section size, with a
fixed seed, BEFORE any retrieval tuning happens. The author then writes one question per row.
Usage:  python -m src.eval_sampler   ->  eval/authoring_plan.csv
"""
import csv, random
from collections import defaultdict
from .common import ROOT, load_json, read_jsonl, log_run

PLAN = {  # split -> type -> count   (matches the Milestone 1 design: 10 dev + 40 test)
    "dev":  {"single": 4, "multihop": 2, "unanswerable": 2, "nearmiss": 2},
    "test": {"single": 16, "multihop": 8, "unanswerable": 8, "nearmiss": 8},
}
# Gold passages of examples already shown in Milestone 1/2 documents are demonstration-only.
DEMO_EXCLUDED = {"GC2627-0051", "GC2627-0054", "GC2627-0150", "GC2627-0151", "GC2627-0072",
                 "SH2026-0209", "GC2627-0044", "GC2627-0033", "GC2627-0034", "GC2627-0035"}

def main():
    seed = load_json("configs/pipeline.json")["seed"]
    rng = random.Random(seed)
    C = [c for c in read_jsonl("data/processed/chunks.jsonl")
         if c["n_words"] >= 40 and c["chunk_id"] not in DEMO_EXCLUDED
         and not any(h in ("Where to Get Help", "Emergency Contacts") for h in c["heading_path"])]
    by_sec = defaultdict(list)
    for c in C:
        by_sec[(c["doc_id"], c["heading_path"][0] if c["heading_path"] else "")].append(c)
    pool = [c for v in by_sec.values() for c in v]
    rng.shuffle(pool)           # uniform over chunks == proportional to section size
    used, rows, n = set(), [], 0
    def sec(c):  # handbook nests one level deeper than the catalog
        return (c["doc_id"], tuple(c["heading_path"][:2 if c["doc_id"] == "SH2026" else 1]))
    def take(pred=lambda c: True):
        for c in pool:
            if c["chunk_id"] not in used and pred(c):
                used.add(c["chunk_id"]); return c
        raise RuntimeError("pool exhausted")
    for split in ("dev", "test"):
        for qtype, k in PLAN[split].items():
            for _ in range(k):
                n += 1; iid = f"{split[0].upper()}{n:02d}"
                if qtype == "unanswerable":
                    rows.append([iid, split, qtype, "", "", "Write a plausible graduate-student question whose answer is NOT in the corpus; run `python -m src.eval_validate --check-absent \"<keywords>\"` to confirm."])
                elif qtype == "multihop":
                    free = [c for c in pool if c["chunk_id"] not in used]
                    a = next(c for c in free if sum(sec(x) == sec(c) for x in free) >= 2)
                    used.add(a["chunk_id"])
                    b = take(lambda c: sec(c) == sec(a))
                    rows.append([iid, split, qtype, a["chunk_id"], b["chunk_id"], f'{" > ".join(a["heading_path"])} + {" > ".join(b["heading_path"])} -- Needs BOTH passages. If no natural link exists, mark REDRAW in the log; never hand-pick a replacement.'])
                else:
                    a = take()
                    note = ("Write a question that SOUNDS answerable from this passage's topic but asks for a detail it does not contain."
                            if qtype == "nearmiss" else "Write a question answered by this passage alone.")
                    rows.append([iid, split, qtype, a["chunk_id"], "", f'{" > ".join(a["heading_path"])} -- {note}'])
    # Spare multi-hop pairs, drawn from the SAME seeded sequence after the plan. Used in order (S1, S2, ...)
    # only when a planned pair has no natural link (REDRAW) - never hand-picked.
    spares = []
    for k in range(6):
        free = [c for c in pool if c["chunk_id"] not in used]
        a = next(c for c in free if sum(sec(x) == sec(c) for x in free) >= 2)
        used.add(a["chunk_id"]); b = take(lambda c: sec(c) == sec(a))
        spares.append([f"S{k+1}", a["chunk_id"], b["chunk_id"], f'{" > ".join(a["heading_path"])} + {" > ".join(b["heading_path"])}'])
    with open(ROOT / "eval/authoring_spares.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f); w.writerow(["spare_id", "source_chunk_1", "source_chunk_2", "sections"]); w.writerows(spares)
    with open(ROOT / "eval/authoring_plan.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f); w.writerow(["item_id", "split", "type", "source_chunk_1", "source_chunk_2", "guidance"]); w.writerows(rows)
    print(f"{len(rows)} rows written (seed={seed}, eligible chunks={len(C)})")
    print("run_id:", log_run("eval_sampling", {"seed": seed, "eligible_chunks": len(C), "plan": PLAN, "demo_excluded": sorted(DEMO_EXCLUDED)}))

if __name__ == "__main__":
    main()
