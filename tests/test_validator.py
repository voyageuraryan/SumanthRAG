import json
import src.eval_validate as ev

def test_empty_sets_fail(monkeypatch):
    monkeypatch.setattr(ev, "load", lambda split: [])  # independent of the real question files
    assert ev.validate(quiet=True) is False

def test_wrong_size_fails(tmp_path, monkeypatch):
    errs = []
    item = {"id": "D01", "split": "dev", "type": "single", "question": "q?", "gold_answer": "a", "gold_chunk_ids": [["GC2627-0007"]],
            "answerable": True, "expected_behavior": "answer", "written_on": "2026-10-29"}
    ev.check_split("dev", [item], {"GC2627-0007"}, ev.planned_ids(), errs)
    assert any("expected exactly 10" in e for e in errs) and any("missing" in e for e in errs)

def test_type_rules():
    errs = []
    bad = {"id": "D07", "split": "dev", "type": "unanswerable", "question": "q?", "gold_answer": "a", "gold_chunk_ids": [["GC2627-0007"]],
           "answerable": True, "expected_behavior": "answer", "written_on": "2026-10-29"}
    ev.check_split("dev", [bad], {"GC2627-0007"}, ev.planned_ids(), errs)
    assert any("needs expected_behavior" in e for e in errs) and any("answerable=False" in e for e in errs)
