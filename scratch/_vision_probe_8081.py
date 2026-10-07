"""Vision-board probe: render text+shape, ask the :8081 model what it sees."""
import base64
import io
import json
import urllib.request

from PIL import Image, ImageDraw

img = Image.new("RGB", (640, 200), "white")
d = ImageDraw.Draw(img)
d.text((40, 80), "HOJAIGA 42", fill=(0, 0, 0))
d.ellipse([450, 60, 560, 170], outline=(255, 0, 0), width=6)
buf = io.BytesIO()
img.save(buf, format="PNG")
b64 = base64.b64encode(buf.getvalue()).decode()

payload = {
    "model": "qwen3-vl",
    "messages": [{
        "role": "user",
        "content": [
            {"type": "text", "text": "What text is shown and what shape is drawn? Answer briefly."},
            {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}},
        ],
    }],
    "max_tokens": 120,
    "temperature": 0.1,
}
req = urllib.request.Request(
    "http://127.0.0.1:8081/v1/chat/completions",
    data=json.dumps(payload).encode(),
    headers={"Content-Type": "application/json"},
)
with urllib.request.urlopen(req, timeout=300) as resp:
    out = json.loads(resp.read().decode())
answer = out["choices"][0]["message"]["content"]
print("VISION_ANSWER=", repr(answer))
assert "HOJAIGA" in answer.upper() and "42" in answer, "OCR failed"
assert ("circle" in answer.lower() or "round" in answer.lower() or "oval" in answer.lower()), "shape failed"
print("VISION BOARD OK on :8081 (Qwen3-VL-8B)")
