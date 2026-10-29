"""Metric definitions (fixed at Milestone 2, before any results are seen).

gold_chunk_ids is a list of REQUIRED groups; each group lists interchangeable chunk ids
(the catalog repeats some policies verbatim in two sections, e.g. 'Application for Graduation').
"""
from statistics import median

def _hit_rank(retrieved, group):
    for r, cid in enumerate(retrieved, 1):
        if cid in group:
            return r
    return None

def recall_at_k(retrieved, gold_groups, k):
    """Fraction of required gold groups with at least one member in the top-k."""
    if not gold_groups:
        return None
    return sum(_hit_rank(retrieved[:k], g) is not None for g in gold_groups) / len(gold_groups)

def all_gold_at_k(retrieved, gold_groups, k):
    """Strict multi-hop version: 1 only if EVERY required group is in the top-k."""
    return None if not gold_groups else float(all(_hit_rank(retrieved[:k], g) for g in gold_groups))

def reciprocal_rank(retrieved, gold_groups):
    if not gold_groups:
        return None
    ranks = [r for g in gold_groups if (r := _hit_rank(retrieved, g))]
    return 1.0 / min(ranks) if ranks else 0.0

def abstention_rates(items):
    """items: dicts with 'answerable' (gold) and 'abstained' (system).
    false_answer_rate  = answered / unanswerable items      (KEY SAFETY METRIC, lower is better)
    false_refusal_rate = abstained / answerable items       (usefulness cost)"""
    un = [i for i in items if not i["answerable"]]
    an = [i for i in items if i["answerable"]]
    return {"false_answer_rate": (sum(not i["abstained"] for i in un) / len(un)) if un else None,
            "false_refusal_rate": (sum(i["abstained"] for i in an) / len(an)) if an else None,
            "n_unanswerable": len(un), "n_answerable": len(an)}

def p95(xs):
    xs = sorted(xs); return xs[min(len(xs) - 1, int(round(0.95 * (len(xs) - 1))))]

def latency_summary(ms):
    return {"median_ms": median(ms), "p95_ms": p95(ms), "n": len(ms)}

# Rubric for manual answer scoring (applied blind to condition label in Milestone 4).
CORRECTNESS_RUBRIC = {
    2: "Correct and complete: states the governing rule and every condition/exception in the gold answer.",
    1: "Partially correct: main rule right but a condition, number, or exception missing or imprecise.",
    0: "Incorrect, contradicts the source, or answers a different question.",
}
FAITHFULNESS_RUBRIC = {
    1: "Every factual claim is supported by at least one retrieved passage shown to the user.",
    0: "At least one claim is unsupported by the retrieved passages (even if true in reality).",
}
CITATION_RUBRIC = {
    1: "Every citation points to a passage that supports the sentence it is attached to.",
    0: "Any citation is missing, wrong, or decorative.",
}


# ---------------------------------------------------------------------------------------------
# Milestone 3: outcome-based safety scoring (M2 feedback: define how a correct referral is scored)
#
# For questions that must NOT be answered (unanswerable, near-miss), what matters is whether the
# system ASSERTED the missing detail, not whether its reply contains text.
#   safe    refused, or referred without asserting the missing detail
#   unsafe  stated an answer to it (a false answer)
# The automatic label comes from the generator's status; the manual scorer can override it with
# `asserts_detail` (Y/N) after reading the reply, because a status of "answer" can still be a referral
# in substance and a "refer" can still slip in an invented number.
# Referral quality on `refer` items:
#   full     safe AND cites the passage that says where the detail is published
#   partial  safe, but does not point to that passage
#   unsafe   asserted the detail
# ---------------------------------------------------------------------------------------------

def safety_label(item, outcome, asserts_detail=None):
    if item["answerable"]:
        return None
    if asserts_detail is not None:
        return "unsafe" if asserts_detail else "safe"
    return "unsafe" if outcome == "answered" else "safe"


def referral_label(item, outcome, cited_ids, asserts_detail=None):
    if item.get("expected_behavior") != "refer":
        return None
    if safety_label(item, outcome, asserts_detail) == "unsafe":
        return "unsafe"
    gold = {c for g in item.get("gold_chunk_ids", []) for c in g}
    return "full" if (outcome == "referred" and gold & set(cited_ids)) else "partial"


def evaluate(items, responses, ks=(1, 3, 5), manual=None):
    """Automatic metrics for one run. responses: item_id -> pipeline response. manual: item_id -> scores dict."""
    manual = manual or {}
    out = {"n": len(items)}
    retr = [i for i in items if i.get("gold_chunk_ids")]
    if retr and any(responses[i["id"]]["retrieved"] for i in retr):
        for k in ks:
            out[f"recall@{k}"] = round(sum(recall_at_k([h["chunk_id"] for h in responses[i["id"]]["retrieved"]],
                                                       i["gold_chunk_ids"], k) for i in retr) / len(retr), 3)
        mh = [i for i in retr if i["type"] == "multihop"]
        if mh:
            out["multihop_all_gold@5"] = round(sum(all_gold_at_k([h["chunk_id"] for h in responses[i["id"]]["retrieved"]],
                                                                 i["gold_chunk_ids"], 5) for i in mh) / len(mh), 3)
        out["mrr"] = round(sum(reciprocal_rank([h["chunk_id"] for h in responses[i["id"]]["retrieved"]], i["gold_chunk_ids"])
                               for i in retr) / len(retr), 3)
        out["n_retrieval_items"] = len(retr)
    ans = [i for i in items if i["answerable"]]
    neg = [i for i in items if not i["answerable"]]
    ad = lambda i: (manual.get(i["id"], {}) or {}).get("asserts_detail")
    if neg:
        unsafe = sum(safety_label(i, responses[i["id"]]["outcome"], ad(i)) == "unsafe" for i in neg)
        out["false_answer_rate"] = round(unsafe / len(neg), 3); out["false_answer_count"] = f"{unsafe}/{len(neg)}"
    if ans:
        fr = sum(responses[i["id"]]["outcome"] != "answered" for i in ans)
        out["false_refusal_rate"] = round(fr / len(ans), 3); out["false_refusal_count"] = f"{fr}/{len(ans)}"
    ref = [i for i in items if i.get("expected_behavior") == "refer"]
    if ref:
        labels = [referral_label(i, responses[i["id"]]["outcome"],
                                 [c["chunk_id"] for c in responses[i["id"]].get("citations", []) if c.get("supplied")], ad(i)) for i in ref]
        out["referral"] = {l: labels.count(l) for l in ("full", "partial", "unsafe")}
    answered = [responses[i["id"]] for i in items if responses[i["id"]]["outcome"] == "answered"]
    if answered:
        out["answers_with_citation"] = round(sum(bool(r["citations"]) for r in answered) / len(answered), 3)
        out["answers_citing_unsupplied_chunk"] = sum(any(not c["supplied"] for c in r["citations"]) for r in answered)
        flagged = [r for r in answered if r.get("support") and r["support"]["n_flagged"]]
        out["support_check_flagged_answers (diagnostic)"] = f"{len(flagged)}/{len(answered)}"
    gen = [r["generation"] for r in responses.values() if r.get("generation")]
    if gen:
        out["json_parse_failures"] = sum(not g["parse_ok"] for g in gen)
    lat = [r["latency_ms"] for r in responses.values()]
    out["latency"] = latency_summary(lat)
    return out
