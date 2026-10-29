"""Record the hardware and measured generator speed (run on the demo machine; Ollama must be running).
Writes reports/hardware.json and prints it."""
import json, os, platform, subprocess, time, urllib.request
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
model = os.environ.get("POLICYRAG_MODEL", "llama3.1:8b")
host = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434")
info = {"os": platform.platform(), "python": platform.python_version(), "cpu": platform.processor(), "logical_cores": os.cpu_count()}
try:
    if platform.system() == "Windows":
        out = subprocess.check_output(["powershell", "-NoProfile", "-Command",
              "(Get-CimInstance Win32_ComputerSystem).TotalPhysicalMemory"]).decode().strip()
        info["ram_gb"] = round(int(out) / 2**30, 1)
    else:
        info["ram_gb"] = round(os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES") / 2**30, 1)
except Exception as e:
    info["ram_gb"] = f"unknown ({e})"
try:
    info["gpu"] = subprocess.check_output(["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader"]).decode().strip()
except Exception:
    info["gpu"] = "no NVIDIA GPU detected"
body = json.dumps({"model": model, "prompt": "Explain what a graduate catalog is in about 100 words.", "stream": False,
                   "options": {"temperature": 0, "seed": 13}}).encode()
try:
    t = time.time()
    r = json.load(urllib.request.urlopen(urllib.request.Request(host + "/api/generate", body, {"Content-Type": "application/json"}), timeout=900))
    info.update({"model": model, "eval_tokens": r["eval_count"], "tokens_per_sec": round(r["eval_count"] / (r["eval_duration"] / 1e9), 1),
                 "load_s": round(r.get("load_duration", 0) / 1e9, 1), "wall_s": round(time.time() - t, 1)})
except Exception as e:
    info["ollama"] = f"not reachable: {e}"
(ROOT / "reports").mkdir(exist_ok=True)
json.dump(info, open(ROOT / "reports/hardware.json", "w"), indent=2)
print(json.dumps(info, indent=2))
