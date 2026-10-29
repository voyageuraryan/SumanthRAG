"""Read a filled-in blind scoring sheet, un-blind it, and compute the manual metrics per condition.

  python -m src.score_import results/eval/<run_id>

Rubrics (src/metrics.py): correctness 0/1/2 (answerable items that were answered), faithfulness 0/1 and
citation accuracy 0/1 (any answered or referred reply), asserts_detail Y/N (unanswerable + near-miss items:
did the reply state the missing detail?). Blank cells are treated as not scored.
"""
import csv, json, sys
from pathlib import Path
from .common import ROOT, read_jsonl, log_run
from .metrics import evaluate, CORRECTNESS_RUBRIC

def num(v):
    v = (v or "").strip()
    return float(v) if v.replace(".", "", 1).isdigit() else None

def main():
    d = ROOT / sys.argv[1] if not Path(sys.argv[1]).is_absolute() else Path(sys.argv[1])
    key = {r["blind_id"]: r for r in csv.DictReader(open(d / "scoring_key.csv", encoding="utf-8"))}
    sheet = list(csv.DictReader(open(d / "scoring_sheet.csv", encoding="utf-8-sig")))
    cfg = json.load(open(d / "run_config.json", encoding="utf-8"))
    items = read_jsonl(cfg["items_file"])
    by_cond = {}
    for row in sheet:
        k = key[row["blind_id"]]
        yn = (row.get("asserts_detail_Y_N") or "").strip().upper()[:1]
        by_cond.setdefault(k["condition"], {})[k["item_id"]] = {
            "correctness": num(row.get("correctness_0_1_2")), "faithfulness": num(row.get("faithfulness_0_1")),
            "citation": num(row.get("citation_accuracy_0_1")), "asserts_detail": {"Y": True, "N": False}.get(yn)}
    result = {}
    for cond, manual in by_cond.items():
        resp = {json.loads(l)["item_id"]: json.loads(l) for l in open(d / f"outputs_{cond}.jsonl", encoding="utf-8")}
        m = evaluate(items, resp, manual=manual)   # safety re-labelled with the human asserts_detail judgments
        def mean(key, pred=lambda i: True):
            v = [manual[i["id"]][key] for i in items if pred(i) and manual.get(i["id"], {}).get(key) is not None]
            return {"mean": round(sum(v) / len(v), 3), "n_scored": len(v)} if v else None
        m["manual"] = {"correctness_0_2": mean("correctness", lambda i: i["answerable"]),
                       "faithfulness": mean("faithfulness"), "citation_accuracy": mean("citation"),
                       "n_asserts_detail_judged": sum(manual.get(i["id"], {}).get("asserts_detail") is not None for i in items if not i["answerable"])}
        result[cond] = m
    json.dump(result, open(d / "metrics_scored.json", "w"), indent=2)
    print(json.dumps(result, indent=1))
    print("run_id:", log_run("manual_scoring", {"eval_run_id": cfg["run_id"], "metrics": result}))

if __name__ == "__main__":
    main()
