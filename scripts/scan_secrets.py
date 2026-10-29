"""Pre-commit / pre-submission scan for anything that looks like a credential."""
import re, sys, pathlib
PATTERNS = {"private key": r"-----BEGIN [A-Z ]*PRIVATE KEY-----", "openai-style key": r"\bsk-[A-Za-z0-9]{20,}",
            "hf token": r"\bhf_[A-Za-z0-9]{30,}", "aws key": r"\bAKIA[0-9A-Z]{16}\b",
            "generic secret": r"(?i)(api[_-]?key|secret|token|password)\s*[:=]\s*['\"][^'\"]{8,}['\"]"}
root = pathlib.Path(__file__).resolve().parent.parent
bad = []
for p in root.rglob("*"):
    if p.is_file() and p.suffix in {".py", ".json", ".md", ".txt", ".sh", ".yaml", ".yml", ".env", ".cfg", ".toml"} and not {"data", ".venv", ".git", "__pycache__"} & set(p.parts):
        t = p.read_text(errors="ignore")
        bad += [f"{p.relative_to(root)}: {name}" for name, rx in PATTERNS.items() if re.search(rx, t)]
print("secret scan:", "CLEAN" if not bad else bad); sys.exit(1 if bad else 0)
