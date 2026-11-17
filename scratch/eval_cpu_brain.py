import json, time, sys, subprocess
import requests

URL = "http://127.0.0.1:11434"
try:
    tags = requests.get(URL + "/api/tags", timeout=5).json()
    print("ollama models:", [m["name"] for m in tags.get("models", [])])
except Exception as exc:
    print("ollama not reachable:", exc)
    sys.exit(0)

prompt = "You are a teacher. In three short sentences explain what a timeline is in a video editor and why an editor trims a clip."
for label, opts in (("CPU only (num_gpu=0)", {"num_gpu": 0}), ("default (GPU offload as Ollama decides)", {})):
    body = {"model": "qwen2.5:7b", "prompt": prompt, "stream": False, "options": {"temperature": 0.0, "num_predict": 80, **opts}}
    t0 = time.time()
    try:
        r = requests.post(URL + "/api/generate", json=body, timeout=300).json()
    except Exception as exc:
        print(label, "failed", exc)
        continue
    dt = time.time() - t0
    ec, ed = r.get("eval_count", 0), r.get("eval_duration", 1)
    pc, pd = r.get("prompt_eval_count", 0), r.get("prompt_eval_duration", 1)
    print(f"{label:42s} wall {dt:5.1f}s  gen {ec} tok at {ec / (ed / 1e9):5.1f} tok/s   prompt {pc} tok at {pc / (pd / 1e9):6.1f} tok/s   load {r.get('load_duration', 0) / 1e9:4.1f}s")
    print("   ->", (r.get("response") or "")[:140].replace("\n", " "))

print("\nGPU/VRAM now:")
try:
    print(subprocess.run(["nvidia-smi", "--query-gpu=name,memory.used,memory.total", "--format=csv,noheader"], capture_output=True, text=True, timeout=10).stdout.strip())
except Exception as exc:
    print("nvidia-smi:", exc)
print("\nPython packages relevant to OmniParser-class detectors:")
for pkg in ("torch", "ultralytics", "onnxruntime", "onnxruntime-gpu", "transformers", "opencv-python", "networkx", "PyQt6"):
    out = subprocess.run([sys.executable, "-m", "pip", "show", pkg], capture_output=True, text=True).stdout
    ver = [l.split(": ", 1)[1] for l in out.splitlines() if l.startswith("Version")]
    print(f"  {pkg:18s} {ver[0] if ver else 'not installed'}")
