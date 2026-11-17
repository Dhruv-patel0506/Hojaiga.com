"""
picker -- the trained adapter, in the loop.

    python -m core_organs.mind.picker serve [--adapter DIR] [--port 11500] [--idle-unload-s 240]    local server; the model loads on the first request and is FREED after idle, so the trainer can have the GPU
    python -m core_organs.mind.picker ask --app web:x.com --intent "Open the Pricing page" --elements "link|Home" "link|Pricing"
    HOJAIGA_PICKER_URL=http://127.0.0.1:11500   turns it on for the executor's judge (desktop_grounding.ElementJudge.decide asks it first and keeps its own judge as the fallback)

The question is always the shape the adapter was trained on (SYSTEM_V2 + numbered elements + intent). The answer is one action: click <n> | confirm <n> (it would send / pay / delete: ask the person) | replan (the screen is not where the plan expects).
Whatever it answers is CHECKED by the caller: an index outside the list, a verb that is not legal, or a missing server all fall back to the existing judge, so a bad answer costs one step, not a wrong click.
"""
from __future__ import annotations

import argparse
import gc
import json
import os
import re
import threading
import time
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Dict, List, Optional, Sequence

PICKER_URL = os.environ.get("HOJAIGA_PICKER_URL", "")
BASE_MODEL = os.environ.get("HOJAIGA_PICKER_BASE", "Qwen/Qwen3-VL-2B-Instruct")
RUNS = r"D:\new_automation\data\ai_root\harvest\training\runs"

SYSTEM_V2 = ("You operate software by reading a numbered list of on-screen elements. Reply with a JSON list holding ONE action: "
             "[{\"step\": 1, \"action\": \"click|hotkey|type|confirm|replan\", \"target_id\": <number or null>, \"hotkey\": <keys or null>, \"text\": <text or null>, \"verify_expectation\": \"<what the screen should show next>\"}]. "
             "Use confirm (target_id = the control, text = the kind of risk: money, publish, delete, account, consent, install) when pressing the control would pay, send, publish, delete, sign out, "
             "agree or install, so the person is asked first. Use replan (text = not_here) when the Plan is given and none of its controls are on the screen.")


def user_prompt(app: str, elements: Sequence[Dict[str, str]], intent: str, plan: Sequence[str] = (), done: int = 0) -> str:
    lines = "\n".join(f"#{i} {e.get('role', 'control')} '{e.get('name', '')}'" for i, e in enumerate(elements, 1))
    plan_txt = ""
    if plan:
        plan_txt = "Plan:\n" + "\n".join(f"{i}. {'[done] ' if i <= done else ''}{p}" for i, p in enumerate(plan, 1)) + "\n"
    return f"Application: {app}\nElements:\n{lines}\n{plan_txt}Intent: {intent}\nPredict exact Action JSON:"


def parse_reply(text: str) -> Optional[Dict[str, Any]]:
    dec = json.JSONDecoder()
    for m in re.finditer(r"\[", text or ""):
        try:
            arr, _ = dec.raw_decode(text[m.start():])
        except (json.JSONDecodeError, ValueError):
            continue
        if isinstance(arr, list) and arr and isinstance(arr[0], dict) and arr[0].get("action"):
            return arr[0]
    kind = re.search(r'"action"\s*:\s*"(\w+)"', text or "")                      # cut off inside the free-text verify_expectation: every field that is acted on has already arrived
    if not kind:
        return None
    out: Dict[str, Any] = {"step": 1, "action": kind.group(1), "target_id": None, "hotkey": None, "text": None, "verify_expectation": "", "truncated": True}
    tid = re.search(r'"target_id"\s*:\s*(\d+)', text)
    if tid:
        out["target_id"] = int(tid.group(1))
    txt = re.search(r'"text"\s*:\s*"((?:[^"\\]|\\.)*)"', text)
    if txt:
        out["text"] = txt.group(1)
    return out


# ---- client -------------------------------------------------------------------------------------------------------------------------------------------
def available(url: str = "") -> bool:
    url = url or os.environ.get("HOJAIGA_PICKER_URL", "") or PICKER_URL
    if not url:
        return False
    try:
        with urllib.request.urlopen(url.rstrip("/") + "/health", timeout=1.5) as r:
            return r.status == 200
    except Exception:
        return False


def ask(app: str, elements: Sequence[Dict[str, str]], intent: str, plan: Sequence[str] = (), done: int = 0, url: str = "", timeout: float = 90.0) -> Optional[Dict[str, Any]]:
    """One action from the adapter, validated against the list; None when the server is down or the answer is unusable (the caller then uses its own judge)."""
    url = (url or os.environ.get("HOJAIGA_PICKER_URL", "") or PICKER_URL).rstrip("/")
    if not url or not elements:
        return None
    body = json.dumps({"app": app, "elements": list(elements), "intent": intent, "plan": list(plan), "done": done}).encode("utf-8")
    try:
        req = urllib.request.Request(url + "/pick", data=body, headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req, timeout=timeout) as r:
            out = json.loads(r.read().decode("utf-8"))
    except Exception:
        return None
    return validate(out.get("action"), len(elements), bool(plan))


def validate(act: Optional[Dict[str, Any]], n_elements: int, has_plan: bool = False) -> Optional[Dict[str, Any]]:
    if not isinstance(act, dict):
        return None
    kind = str(act.get("action", "")).lower()
    if kind in ("click", "confirm"):
        try:
            tid = int(act.get("target_id"))
        except (TypeError, ValueError):
            return None
        if not 1 <= tid <= n_elements:
            return None
        return {**act, "action": kind, "target_id": tid}
    if kind == "replan":
        return {**act, "action": "replan", "target_id": None} if has_plan else None
    if kind in ("hotkey", "type"):
        return act
    return None


# ---- server -------------------------------------------------------------------------------------------------------------------------------------------
class _Model:
    """The base model + adapter on the GPU, loaded on demand and dropped after `idle_s` without a request."""

    def __init__(self, adapter: str, idle_s: float, exit_on_idle: bool = False) -> None:
        self.adapter, self.idle_s, self.exit_on_idle = adapter, idle_s, exit_on_idle
        self.lock = threading.Lock()
        self.m: Any = None
        self.proc: Any = None
        self.last = time.time()
        self.loads = 0

    def _load(self) -> None:
        import torch
        from peft import PeftModel
        from transformers import AutoProcessor, BitsAndBytesConfig, Qwen3VLForConditionalGeneration
        bf16 = torch.cuda.is_bf16_supported()
        bnb = BitsAndBytesConfig(load_in_4bit=True, bnb_4bit_quant_type="nf4", bnb_4bit_use_double_quant=True, bnb_4bit_compute_dtype=torch.bfloat16 if bf16 else torch.float16, llm_int8_skip_modules=["visual", "lm_head"])
        base = Qwen3VLForConditionalGeneration.from_pretrained(BASE_MODEL, quantization_config=bnb, device_map={"": 0}, dtype=torch.bfloat16 if bf16 else torch.float16)
        self.m = PeftModel.from_pretrained(base, self.adapter) if self.adapter and os.path.isdir(self.adapter) else base
        self.m.eval()
        self.proc = AutoProcessor.from_pretrained(BASE_MODEL)
        self.loads += 1

    def unload(self) -> None:
        with self.lock:
            if self.m is None:
                return
            self.m, self.proc = None, None
            gc.collect()
            try:
                import torch
                torch.cuda.empty_cache()
            except Exception:
                pass

    def generate(self, system: str, user: str, max_new_tokens: int = 56) -> str:
        import torch
        with self.lock:
            if self.m is None:
                self._load()
            self.last = time.time()
            msgs = [{"role": "system", "content": [{"type": "text", "text": system}]}, {"role": "user", "content": [{"type": "text", "text": user}]}]
            enc = self.proc.apply_chat_template(msgs, tokenize=True, add_generation_prompt=True, return_dict=True, return_tensors="pt")
            enc = {k: (v.to(self.m.device) if hasattr(v, "to") else v) for k, v in enc.items()}
            with torch.no_grad():
                out = self.m.generate(**enc, max_new_tokens=max_new_tokens, do_sample=False)
            self.last = time.time()
            return self.proc.batch_decode(out[:, enc["input_ids"].shape[1]:], skip_special_tokens=True)[0]

    def watch(self) -> None:
        while True:
            time.sleep(10)
            if self.m is not None and time.time() - self.last > self.idle_s:
                if self.exit_on_idle:                   # measured: dropping the references left ~1.5 GB of the GPU held (CUDA context + allocator); only the process ending gives all of it back to the trainer
                    print("idle: exiting to free the GPU", flush=True)
                    os._exit(0)
                self.unload()


def newest_adapter() -> str:
    best, t = "", 0.0
    if os.path.isdir(RUNS):
        for d in os.listdir(RUNS):
            p = os.path.join(RUNS, d, "adapter")
            if os.path.isdir(p) and os.path.getmtime(p) > t:
                best, t = p, os.path.getmtime(p)
    return best


def serve(port: int, adapter: str, idle_s: float, system: str = SYSTEM_V2, exit_on_idle: bool = False) -> None:
    model = _Model(adapter, idle_s, exit_on_idle)
    threading.Thread(target=model.watch, daemon=True).start()

    class H(BaseHTTPRequestHandler):
        def log_message(self, *a: Any) -> None:
            pass

        def _send(self, code: int, obj: Dict[str, Any]) -> None:
            b = json.dumps(obj, ensure_ascii=False).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(b)))
            self.end_headers()
            self.wfile.write(b)

        def do_GET(self) -> None:
            if self.path == "/health":
                self._send(200, {"ok": True, "adapter": adapter, "loaded": model.m is not None, "loads": model.loads, "idle_unload_s": idle_s})
            else:
                self._send(404, {"error": "unknown"})

        def do_POST(self) -> None:
            if self.path != "/pick":
                return self._send(404, {"error": "unknown"})
            try:
                req = json.loads(self.rfile.read(int(self.headers.get("Content-Length", "0"))).decode("utf-8"))
                t0 = time.time()
                text = model.generate(system, user_prompt(req.get("app", ""), req.get("elements", []), req.get("intent", ""), req.get("plan", []), int(req.get("done", 0))))
                self._send(200, {"action": parse_reply(text), "raw": text[:300], "seconds": round(time.time() - t0, 2)})
            except Exception as e:
                self._send(500, {"error": f"{type(e).__name__}: {str(e)[:200]}"})

    srv = ThreadingHTTPServer(("127.0.0.1", port), H)
    print(f"picker listening on 127.0.0.1:{port}  adapter={adapter or '(none: base model)'}  idle unload {idle_s:.0f}s", flush=True)
    srv.serve_forever()


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["serve", "ask", "newest"])
    ap.add_argument("--adapter", default="")
    ap.add_argument("--port", type=int, default=11500)
    ap.add_argument("--idle-unload-s", type=float, default=240.0)
    ap.add_argument("--exit-on-idle", action="store_true", help="end the process when idle (the only way to hand ALL of the GPU back, e.g. before training)")
    ap.add_argument("--app", default="web:example.com")
    ap.add_argument("--intent", default="")
    ap.add_argument("--elements", nargs="*", default=[])
    ap.add_argument("--url", default="")
    a = ap.parse_args(argv)
    if a.cmd == "newest":
        print(newest_adapter())
        return 0
    if a.cmd == "serve":
        serve(a.port, a.adapter or newest_adapter(), a.idle_unload_s, exit_on_idle=a.exit_on_idle)
        return 0
    els = [{"role": e.split("|", 1)[0], "name": e.split("|", 1)[-1]} for e in a.elements]
    print(json.dumps(ask(a.app, els, a.intent, url=a.url or f"http://127.0.0.1:{a.port}"), indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
