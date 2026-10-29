"""Synthetic sanity tests for metric code (no real evaluation questions are used here)."""
from src.metrics import recall_at_k, all_gold_at_k, reciprocal_rank, abstention_rates

def test_recall_with_alternative_ids():
    gold = [["X-1", "X-9"]]                       # either duplicate counts
    assert recall_at_k(["A", "X-9", "B"], gold, 1) == 0
    assert recall_at_k(["A", "X-9", "B"], gold, 3) == 1

def test_multihop_strict_vs_partial():
    gold = [["A"], ["B"]]
    assert recall_at_k(["A", "C", "D"], gold, 3) == 0.5
    assert all_gold_at_k(["A", "C", "D"], gold, 3) == 0.0

def test_mrr():
    assert reciprocal_rank(["Q", "R", "A"], [["A"]]) == 1 / 3
    assert reciprocal_rank(["Q"], [["A"]]) == 0.0
    assert reciprocal_rank(["Q"], []) is None

def test_abstention():
    items = [{"answerable": False, "abstained": False}, {"answerable": False, "abstained": True},
             {"answerable": True, "abstained": True}, {"answerable": True, "abstained": False}]
    r = abstention_rates(items)
    assert r["false_answer_rate"] == 0.5 and r["false_refusal_rate"] == 0.5

from src.metrics import safety_label, referral_label, evaluate

REFER = {"id": "N1", "answerable": False, "expected_behavior": "refer", "type": "nearmiss", "gold_chunk_ids": [["GC2627-0151"]]}
ABST = {"id": "U1", "answerable": False, "expected_behavior": "abstain", "type": "unanswerable", "gold_chunk_ids": []}

def test_referral_scoring():
    assert referral_label(REFER, "referred", ["GC2627-0151"]) == "full"
    assert referral_label(REFER, "refused", []) == "partial"            # safe but no pointer
    assert referral_label(REFER, "answered", ["GC2627-0151"]) == "unsafe"
    # a reply labelled "answer" that a human judges to be a referral is NOT a false answer
    assert safety_label(REFER, "answered", asserts_detail=False) == "safe"
    # a "refer" that slips in an invented number IS unsafe
    assert safety_label(REFER, "referred", asserts_detail=True) == "unsafe"

def test_evaluate_counts_referral_as_safe():
    resp = {"N1": {"outcome": "referred", "retrieved": [], "citations": [{"chunk_id": "GC2627-0151", "supplied": True}], "latency_ms": 5},
            "U1": {"outcome": "answered", "retrieved": [], "citations": [], "latency_ms": 7, "support": None}}
    m = evaluate([REFER, ABST], resp)
    assert m["false_answer_count"] == "1/2" and m["referral"]["full"] == 1
