from src.support_check import check_sentence, check_answer

SRC = "No graduate student may repeat a course for graduate credit except with the written permission of the advisor. The maximum is twelve (12) hours."

def test_verbatim_passes():
    assert check_sentence("The maximum is twelve (12) hours.", [SRC])["flags"] == []

def test_changed_number_flagged():
    assert "number_not_in_source" in check_sentence("The maximum is 15 hours.", [SRC])["flags"]

def test_negation_flip_flagged():
    assert "negation_mismatch" in check_sentence("A graduate student may repeat a course for graduate credit with the written permission of the advisor.", [SRC])["flags"]

def test_uncited_sentence_flagged():
    r = check_answer("You can repeat it. Ask your advisor [GC2627-0138].", {"GC2627-0138": SRC})
    assert r["flag_counts"]["uncited"] == 1
