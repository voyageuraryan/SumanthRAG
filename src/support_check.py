"""Gate 3 candidate: does each answer sentence look supported by the passages it cites?

STATUS: DIAGNOSTIC ONLY (M2 feedback). Lexical overlap is not proof of support: a paraphrase can share
few words with its source, and a sentence with a changed number or a flipped negation can share almost
all of them. The three signals below are logged for every answer but do NOT refuse anything until
`python -m src.checks.support_check_eval` shows they separate supported from unsupported sentences.

Signals per sentence (cited passages = the chunks named in that sentence's [chunk-id] markers):
  overlap   share of the sentence's content words found in the cited passages     (flag if < 0.5)
  numbers   every number in the sentence (digits or number words) occurs in them  (flag if not)
  negation  negation polarity matches the most similar passage sentence            (flag if not)
  uncited   sentence has no citation, or cites a chunk that was not supplied        (flag)
"""
import re

STOP = set("""a an and are as at be been but by can could do does for from had has have he her his how i if in
into is it its may me might more most must my no nor not of on or our shall she should so such than that the
their them then there these they this those to under up upon was we were what when where which while who whom
why will with would you your also any each other only own same some very just about over per via""".split())
NEG = {"not", "no", "never", "cannot", "none", "neither", "nor", "without", "except", "unless"}
NUMWORDS = {"zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8,
            "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15,
            "sixteen": 16, "seventeen": 17, "eighteen": 18, "nineteen": 19, "twenty": 20, "thirty": 30,
            "forty": 40, "fifty": 50, "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90, "hundred": 100}
CITE = re.compile(r"\[([A-Z]{2}\d{4}-\d{4})\]")
SENT = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9\"(])")


def words(t):
    return re.findall(r"[a-z0-9']+", t.lower().replace("n't", " not").replace("cannot", "can not"))


def content(t):
    return {w for w in words(t) if w not in STOP and w not in NEG and len(w) > 2 and not w.isdigit()}


def numbers(t):
    out = set()
    for w in re.findall(r"\d+(?:\.\d+)?|[a-z]+", t.lower().replace(",", "")):
        if w in NUMWORDS: out.add(float(NUMWORDS[w]))
        elif re.fullmatch(r"\d+(?:\.\d+)?", w): out.add(float(w))
    return out


def negated(t):
    return any(w in NEG for w in words(t))


def split_sentences(text):
    return [s.strip() for s in SENT.split(text.strip()) if s.strip()]


def check_sentence(sentence, cited_texts, min_overlap=0.5):
    clean = CITE.sub("", sentence).strip()
    src = " ".join(cited_texts)
    cw = content(clean)
    overlap = (len(cw & content(src)) / len(cw)) if cw else 1.0
    missing_nums = sorted(numbers(clean) - numbers(src))
    # polarity against the single most similar passage sentence
    best, best_sim = "", -1.0
    for ps in split_sentences(src) or [src]:
        pc = content(ps); sim = len(cw & pc) / (len(cw | pc) or 1)
        if sim > best_sim: best, best_sim = ps, sim
    neg_mismatch = bool(best) and negated(clean) != negated(best)
    flags = []
    if overlap < min_overlap: flags.append("low_overlap")
    if missing_nums: flags.append("number_not_in_source")
    if neg_mismatch: flags.append("negation_mismatch")
    return {"overlap": round(overlap, 3), "missing_numbers": missing_nums, "negation_mismatch": neg_mismatch,
            "flags": flags}


def check_answer(answer, passages_by_id, min_overlap=0.5):
    """Returns per-sentence results + an answer-level summary. passages_by_id: chunk_id -> body text."""
    rows = []
    for s in split_sentences(answer):
        cites = CITE.findall(s)
        valid = [c for c in cites if c in passages_by_id]
        if not cites:
            rows.append({"sentence": s, "cites": [], "flags": ["uncited"]}); continue
        r = check_sentence(s, [passages_by_id[c] for c in valid], min_overlap) if valid else {"flags": []}
        if len(valid) < len(cites): r["flags"] = r.get("flags", []) + ["cites_unsupplied_chunk"]
        rows.append({"sentence": s, "cites": cites, **r})
    flagged = [r for r in rows if r["flags"]]
    return {"sentences": rows, "n_sentences": len(rows), "n_flagged": len(flagged),
            "flag_counts": {f: sum(f in r["flags"] for r in rows) for f in
                            ("low_overlap", "number_not_in_source", "negation_mismatch", "uncited", "cites_unsupplied_chunk")}}
