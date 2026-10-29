"""Run a fixed question set through the full pipeline and retain every input and output.

  python -m src.run_eval --split demo --conditions A,0        # the 6 Milestone 2 demonstration queries
  python -m src.run_eval --split dev  --conditions A,0        # the 10 dev (pilot) questions
  python -m src.run_eval --split test --conditions A,B --final   # Milestone 4 only; needs eval/LOCK.json

Writes results/eval/<run_id>/:
  run_config.json        versions of data, code, config, prompt, retriever and model build per condition
  outputs_<cond>.jsonl   the full response for every question (answer, citations, passages, scores, timing)
  metrics_auto.json      retrieval, abstention/referral, citation, latency metrics (no human judgment)
  scoring_sheet.csv      BLIND manual-scoring sheet (condition hidden, rows shuffled)
  scoring_key.csv        blind id -> condition (do not open until scoring is done)
  summary.md             human-readable table
and appends one record to results/runs.jsonl.
"""
import argparse, csv, json, random, sys, time, uuid
from .common import ROOT, read_jsonl, log_run, sha256_file
from .metrics import evaluate
from .pipeline import Pipeline
from .eval_validate import validate

SPLIT_FILES = {"demo": "eval/demo_queries.jsonl", "dev": "eval/questions_dev.jsonl", "test": "eval/questions_test.jsonl"}


def load_items(split, final):
    if split == "test":
        if not final:
            sys.exit("The test split is held out until Milestone 4. Re-run with --final only for the formal evaluation.")
        if not (ROOT / "eval/LOCK.json").exists():
            sys.exit("Test set is not locked. Run: python -m src.eval_validate --lock")
        if not validate(quiet=True):
            sys.exit("Evaluation files do not validate (or the test set changed after locking).")
    if split == "dev" and not validate("dev"):
        sys.exit("Dev set does not validate - fix it before running (python -m src.eval_validate --split dev).")
    items = read_jsonl(SPLIT_FILES[split])
    if not items:
        sys.exit(f"{SPLIT_FILES[split]} is empty")
    return items


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--split", required=True, choices=list(SPLIT_FILES))
    ap.add_argument("--conditions", default="A,0")
    ap.add_argument("--final", action="store_true")
    ap.add_argument("--tag", default="")
    a = ap.parse_args()
    items = load_items(a.split, a.final)
    run_id = f"{time.strftime('%Y%m%d-%H%M%S')}-{a.split}-{uuid.uuid4().hex[:4]}"
    out_dir = ROOT / "results/eval" / run_id; out_dir.mkdir(parents=True)
    conds = [c.strip() for c in a.conditions.split(",") if c.strip()]
    run_cfg = {"run_id": run_id, "split": a.split, "items_file": SPLIT_FILES[a.split],
               "items_sha256": sha256_file(ROOT / SPLIT_FILES[a.split]), "n_items": len(items), "conditions": {}}
    all_metrics, sheet = {}, []
    for cond in conds:
        pipe = Pipeline(cond)
        info = pipe.versions(); run_cfg["conditions"][cond] = info
        if info["generator"].get("error"):
            sys.exit(f"Generator unavailable: {info['generator']['error']}. Start Ollama (ollama serve) and pull the model.")
        responses = {}
        with open(out_dir / f"outputs_{cond}.jsonl", "w", encoding="utf-8") as f:
            for n, it in enumerate(items, 1):
                r = pipe.answer(it["question"])
                r["item_id"] = it["id"]; r["item_type"] = it["type"]; responses[it["id"]] = r
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
                print(f"[{cond}] {n}/{len(items)} {it['id']} -> {r['outcome']:9s} {r['latency_ms']/1000:.1f}s")
        all_metrics[cond] = evaluate(items, responses)
        for it in items:
            r = responses[it["id"]]
            sheet.append({"cond": cond, "item_id": it["id"], "type": it["type"], "expected_behavior": it["expected_behavior"],
                          "question": it["question"], "gold_answer": it["gold_answer"],
                          "gold_chunks": "; ".join(",".join(g) for g in it.get("gold_chunk_ids", [])),
                          "system_reply": r["answer"], "system_status": r["status"],
                          "cited": ", ".join(c["chunk_id"] for c in r.get("citations", [])),
                          "retrieved_top5": ", ".join(h["chunk_id"] for h in r["retrieved"])})
    json.dump(run_cfg, open(out_dir / "run_config.json", "w"), indent=2)
    json.dump(all_metrics, open(out_dir / "metrics_auto.json", "w"), indent=2)
    # blind manual-scoring sheet
    rng = random.Random(run_id); rng.shuffle(sheet)
    with open(out_dir / "scoring_key.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f); w.writerow(["blind_id", "condition", "item_id"])
        for i, s in enumerate(sheet, 1):
            s["blind_id"] = f"R{i:03d}"; w.writerow([s["blind_id"], s["cond"], s["item_id"]])
    cols = ["blind_id", "item_id", "type", "expected_behavior", "question", "gold_answer", "gold_chunks", "system_reply",
            "system_status", "cited", "retrieved_top5", "correctness_0_1_2", "faithfulness_0_1", "citation_accuracy_0_1",
            "asserts_detail_Y_N", "notes"]
    with open(out_dir / "scoring_sheet.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore"); w.writeheader()
        for s in sheet: w.writerow(s)
    # summary
    keys = sorted({k for m in all_metrics.values() for k in m})
    lines = [f"# Run {run_id} ({a.split}, n={len(items)})", "", "| metric | " + " | ".join(conds) + " |", "|---|" + "---|" * len(conds)]
    for k in keys:
        lines.append(f"| {k} | " + " | ".join(json.dumps(all_metrics[c].get(k, "")) for c in conds) + " |")
    lines += ["", "| item | type | " + " | ".join(f"{c} outcome" for c in conds) + " |", "|---|---|" + "---|" * len(conds)]
    outs = {c: {json.loads(l)["item_id"]: json.loads(l) for l in open(out_dir / f"outputs_{c}.jsonl", encoding="utf-8")} for c in conds}
    for it in items:
        lines.append(f"| {it['id']} | {it['type']} | " + " | ".join(outs[c][it["id"]]["outcome"] for c in conds) + " |")
    (out_dir / "summary.md").write_text("\n".join(lines), encoding="utf-8")
    log_run("eval_run", {"eval_run_id": run_id, "split": a.split, "tag": a.tag, "conditions": conds,
                         "items_sha256": run_cfg["items_sha256"], "results_dir": f"results/eval/{run_id}",
                         "models": {c: run_cfg["conditions"][c]["generator"] for c in conds},
                         "prompts": {c: run_cfg["conditions"][c]["prompt_sha"] for c in conds}, "metrics": all_metrics})
    print("\n".join(lines[:len(keys) + 4]))
    print(f"\nSaved to results/eval/{run_id}")


if __name__ == "__main__":
    main()
