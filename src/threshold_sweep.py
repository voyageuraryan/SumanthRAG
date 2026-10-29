"""Gate-1 sensitivity: what WOULD a retrieval-score threshold do on this run? (exact simulation)

Because the M3 baseline runs with tau = 0, every question reached the generator. A threshold tau would
only have replaced some of those outcomes with "refused", so its effect can be computed exactly from the
saved outputs - no re-run, no tuning loop on the model.

With only 10 dev questions one chosen tau is not precise (M2 feedback). This reports the whole curve,
the tau a simple rule would pick, how that pick moves when any single question is left out, and a
bootstrap interval. Usage: python -m src.threshold_sweep results/eval/<run_id> [--condition A]
"""
import argparse, json, random
from pathlib import Path
from .common import ROOT, read_jsonl, log_run

def rates(items, resp, tau):
    neg = [i for i in items if not i["answerable"]]; pos = [i for i in items if i["answerable"]]
    out = lambda i: "refused" if (resp[i["id"]]["gate1"]["top_score_norm"] or 0) < tau else resp[i["id"]]["outcome"]
    far = sum(out(i) == "answered" for i in neg) / len(neg) if neg else None
    frr = sum(out(i) != "answered" for i in pos) / len(pos) if pos else None
    return far, frr

def pick(items, resp, grid, max_frr=0.2):
    """Rule fixed in M2: the largest tau whose false-refusal rate stays <= 20%."""
    ok = [t for t in grid if (rates(items, resp, t)[1] or 0) <= max_frr]
    return max(ok) if ok else 0.0

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("run_dir"); ap.add_argument("--condition", default="A")
    a = ap.parse_args(); d = ROOT / a.run_dir
    cfg = json.load(open(d / "run_config.json", encoding="utf-8")); items = read_jsonl(cfg["items_file"])
    resp = {json.loads(l)["item_id"]: json.loads(l) for l in open(d / f"outputs_{a.condition}.jsonl", encoding="utf-8")}
    grid = [round(x * 0.01, 2) for x in range(0, 81)]
    curve = [{"tau": t, "false_answer_rate": rates(items, resp, t)[0], "false_refusal_rate": rates(items, resp, t)[1]} for t in grid]
    chosen = pick(items, resp, grid)
    loo = [pick([j for j in items if j["id"] != i["id"]], resp, grid) for i in items]
    rng = random.Random(13); boots = []
    for _ in range(1000):
        s = [rng.choice(items) for _ in items]
        if any(i["answerable"] for i in s): boots.append(pick(s, resp, grid))
    boots.sort()
    res = {"condition": a.condition, "n_items": len(items), "rule": "largest tau with false-refusal <= 0.20",
           "chosen_tau": chosen, "rates_at_chosen": dict(zip(["false_answer_rate", "false_refusal_rate"], rates(items, resp, chosen))),
           "leave_one_out_tau": {"min": min(loo), "max": max(loo), "values": loo},
           "bootstrap_tau_90pct": [boots[int(0.05 * len(boots))], boots[int(0.95 * len(boots))]],
           "score_norm_by_item": {i["id"]: {"answerable": i["answerable"], "top_score_norm": resp[i["id"]]["gate1"]["top_score_norm"],
                                            "outcome_at_tau0": resp[i["id"]]["outcome"]} for i in items},
           "curve": curve}
    json.dump(res, open(d / f"threshold_sweep_{a.condition}.json", "w"), indent=1)
    try:
        import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
        fig, ax = plt.subplots(figsize=(6.4, 3.4))
        ax.plot(grid, [c["false_answer_rate"] for c in curve], label="false-answer rate (should-refuse items)", color="#B4442C")
        ax.plot(grid, [c["false_refusal_rate"] for c in curve], label="false-refusal rate (answerable items)", color="#2F5D8A")
        ax.axvspan(res["bootstrap_tau_90pct"][0], res["bootstrap_tau_90pct"][1], color="#999", alpha=0.18, label="bootstrap 90% range of chosen tau")
        ax.axvline(chosen, ls="--", c="#333", lw=1); ax.set_xlabel("gate-1 threshold tau (normalized retrieval score)"); ax.set_ylabel("rate")
        ax.set_ylim(-0.03, 1.03); ax.legend(frameon=False, fontsize=8); ax.spines[["top", "right"]].set_visible(False)
        ax.set_title(f"Condition {a.condition}: gate-1 sensitivity (n={len(items)})", fontsize=10, loc="left")
        plt.tight_layout(); plt.savefig(d / f"threshold_sweep_{a.condition}.png", dpi=200)
    except ImportError:
        pass
    print(json.dumps({k: v for k, v in res.items() if k not in ("curve", "score_norm_by_item")}, indent=1))
    print("run_id:", log_run("threshold_sweep", {"eval_run_id": cfg["run_id"], **{k: v for k, v in res.items() if k != "curve"}}))

if __name__ == "__main__":
    main()
