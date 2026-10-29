"""Step 1: verify the frozen corpus and parse PDFs into heading-tagged text blocks.

Usage:  python -m src.ingest
Output: data/processed/blocks.jsonl, reports/ingest_stats.json
"""
import json, re, sys
from collections import Counter
import pymupdf
from .common import ROOT, load_json, sha256_file, normalize, write_jsonl, log_run, config_hash

RE_PAGE_NUM = re.compile(r"^\d{1,3}$")
RE_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")
RE_PHONE = re.compile(r"\b\d{3}[-.\s]\d{3}[-.\s]\d{4}\b")
RE_URL = re.compile(r"https?://\S+")
LIGATURES = "ﬀﬁﬂﬃﬄ"


def heading_level(spans, doc):
    """Return a heading level if every visible span matches a heading font/size, else None."""
    vis = [s for s in spans if s["text"].strip()]
    if not vis:
        return None
    levels = doc["heading_font_levels"]
    must = re.compile(doc["heading_font_must_contain"])
    sizes = {str(round(s["size"])) for s in vis}
    if len(sizes) != 1:
        return None
    size = sizes.pop()
    if size not in levels or not all(must.search(s["font"]) for s in vis):
        return None
    text = "".join(s["text"] for s in vis).strip()
    if len(text) > 120 or text.endswith((".", ",", ";")) and len(text) > 60:
        return None
    return levels[size]


def parse_document(doc, stats):
    pdf = pymupdf.open(ROOT / doc["file"])
    first, last = doc["include_pages"]
    stack = {}            # level -> heading text
    blocks, buf, buf_pages = [], [], []
    row = []              # pending left-column lines of a two-column calendar table row
    table_secs = set(doc.get("table_sections", []))

    def path():
        return [stack[k] for k in sorted(stack)]

    def flush():
        if buf:
            text = " ".join(buf)
            text = re.sub(r"\s+-\s+(?=[a-z])", "-", text)   # keep real hyphens, drop line-break spacing
            text = re.sub(r"\s*•\s*", "\n- ", text).strip()
            blocks.append({"doc_id": doc["doc_id"], "doc_title": doc["title"],
                           "heading_path": path(), "page_start": buf_pages[0],
                           "page_end": buf_pages[-1], "text": text})
            buf.clear(); buf_pages.clear()

    for pno in range(first - 1, last):
        page = pdf[pno]
        raw = page.get_text()
        stats["ligatures_raw"] += sum(raw.count(c) for c in LIGATURES)
        stats["zero_width_raw"] += raw.count("​")
        if not raw.strip():
            stats["empty_pages"].append(f'{doc["doc_id"]}:p{pno+1}'); continue
        first_line_seen = False
        for b in page.get_text("dict")["blocks"]:
            for line in b.get("lines", []):
                spans = line["spans"]
                text = normalize("".join(s["text"] for s in spans))
                if not text:
                    continue
                y = line["bbox"][1]
                # Running header (catalog) and page-number lines (handbook)
                if (doc["doc_id"] == "GC2627" and y < 45) or (not first_line_seen and RE_PAGE_NUM.match(text)):
                    stats["header_footer_lines_removed"] += 1
                    first_line_seen = True
                    continue
                first_line_seen = True
                lvl = heading_level(spans, doc)
                if lvl is None and table_secs and (set(stack.values()) & table_secs):
                    # Rebuild "Event | Date" rows: the date sits in a right column on the
                    # same baseline as the FIRST line of a (possibly wrapped) event label.
                    x0 = line["bbox"][0]
                    if x0 < 150:
                        row.append((text, y)); buf_pages.append(pno + 1); continue
                    if row and abs(y - row[0][1]) < 2:
                        label = " ".join(t for t, _ in row)
                        row.clear()
                        if label != "Event":
                            buf.append(f"• {label}: {text}"); buf_pages.append(pno + 1)
                            stats["table_rows_rebuilt"] += 1
                        continue
                if lvl is not None:
                    if row:
                        buf.extend(t for t, _ in row); row.clear()
                    flush()
                    for k in [k for k in stack if k >= lvl]:
                        del stack[k]
                    stack[lvl] = text
                    stats["headings_by_level"][f'{doc["doc_id"]}:L{lvl}'] += 1
                    continue
                buf.append(text); buf_pages.append(pno + 1)
        stats["pages_processed"] += 1
    flush()

    excluded = set(doc["exclude_sections"])
    kept = [bl for bl in blocks if not (set(bl["heading_path"][:2]) & excluded)]
    stats["blocks_excluded_by_section"][doc["doc_id"]] = len(blocks) - len(kept)
    return kept


def main():
    manifest = load_json("configs/corpus_manifest.json")
    cfg = load_json("configs/pipeline.json")
    # 1. Verify the frozen snapshot before doing anything else.
    for doc in manifest["documents"]:
        actual = sha256_file(ROOT / doc["file"])
        if actual != doc["sha256"]:
            sys.exit(f'HASH MISMATCH for {doc["doc_id"]}: corpus is not the frozen snapshot ({actual})')
    print("corpus hash check: OK")

    stats = {"pages_processed": 0, "empty_pages": [], "ligatures_raw": 0, "zero_width_raw": 0,
             "header_footer_lines_removed": 0, "table_rows_rebuilt": 0, "headings_by_level": Counter(),
             "blocks_excluded_by_section": {}}
    all_blocks = []
    for doc in manifest["documents"]:
        all_blocks += parse_document(doc, stats)
    for i, bl in enumerate(all_blocks):
        bl["block_id"] = f"B{i:05d}"
    joined = "\n".join(b["text"] for b in all_blocks)
    stats.update({
        "blocks": len(all_blocks),
        "words": len(joined.split()),
        "ligatures_after_normalization": sum(joined.count(c) for c in LIGATURES),
        "pii_scan": {"emails": len(RE_EMAIL.findall(joined)), "phone_numbers": len(RE_PHONE.findall(joined)),
                     "urls": len(RE_URL.findall(joined))},
        "headings_by_level": dict(stats["headings_by_level"]),
    })
    write_jsonl("data/processed/blocks.jsonl", all_blocks)
    with open(ROOT / "reports/ingest_stats.json", "w") as f:
        json.dump(stats, f, indent=2)
    run_id = log_run("ingest", {"corpus_version": manifest["corpus_version"],
                                "config_hash": config_hash(cfg), "stats": stats})
    print(json.dumps(stats, indent=2)); print("run_id:", run_id)


if __name__ == "__main__":
    main()
