"""Quantify why NFKC normalization is required: which words are unmatchable by BM25 without it.
Usage: python -m src.checks.normalization_effect
"""
import re, json
from collections import Counter
import pymupdf
from ..common import ROOT, load_json, log_run
LIG = re.compile("[ﬀ-ﬄ]")

def main():
    m = load_json("configs/corpus_manifest.json")
    affected, total = Counter(), 0
    for d in m["documents"]:
        pdf = pymupdf.open(ROOT / d["file"]); a, b = d["include_pages"]
        for p in range(a - 1, b):
            words = re.findall(r"\S+", pdf[p].get_text().lower())
            total += len(words)
            affected.update(re.sub(r"[^\wﬀ-ﬄ]", "", w) for w in words if LIG.search(w))
    n = sum(affected.values())
    out = {"words_scanned": total, "words_with_ligatures": n, "pct": round(100 * n / total, 2),
           "distinct_affected_words": len(affected),
           "top_affected": [[w.encode("unicode_escape").decode(), c] for w, c in affected.most_common(12)]}
    print(json.dumps(out, indent=1)); print("run_id:", log_run("check_normalization", out))

if __name__ == "__main__":
    main()
