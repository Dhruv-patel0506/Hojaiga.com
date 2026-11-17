"""Does the precision eye (Qwen3-VL-8B on llama.cpp :8081) actually READ a Blender start-up screen? Asks it the question the executor's eye asks: what is on this screen, and what closes it."""
import base64
import io
import json
import sys
import time

sys.path.insert(0, r"d:\new_automation\All codes")
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from PIL import Image
import urllib.request

END = "http://127.0.0.1:8081/v1/chat/completions"
PROMPT = ("You are looking at a screenshot of a Windows desktop application that the automation is about to drive. "
          "Answer in JSON: {\"screen\": \"<one line: what this screen IS>\", \"blocking\": true|false, "
          "\"blocker\": \"<what is standing in the way of using the application, or empty>\", "
          "\"doors\": [\"<label of a button that closes/back out of it, e.g. Skip / Got it / Don't show again / OK / X>\"], "
          "\"visible_controls\": [\"<label of every clickable thing you can read>\"]}. "
          "Only what is literally visible. No prose outside the JSON.")

for path in sys.argv[1:] or [r"d:\new_automation\scratch\blender_cap_now.png"]:
    img = Image.open(path)
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
    try:
        req = urllib.request.Request(END, data=json.dumps(payload).encode("utf-8"), headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req, timeout=180) as resp:
            body = json.loads(resp.read().decode("utf-8"))
        content = body["choices"][0]["message"]["content"]
        print(f"\n### {path}  ({w}x{h}, sent {int(w*scale)}x{int(h*scale)})  {time.time()-t0:.1f}s")
        print(content[:1400])
    except Exception as exc:                                       # noqa: BLE001
        print(f"\n### {path}: EYE FAILED -> {type(exc).__name__}: {exc}")
