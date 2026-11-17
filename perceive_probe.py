"""
perceive_probe.py -- decisive test of the Part-1 premise: does the :8081 Qwen3-VL eye
actually READ the current surface (e.g. "Paint is on Settings, not the canvas") and how
long does one perception call take on this 6 GB GPU? This gates the whole agent-loop design:
if the eye sees the wrong surface, perception-first is worth it; the latency tells us how
often we can afford to call it.
"""
import base64
import io
import json
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path("All codes").resolve()))
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass
from core_organs import headless_input as hin

END = "http://127.0.0.1:8081/v1/chat/completions"
HEALTH = "http://127.0.0.1:8081/health"
PROMPT = (
    "You are looking at a screenshot of a Windows desktop application that an automation agent "
    "is about to drive. Answer in STRICT JSON, nothing else: "
    '{"surface": "<one of: MAIN_CANVAS | SETTINGS | DIALOG | START_SCREEN | MENU | OTHER>", '
    '"what": "<one line: what this screen actually is>", '
    '"ready_for_main_work": true|false, '
    '"doors": ["<label of any button that closes/back-outs of this page, e.g. Back arrow, X, OK>"], '
    '"visible_controls": ["<label of every clickable thing you can read>"]}'
)


def find_win(sub):
    for h, t in hin.top_level_titles(visible_only=False):
        if sub.lower() in (t or "").lower():
            return h, t
    return None, None


def ensure(app, exe):
    h, t = find_win(app)
    if h:
        return h, t
    subprocess.Popen([exe])
    for _ in range(20):
        time.sleep(0.6)
        h, t = find_win(app)
        if h:
            return h, t
    return None, None


def perceive(img):
    w, h = img.size
    scale = min(1.0, 1024 / max(w, h))
    send = img.resize((int(w * scale), int(h * scale))) if scale < 1.0 else img
    buf = io.BytesIO()
    send.convert("RGB").save(buf, format="JPEG", quality=88)
    b64 = base64.b64encode(buf.getvalue()).decode("ascii")
    payload = {"model": "qwen3-vl", "temperature": 0.0, "max_tokens": 700,
               "messages": [{"role": "user", "content": [
                   {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64," + b64}},
                   {"type": "text", "text": PROMPT}]}]}
    t0 = time.time()
    req = urllib.request.Request(END, data=json.dumps(payload).encode("utf-8"),
                                 headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=240) as resp:
        body = json.loads(resp.read().decode("utf-8"))
    return body["choices"][0]["message"]["content"], round(time.time() - t0, 1), img.size


def main():
    try:
        urllib.request.urlopen(HEALTH, timeout=3)
        print("[eye] :8081 health OK")
    except Exception as e:
        print("[eye] :8081 NOT reachable:", e)
        return

    h, t = ensure("Paint", "mspaint.exe")
    print("[paint] hwnd", h, repr(t))
    if not h:
        print("could not open Paint"); return
    img, note, rung = hin.capture_window_robust(h)
    if img is None:
        print("[capture] failed:", note); return
    img.save(str(Path("scratch") / "paint_perceive.png"))
    content, secs, size = perceive(img)
    print(f"[perceive] {size} in {secs}s via {rung}")
    print(content[:1200])


if __name__ == "__main__":
    main()
