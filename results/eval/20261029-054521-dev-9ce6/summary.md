# Run 20261029-054521-dev-9ce6 (dev, n=10)

| metric | A | 0 |
|---|---|---|
| answers_citing_unsupplied_chunk | 0 | 0 |
| answers_with_citation | 1.0 | 0.0 |
| false_answer_count | "0/4" | "3/4" |
| false_answer_rate | 0.0 | 0.75 |
| false_refusal_count | "1/6" | "0/6" |
| false_refusal_rate | 0.167 | 0.0 |
| json_parse_failures | 0 | 0 |
| latency | {"median_ms": 107608.0, "p95_ms": 178361, "n": 10} | {"median_ms": 22629.0, "p95_ms": 29683, "n": 10} |
| mrr | 0.681 | "" |
| multihop_all_gold@5 | 0.5 | "" |
| n | 10 | 10 |
| n_retrieval_items | 6 | "" |
| recall@1 | 0.417 | "" |
| recall@3 | 0.75 | "" |
| recall@5 | 0.917 | "" |
| support_check_flagged_answers (diagnostic) | "3/5" | "0/9" |

| item | type | A outcome | 0 outcome |
|---|---|---|---|
| D01 | single | answered | answered |
| D02 | single | refused | answered |
| D03 | single | answered | answered |
| D04 | single | answered | answered |
| D05 | multihop | answered | answered |
| D06 | multihop | answered | answered |
| D07 | unanswerable | referred | answered |
| D08 | unanswerable | referred | answered |
| D09 | nearmiss | refused | answered |
| D10 | nearmiss | refused | refused |