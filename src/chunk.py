"""Step 2: heading-aware chunking.

Rules (configs/pipeline.json -> chunking):
  * A chunk never crosses a level-1/level-2 section boundary.
  * Sections shorter than min_words are merged forward into the next section under the same parent
    (fixes bold list items that the PDF marks up like headings).
  * Sections longer than max_words are split on sentence boundaries with `overlap_sentences` overlap.
  * The heading path is prepended so a severed sub-clause keeps its parent context.
Usage:  python -m src.chunk
Output: data/processed/chunks.jsonl
"""
import re, json, statistics
from .common import load_json, read_jsonl, write_jsonl, sha256_text, log_run, config_hash, ROOT

SENT = re.compile(r"(?<=[.;:!?])\s+(?=[A-Z0-9(\"-])|\n(?=- )")

def wc(s): return len(s.split())

def sections(blocks):
    """Group consecutive blocks that share an identical heading path."""
    out = []
    for b in blocks:
        key = (b["doc_id"], tuple(b["heading_path"]))
        if out and out[-1]["key"] == key:
            out[-1]["text"] += "\n" + b["text"]; out[-1]["page_end"] = b["page_end"]
        else:
            out.append({"key": key, "doc_id": b["doc_id"], "doc_title": b["doc_title"],
                        "heading_path": b["heading_path"], "page_start": b["page_start"],
                        "page_end": b["page_end"], "text": b["text"]})
    return out

def top2(sec):
    hp = [h for h in sec["heading_path"] if h != "GRADUATE"]
    return (sec["doc_id"], tuple(hp[:2]))

def merge_small(secs, min_words):
    merged, carry = [], None
    for s in secs:
        if carry and top2(carry) == top2(s):
            # keep the small section's own heading inline so its meaning is not lost
            s = dict(s, text=f'{carry["heading_path"][-1] if carry["heading_path"] else ""}: {carry["text"]}\n{s["text"]}',
                     page_start=carry["page_start"])
            carry = None
        elif carry:
            merged.append(carry); carry = None
        if wc(s["text"]) < min_words:
            carry = s
        else:
            merged.append(s)
    if carry: merged.append(carry)
    return merged

def split(text, max_words, overlap):
    sents = [x.strip() for x in SENT.split(text) if x.strip()]
    windows, cur = [], []
    for s in sents:
        if cur and wc(" ".join(cur + [s])) > max_words:
            windows.append(" ".join(cur))
            cur = cur[-overlap:] if overlap else []
        cur.append(s)
    if cur: windows.append(" ".join(cur))
    return windows

def main():
    cfg = load_json("configs/pipeline.json"); c = cfg["chunking"]
    blocks = read_jsonl("data/processed/blocks.jsonl")
    secs = merge_small(sections(blocks), c["min_words"])
    chunks = []
    for s in secs:
        hp = [h for h in s["heading_path"] if h != "GRADUATE"]
        prefix = f'{s["doc_title"]} > ' + " > ".join(hp)
        for j, body in enumerate(split(s["text"], c["max_words"], c["overlap_sentences"])):
            text = f"{prefix}\n{body}" if c["prepend_heading_path"] else body
            chunks.append({"chunk_id": f'{s["doc_id"]}-{len(chunks):04d}', "doc_id": s["doc_id"],
                           "doc_title": s["doc_title"], "heading_path": hp, "section_part": j,
                           "page_start": s["page_start"], "page_end": s["page_end"],
                           "n_words": wc(body), "text": text, "body": body,
                           "content_hash": sha256_text(body)[:16]})
    write_jsonl("data/processed/chunks.jsonl", chunks)
    lens = [x["n_words"] for x in chunks]
    stats = {"sections_after_merge": len(secs), "chunks": len(chunks),
             "by_doc": {d: sum(1 for x in chunks if x["doc_id"] == d) for d in sorted({x["doc_id"] for x in chunks})},
             "words_min": min(lens), "words_median": statistics.median(lens), "words_mean": round(statistics.mean(lens), 1),
             "words_max": max(lens), "under_min_words": sum(l < c["min_words"] for l in lens),
             "over_max_words": sum(l > c["max_words"] for l in lens)}
    json.dump(stats, open(ROOT / "reports/chunk_stats.json", "w"), indent=2)
    rid = log_run("chunk", {"config_hash": config_hash(cfg), "chunking": c, "stats": stats})
    print(json.dumps(stats, indent=2)); print("run_id:", rid)

if __name__ == "__main__":
    main()
