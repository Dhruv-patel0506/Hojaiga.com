"""
D:\\new_automation\\run_autonomous_app_tutor.py
=============================================
HOJAIGA AUTONOMOUS APP REVERSE-ENGINEER & LIVE INTERACTIVE TUTOR
- Stage 1: Zero-Knowledge Discovery (Probes real UI controls via UIA/DOM).
- Stage 2: Spatial Zone Clustering & Purpose Deduction via Qwen3-VL; EVERY non-frame control goes into the Stage 3 queue (no cap).
- Stage 3: Interactive Guidance (Red Highlight Box + Voice Explanation + Live Actuation); each explanation is one VLM sentence about that control in its container;
           the window rectangle is re-read and the target re-normalised before every move / click / type.
- Stage 4: Zero-VRAM RAG Causal Persistence behind a pre-save gate: COMPLETE only when the scan holds its archetype's core controls, else INCOMPLETE_SCAN and a re-scan.

Live runs steal the screen: they need HOJAIGA_ALLOW_LIVE=1. `--replay trace.json [trace2.json ...]` runs the whole pipeline offline from saved scan traces (attempt N of the
re-scan loop reads the Nth file) and needs no window, no GPU and no model (`--vlm` opts in to the model on CPU).
The VLM runs on CPU unless HOJAIGA_TUTOR_GPU=1.
"""

from __future__ import annotations
import argparse
import json
import os
import sys
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT_DIR = Path(r"D:\new_automation")
for _p in (str(ROOT_DIR), str(ROOT_DIR / "All codes")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from core_organs import scan_gate, tutor_logic            # noqa: E402  (pure python, no torch / GUI)

DATA_DIR = ROOT_DIR / "data"
RAG_DB_PATH = DATA_DIR / "hojaiga_master_rag.db"
RUNS_DIR = DATA_DIR / "ai_root" / "harvest" / "training" / "runs"
DISCOVERY_CAPS = (400, 1600, None)       # descendants read on scan attempt 0, 1, 2+ (None = all); the first pass used a fixed 200 and silently lost controls
INTERACTIVE_TYPES = ("Button", "SplitButton", "Edit", "Document", "TabItem", "TreeItem", "ListItem", "ComboBox", "MenuItem", "CheckBox", "RadioButton", "Hyperlink", "Slider")
CONTEXT_TYPES = ("Text", "Pane", "Group", "Custom", "Image", "ToolBar", "List", "Tree", "Tab", "Window")      # never queued: used for the gate and for container context


# 1. Voice Engine
def speak(text: str):
    print(f"\n[HoJaiga Tutor] \"{text}\"")
    try:
        import pyttsx3
        engine = pyttsx3.init()
        engine.setProperty("rate", 170)
        engine.say(text)
        engine.runAndWait()
    except Exception:
        pass


# 2. Transparent On-Screen Highlight Box (HeyClicky Overlay)
def draw_screen_highlight(x1: int, y1: int, x2: int, y2: int, label: str, duration_sec: float = 3.5):
    def _run():
        try:
            import tkinter as tk
            root = tk.Tk()
            root.overrideredirect(True)
            root.attributes("-topmost", True)
            root.attributes("-transparentcolor", "white")
            root.config(bg="white")

            w = max(40, x2 - x1 + 10)
            h = max(24, y2 - y1 + 10)
            root.geometry(f"{w}x{h}+{x1-5}+{y1-5}")

            canvas = tk.Canvas(root, width=w, height=h, bg="white", highlightthickness=0)
            canvas.pack(fill="both", expand=True)

            canvas.create_rectangle(2, 2, w-2, h-2, outline="#FF2A2A", width=3)
            tag_w = min(w, len(label)*8 + 16)
            canvas.create_rectangle(2, 2, tag_w, 20, fill="#FF2A2A", outline="")
            canvas.create_text(6, 10, text=f"-> {label[:25]}", fill="white", anchor="w", font=("Segoe UI", 9, "bold"))

            root.after(int(duration_sec * 1000), root.destroy)
            root.mainloop()
        except Exception:
            pass

    threading.Thread(target=_run, daemon=True).start()


# 3. Model Loader (CPU by default)
def load_vlm():
    import torch
    from transformers import AutoProcessor, AutoModelForImageTextToText
    try:
        from transformers import Qwen3VLForConditionalGeneration
        VLMClass = Qwen3VLForConditionalGeneration
    except ImportError:
        VLMClass = AutoModelForImageTextToText

    use_gpu = os.environ.get("HOJAIGA_TUTOR_GPU") == "1" and torch.cuda.is_available()
    model_id = "Qwen/Qwen3-VL-2B-Instruct"
    adapter_path = None
    if RUNS_DIR.exists():
        runs = sorted([d for d in RUNS_DIR.iterdir() if (d / "adapter").exists()], key=lambda d: d.stat().st_mtime, reverse=True)
        if runs:
            adapter_path = str(runs[0] / "adapter")

    print(f"[*] Loading {model_id} on {'CUDA' if use_gpu else 'CPU'}...")
    processor = AutoProcessor.from_pretrained(model_id, trust_remote_code=True)
    if use_gpu:
        base_model = VLMClass.from_pretrained(model_id, torch_dtype=torch.float16, device_map="auto", trust_remote_code=True)
    else:
        base_model = VLMClass.from_pretrained(model_id, torch_dtype=torch.float32, trust_remote_code=True)
    if adapter_path:
        from peft import PeftModel
        model = PeftModel.from_pretrained(base_model, adapter_path)
    else:
        model = base_model
    model.eval()
    return model, processor


def make_vlm_fn(model: Any, processor: Any, max_new_tokens: int = 60):
    """vlm_fn(image, prompt) -> the model's NEW text only (the old code decoded the prompt together with the answer)."""
    import torch

    def _fn(image: Any, prompt: str) -> str:
        content = ([{"type": "image", "image": image}] if image is not None else []) + [{"type": "text", "text": prompt}]
        text = processor.apply_chat_template([{"role": "user", "content": content}], tokenize=False, add_generation_prompt=True)
        inputs = processor(text=[text], images=[image] if image is not None else None, return_tensors="pt").to(model.device)
        with torch.inference_mode():
            out = model.generate(**inputs, max_new_tokens=max_new_tokens, do_sample=False)
        return processor.decode(out[0][inputs["input_ids"].shape[1]:], skip_special_tokens=True).strip()

    return _fn


# 4. Live Discovery Engine (Desktop Win32 / UIA)
def discover_desktop_controls(app_query: str, max_descendants: Optional[int] = 400) -> Optional[Dict[str, Any]]:
    from pywinauto import Desktop
    import mss
    from PIL import Image

    desktop = Desktop(backend="uia")
    matched_win = None
    q = app_query.lower().strip()

    for w in desktop.windows():
        try:
            txt = (w.window_text() or "").strip()
            if txt and w.is_visible() and q in txt.lower():
                matched_win = w
                break
        except Exception:
            continue

    if not matched_win:
        return None

    matched_win.set_focus()
    time.sleep(0.3)
    rect = tutor_logic.live_rect(matched_win)
    if rect is None:
        return None

    with mss.MSS() as sct:
        monitor = {"top": max(0, rect[1]), "left": max(0, rect[0]), "width": max(100, rect[2]), "height": max(100, rect[3])}
        raw = sct.grab(monitor)
        pil_img = Image.frombytes("RGB", raw.size, raw.bgra, "raw", "BGRX")

    controls: List[Dict[str, Any]] = []
    context: List[Dict[str, Any]] = []
    descendants = matched_win.descendants()
    if max_descendants:
        descendants = descendants[:max_descendants]
    for elem in descendants:
        try:
            if not elem.is_visible():
                continue
            r = elem.rectangle()
            if r.width() < 10 or r.height() < 10:
                continue
            ctype = elem.element_info.control_type or "Element"
            name = (elem.window_text() or elem.element_info.name or "").strip()
            item = {"role": ctype, "name": name, "bbox": [r.left, r.top, r.right, r.bottom]}
            if name and ctype in INTERACTIVE_TYPES:
                controls.append(item)
            elif name and ctype in CONTEXT_TYPES:
                context.append(item)
        except Exception:
            continue

    return {"title": matched_win.window_text(), "window_obj": matched_win, "rect": rect, "image": pil_img,
            "controls": tutor_logic.normalise_controls(controls, rect), "context_controls": tutor_logic.normalise_controls(context, rect),
            "gate_controls": controls + context, "descendants_read": len(descendants)}


def replay_scan_fn(trace_paths: List[str]):
    """scan_fn for offline replay: attempt N reads the Nth trace (the last one repeats)."""
    def _fn(attempt: int) -> Optional[Dict[str, Any]]:
        p = trace_paths[min(attempt, len(trace_paths) - 1)]
        try:
            trace = json.loads(Path(p).read_text(encoding="utf-8"))
        except Exception as e:
            print(f"[!] replay trace unreadable ({p}): {e}")
            return None
        s = tutor_logic.controls_from_trace(trace)
        s.update(context_controls=[], gate_controls=s["controls"], image=None, window_obj=None, source=p)
        s["title"] = s["title"] or Path(p).stem
        return s
    return _fn


# 5. RAG Causal Logger (behind the pre-save gate)
def log_learned_workflow_to_rag(app_name: str, app_purpose: str, steps: List[Dict[str, Any]], verdict: Dict[str, Any], db_path: Optional[Path] = None) -> Dict[str, Any]:
    db = Path(db_path) if db_path else RAG_DB_PATH
    if not db.exists():
        print(f"[!] RAG database not found: {db}")
        return {"saved": False, "error": "db_missing"}
    key = scan_gate._norm(app_name) or "unknown_app"
    res = scan_gate.record_scan(str(db), key, app_name, verdict, app_purpose, steps)
    if res.get("saved"):
        if res["status"] == scan_gate.COMPLETE:
            print(f"[*] Saved learned workflow for '{app_name}' into the RAG ({res['status']}, archetype={verdict.get('archetype')}).")
        else:
            print(f"[!] '{app_name}' stored as {res['status']} ({verdict.get('reason')}) - NOT retrievable; it is queued for re-scan.")
    else:
        print(f"[!] RAG persistence failed: {res.get('error')}")
    return res


# 6. Autonomous Teaching & Actuation Controller
def reverse_engineer_and_teach(app_name: str, surface_data: Dict[str, Any], vlm_fn: Optional[Any] = None, actuate: bool = True, speak_fn: Any = speak,
                               highlight_fn: Any = draw_screen_highlight, vlm_budget_sec: Optional[float] = 600.0, pause_sec: float = 1.5) -> Dict[str, Any]:
    controls = surface_data["controls"]
    title = surface_data["title"]
    img = surface_data.get("image")
    rect = surface_data.get("rect")
    win_obj = surface_data.get("window_obj")
    all_ctrl = controls + surface_data.get("context_controls", [])

    print("\n" + "=" * 80)
    print(f"STAGE 1: REVERSE-ENGINEERING SURFACES FOR '{title.upper()}'")
    print("=" * 80)

    input_fields = [c for c in controls if c["role"] in ("Edit", "searchbox") or "search" in c["name"].lower()]
    action_buttons = [c for c in controls if c["role"] in ("Button", "MenuItem", "SplitButton")]
    nav_links = [c for c in controls if c["role"] in ("TabItem", "TreeItem", "Hyperlink")]

    app_explanation = f"{title} provides an interactive workspace with {len(controls)} discovered controls including inputs, action buttons, and navigation elements."
    if vlm_fn is not None:
        summary_prompt = (
            f"You are HoJaiga Tutor. App: '{title}'. Discovered Controls:\n"
            f"- Inputs: {[c['name'] for c in input_fields[:5]]}\n"
            f"- Actions: {[c['name'] for c in action_buttons[:8]]}\n"
            f"- Nav: {[c['name'] for c in nav_links[:6]]}\n"
            f"Explain in 2 concise sentences what this software does and how its workspace is organized."
        )
        try:
            text = vlm_fn(img.resize((960, 540)) if img is not None else None, summary_prompt)
            if text and len(text.split()) >= 5:
                app_explanation = text
        except Exception as e:
            print(f"[*] VLM Processing Note: {e}")

    print("\n" + "=" * 80)
    print("STAGE 2: NATURAL INTELLIGENCE DEDUCTION")
    print("=" * 80)
    print(f"App Purpose: {app_explanation}")
    speak_fn(f"I have scanned and reverse-engineered {app_name}. {app_explanation}")

    # Every non-chrome control discovered above goes to Stage 3 - nothing is capped
    audit = tutor_logic.queue_audit(controls, win_size=(rect[2], rect[3]) if rect else None, rect=rect)
    lesson_queue = audit["queued"]
    print(f"Stage 2 -> 3 queue: {len(lesson_queue)} of {audit['total']} controls (dropped: {audit['dropped']})")

    print("\n" + "=" * 80)
    print(f"STAGE 3: INTERACTIVE SHOW-AND-TELL & ACTUATION ({len(lesson_queue)} Grounded Steps)")
    print("=" * 80)

    recorded_steps: List[Dict[str, Any]] = []
    cache: Dict[str, Dict[str, str]] = {}
    t_vlm = time.time()
    mouse = None
    if actuate and win_obj is not None:
        from pywinauto import mouse as _mouse
        mouse = _mouse

    for idx, control in enumerate(lesson_queue, 1):
        label = control["name"]
        over_budget = vlm_budget_sec is not None and (time.time() - t_vlm) > vlm_budget_sec
        exp = tutor_logic.explain_control(control, all_ctrl, image=img, rect=rect, app_title=title,
                                          vlm_fn=None if over_budget else vlm_fn, cache=cache)
        explanation = exp["text"]

        # re-read the live rectangle and re-normalise before anything is drawn or moved
        live = tutor_logic.live_rect(win_obj) if win_obj is not None else None
        use_rect = live or rect
        pt = tutor_logic.resolve_point(control, use_rect) if use_rect else None
        b = control["bbox"]
        print(f"\n[Step {idx}/{len(lesson_queue)}] Focus: '{label}' ({control['role']}) at {list(pt) if pt else None}  [{exp['source']}]")

        if live and pt:
            hw, hh = (b[2] - b[0]) / 2.0, (b[3] - b[1]) / 2.0
            highlight_fn(int(pt[0] - hw), int(pt[1] - hh), int(pt[0] + hw), int(pt[1] + hh), label, duration_sec=3.5)
        speak_fn(f"Step {idx}. {explanation}")

        act = {"ok": False, "reason": "not_actuated"}
        if actuate and win_obj is not None:
            act = tutor_logic.act_on_control(win_obj, control, "move", mouse=mouse, settle=lambda: time.sleep(0.2))
            if not act["ok"]:
                print(f"   [Actuation Note]: {act['reason']}")

        recorded_steps.append({
            "step_num": idx,
            "control": label,
            "role": control["role"],
            "coords": list(pt) if pt else None,
            "norm": [round(control["norm"]["cx"], 4), round(control["norm"]["cy"], 4)] if control.get("norm") else None,
            "explanation": explanation,
            "explanation_source": exp["source"],
            "actuation": act["reason"],
        })
        if pause_sec:
            time.sleep(pause_sec)

    return {"app_purpose": app_explanation, "steps": recorded_steps, "queue_audit": {k: audit[k] for k in ("total", "dropped", "balanced")}}


def main():
    parser = argparse.ArgumentParser(description="HoJaiga Autonomous App Reverse-Engineer & Tutor")
    parser.add_argument("app", help="Application name (e.g. 'Notepad', 'Discord', 'File Explorer', 'WhatsApp')")
    parser.add_argument("--no-actuation", action="store_true", help="Disable physical mouse movement during discovery")
    parser.add_argument("--replay", nargs="+", metavar="TRACE", help="run offline from saved scan trace(s); attempt N of the re-scan loop reads the Nth file")
    parser.add_argument("--vlm", action="store_true", help="in --replay mode, also load the VLM (CPU) for the explanations")
    parser.add_argument("--db", help="RAG database to write to (default: the master RAG db; replay without --db writes nothing)")
    parser.add_argument("--max-rescans", type=int, default=2)
    parser.add_argument("--vlm-budget-sec", type=float, default=600.0, help="after this many seconds of model time the remaining explanations use the labelled context fallback (0 = no limit)")
    args = parser.parse_args()

    app_name = args.app.strip()
    live = not args.replay
    if live and os.environ.get("HOJAIGA_ALLOW_LIVE") != "1":
        print("REFUSED: a live run focuses a real window and moves the mouse. Set HOJAIGA_ALLOW_LIVE=1 only when the person has asked for it, or use --replay trace.json.")
        return

    scan_fn = replay_scan_fn(args.replay) if args.replay else (
        lambda attempt: discover_desktop_controls(app_name, DISCOVERY_CAPS[min(attempt, len(DISCOVERY_CAPS) - 1)]))
    surface_data, verdict, history = scan_gate.recursive_scan(
        scan_fn, app_name, max_rescans=args.max_rescans,
        on_attempt=lambda a, v: print(f"[gate] scan attempt {a}: {v['status']} ({v['reason']})"))

    if not surface_data or not surface_data["controls"]:
        print(f"[!] Could not find running application window matching '{app_name}'. Ensure it is open and visible.")
        return

    vlm_fn = None
    if live or args.vlm:
        model, processor = load_vlm()
        vlm_fn = make_vlm_fn(model, processor)

    result = reverse_engineer_and_teach(app_name, surface_data, vlm_fn, actuate=live and not args.no_actuation,
                                        speak_fn=speak if live else (lambda t: print(f"[HoJaiga Tutor] {t}")),
                                        highlight_fn=draw_screen_highlight if live else (lambda *a, **k: None),
                                        vlm_budget_sec=args.vlm_budget_sec or None, pause_sec=1.5 if live else 0.0)
    db = Path(args.db) if args.db else (RAG_DB_PATH if live else None)
    if db:
        log_learned_workflow_to_rag(app_name, result["app_purpose"], result["steps"], verdict, db)
    print(f"\n[gate] final: {verdict['status']} archetype={verdict.get('archetype')} missing={verdict.get('missing')} attempts={len(history)}")
    if live:
        speak(f"Walkthrough complete! That covers the primary interface of {app_name}.")


if __name__ == "__main__":
    main()
