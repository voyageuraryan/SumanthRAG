"""Download the two source PDFs into data/raw/ and verify them against the frozen SHA-256 in the manifest.

The raw PDFs are NOT redistributed with this repository (they are ATU's documents; see README, "Data").
Anyone can rebuild the identical corpus with:   python scripts/fetch_corpus.py
If ATU has replaced a file since 2026-10-04 the hash check fails and the script says so: the project's
results refer only to the frozen snapshot.
"""
import hashlib, json, ssl, subprocess, sys, urllib.error, urllib.request
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
m = json.load(open(ROOT / "configs/corpus_manifest.json", encoding="utf-8"))
ok = True
for d in m["documents"]:
    dest = ROOT / d["file"]; dest.parent.mkdir(parents=True, exist_ok=True)
    if not dest.exists():
        print("downloading", d["source_url"])
        req = urllib.request.Request(d["source_url"], headers={"User-Agent": "Mozilla/5.0 (PolicyRAG coursework)"})
        try:
            try:
                dest.write_bytes(urllib.request.urlopen(req, timeout=120).read())
            except urllib.error.URLError as e:
                if "CERTIFICATE_VERIFY_FAILED" not in str(e): raise
                # catalog.atu.edu serves an incomplete certificate chain and uv's Python has no system trust store.
                # Retry with the OS curl (which fetches the intermediate certificate), then without TLS verification.
                # Integrity does not depend on TLS here: the SHA-256 check below rejects any file that is not the frozen one.
                print("  certificate chain not verifiable by Python; retrying with system curl")
                if subprocess.run(["curl", "-fsSL", "-A", req.get_header("User-agent"), "-o", str(dest), d["source_url"]]).returncode != 0:
                    dest.unlink(missing_ok=True)
                    ctx = ssl._create_unverified_context()
                    dest.write_bytes(urllib.request.urlopen(req, timeout=120, context=ctx).read())
        except Exception as e:
            print(f"  failed ({e}). Download it in a browser and save it as {dest}"); ok = False; continue
        if not dest.exists() or dest.read_bytes()[:5] != b"%PDF-":
            # e.g. the host answered with a bot-protection challenge (HTTP 202, empty body) instead of the PDF
            dest.unlink(missing_ok=True)
            print(f"  the server did not return a PDF (bot protection?). Open {d['source_url']} in a browser, "
                  f"save the file as {dest}, then re-run."); ok = False; continue
    h =hashlib.sha256(dest.read_bytes()).hexdigest()
    match = h == d["sha256"]; ok &= match
    print(f'{d["doc_id"]}: {"OK - matches frozen snapshot" if match else "HASH MISMATCH - not the frozen version (" + h[:12] + ")"}')
sys.exit(0 if ok else 1)
