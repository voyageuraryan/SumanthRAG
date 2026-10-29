"""Data-quality and responsible-use profile of the processed corpus.
Usage:  python -m src.data_quality   ->  reports/data_quality.json
"""
import json, re, statistics
from collections import Counter
from .common import ROOT, read_jsonl, log_run

def shingles(s, n=5):
    w = re.findall(r"[a-z0-9]+", s.lower())
    return {" ".join(w[i:i + n]) for i in range(max(1, len(w) - n + 1))}

def main():
    C = read_jsonl("data/processed/chunks.jsonl")
    lens = [c["n_words"] for c in C]
    # exact + near duplicates (Jaccard over 5-word shingles)
    exact = Counter(c["content_hash"] for c in C)
    sh = [shingles(c["body"]) for c in C]
    near = []
    for i in range(len(C)):
        for j in range(i + 1, len(C)):
            if C[i]["section_part"] and C[j]["section_part"] and C[i]["heading_path"] == C[j]["heading_path"]:
                continue  # intended overlap between consecutive windows of one section
            inter = len(sh[i] & sh[j])
            if inter and inter / len(sh[i] | sh[j]) >= 0.5:
                near.append([C[i]["chunk_id"], C[j]["chunk_id"], round(inter / len(sh[i] | sh[j]), 2)])
    cross_doc = [p for p in near if p[0][:6] != p[1][:6]]
    text = "\n".join(c["body"] for c in C)
    emails = re.findall(r"[\w.+-]+@[\w-]+\.[a-z]{2,}", text)
    role = re.compile(r"^(hwc|disabilities|testingservices|internationaled|career\.services|dps|va|gradcollege|graduateadmissions|internationaladmissions|fa\.help|graduationabsentia|adviseme|tlc|registrar|business\.office|residence\.life|campuslife|campussupport|atu|service|immunization\.section)@")
    personal = sorted({e for e in emails if not role.match(e)})
    broken_urls = len(re.findall(r"https?://\S+/ \S+\.(?:php|html?)", text))
    cross_refs = len(re.findall(r"\(p\. ?\d+\)|see (?:the )?(?:section|policy)|refer to the", text, re.I))
    out = {
        "chunks": len(C), "words_total": sum(lens),
        "length_words": {"min": min(lens), "p25": statistics.quantiles(lens, n=4)[0], "median": statistics.median(lens),
                         "p75": statistics.quantiles(lens, n=4)[2], "max": max(lens)},
        "length_histogram": {b: sum(lo <= l < hi for l in lens) for b, (lo, hi) in
                             {"<40": (0, 40), "40-99": (40, 100), "100-199": (100, 200), "200-300": (200, 301)}.items()},
        "exact_duplicate_chunks": sum(v - 1 for v in exact.values() if v > 1),
        "near_duplicate_pairs_j>=0.5": len(near), "near_duplicate_cross_document": len(cross_doc),
        "near_duplicate_examples": near[:8],
        "chunks_by_top_section": Counter(f'{c["doc_id"]}: {c["heading_path"][0] if c["heading_path"] else "(none)"}' for c in C).most_common(),
        "pii": {"email_mentions": len(emails), "distinct_role_addresses": len({e for e in emails if role.match(e)}),
                "distinct_individual_staff_addresses": len(personal), "student_records": 0},
        "extraction_artifacts": {"urls_split_by_linebreak": broken_urls,
                                 "email_glued_to_next_word": len(re.findall(r"@atu\.edu[a-z]", text))},
        "cross_references": cross_refs,
        "undergraduate_mentions": len(re.findall(r"\bundergraduate\b", text, re.I)),
    }
    json.dump(out, open(ROOT / "reports/data_quality.json", "w"), indent=2)
    print(json.dumps(out, indent=1)); print("run_id:", log_run("data_quality", {k: v for k, v in out.items() if k != "chunks_by_top_section"}))

if __name__ == "__main__":
    main()
