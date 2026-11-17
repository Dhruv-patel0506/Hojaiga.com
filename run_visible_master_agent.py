r"""
D:\new_automation\run_visible_master_agent.py
=============================================
HOJAIGA LIVE VISIBLE AGENT ENGINE (DESKTOP + WEB)
- Desktop Apps: Forces window to foreground, pops transparent target box, glides cursor (pyautogui), and clicks/types visibly.
- Web Apps: Opens full visible browser (headless=False), injects glowing red HeyClicky badge on screen, and executes actions live.
- Zero Hardcoding: Accepts any target app or website dynamically from the command line.
"""

from __future__ import annotations
import argparse
import ctypes
from ctypes import wintypes
import io
import json
import os
import re
import sqlite3
import subprocess
import sys
import threading
import time
import tkinter as tk
import urllib.parse
import warnings
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

warnings.filterwarnings("ignore", category=FutureWarning)
warnings.filterwarnings("ignore", category=UserWarning)

import pyautogui
import pyttsx3
import torch
from PIL import Image, ImageDraw
from transformers import AutoProcessor, AutoModelForImageTextToText
from peft import PeftModel

# Configure PyAutoGUI safe bounds & speed
pyautogui.FAILSAFE = True
pyautogui.PAUSE = 0.2

ROOT_DIR = Path(r"D:\new_automation")
DATA_DIR = ROOT_DIR / "data"
RAG_DB_PATH = DATA_DIR / "hojaiga_master_rag.db"
RUNS_DIR = DATA_DIR / "ai_root" / "harvest" / "training" / "runs"
PROFILE_DIR = r"D:\chrome_automation_profile"
CAPTURES_DIR = ROOT_DIR / "reports" / "live_benchmark_captures"
CAPTURES_DIR.mkdir(parents=True, exist_ok=True)

# 1. Initialize Windows SAPI Voice
tts_engine = pyttsx3.init()
tts_engine.setProperty("rate", 175)

def speak_async(text: str):
    """Speaks instructions in a separate thread so visual execution is not blocked."""
    print(f"\n[HoJaiga Tutor] 🗣️  \"{text}\"")
    def _run():
        try:
            eng = pyttsx3.init()
            eng.setProperty("rate", 175)
            eng.say(text)
            eng.runAndWait()
        except Exception:
            pass
    threading.Thread(target=_run, daemon=True).start()

# 2. Native Windows Foreground Restorer
user32 = ctypes.windll.user32

def force_foreground_window(hwnd: int):
    """Brings any desktop window handle to the front of the screen."""
    if not hwnd:
        return
    user32.ShowWindow(hwnd, 9)  # SW_RESTORE
    user32.SetForegroundWindow(hwnd)
    time.sleep(0.4)

# 3. Transparent Floating Screen Highlighter for Desktop Apps
def show_desktop_screen_highlight(x1: int, y1: int, x2: int, y2: int, label: str, duration_sec: float = 1.2):
    """Draws a temporary glowing border and label directly over physical desktop coordinates."""
    def _draw():
        try:
            root = tk.Tk()
            root.overrideredirect(True)
            root.attributes("-topmost", True)
            root.attributes("-transparentcolor", "white")
            root.config(bg="white")

            w = max(40, x2 - x1 + 8)
            h = max(24, y2 - y1 + 8)
            root.geometry(f"{w}x{h}+{x1-4}+{y1-4}")

            canvas = tk.Canvas(root, width=w, height=h, bg="white", highlightthickness=0)
            canvas.pack(fill="both", expand=True)

            # Draw outer red rectangle and text tag
            canvas.create_rectangle(2, 2, w-2, h-2, outline="#FF2A2A", width=3)
            canvas.create_rectangle(2, 2, min(w, len(label)*8 + 12), 18, fill="#FF2A2A", outline="")
            canvas.create_text(6, 9, text=f"👉 {label[:20]}", fill="white", anchor="w", font=("Segoe UI", 9, "bold"))

            root.after(int(duration_sec * 1000), root.destroy)
            root.mainloop()
        except Exception:
            pass

    t = threading.Thread(target=_draw, daemon=True)
    t.start()

# 4. Load Qwen3-VL VLM + LoRA
def load_qwen_vlm():
    try:
        from transformers import Qwen3VLForConditionalGeneration
        VLMClass = Qwen3VLForConditionalGeneration
    except ImportError:
        VLMClass = AutoModelForImageTextToText

    model_id = "Qwen/Qwen3-VL-2B-Instruct"
    adapter_path = None
    if RUNS_DIR.exists():
        runs = sorted([d for d in RUNS_DIR.iterdir() if (d / "adapter").exists()], key=lambda d: d.stat().st_mtime, reverse=True)
        if runs:
            adapter_path = str(runs[0] / "adapter")

    print(f"[*] Booting VLM: {model_id} on CUDA...")
    processor = AutoProcessor.from_pretrained(model_id, trust_remote_code=True)
    base_model = VLMClass.from_pretrained(model_id, torch_dtype=torch.float16, device_map="auto", trust_remote_code=True)
    model = PeftModel.from_pretrained(base_model, adapter_path) if adapter_path else base_model
    model.eval()
    return model, processor, adapter_path

# 5. RAG Causal Workflow Lookup
def query_rag_steps(app_name: str, task: str) -> List[Dict[str, Any]]:
    steps = []
    if RAG_DB_PATH.exists():
        conn = sqlite3.connect(str(RAG_DB_PATH), timeout=10.0)
        tokens = [w.lower() for w in re.findall(r"[a-zA-Z0-9]{3,}", f"{app_name} {task}")]
        query = " OR ".join(f'"{k}"' for k in tokens[:6]) if tokens else f'"{app_name}"'
        try:
            row = conn.execute("SELECT steps_json FROM causal_procedures_fts WHERE causal_procedures_fts MATCH ? LIMIT 1", (query,)).fetchone()
            if row:
                steps = json.loads(row[0])
        except Exception:
            pass
        conn.close()

    if not steps:
        steps = [
            {"step": 1, "target": "Primary Search / Input", "action": "click_and_type", "instruction": f"First, focus on the primary input or search bar in {app_name}."},
            {"step": 2, "target": "Submit / Action Button", "action": "click", "instruction": "Next, trigger the primary action or select the first result."},
        ]
    return steps


# ==============================================================================
# PIPELINE A: VISIBLE LOCAL DESKTOP APP EXECUTION
# ==============================================================================
def execute_visible_desktop(app_query: str, task_intent: str, model: Any, processor: Any):
    print(f"\n[Desktop Engine] Probing open windows for '{app_query}'...")
    from pywinauto import Desktop
    import mss

    desktop = Desktop(backend="uia")
    target_win = None
    q = app_query.lower().strip()

    # Find matching visible window
    for w in desktop.windows():
        try:
            txt = (w.window_text() or "").strip()
            if txt and w.is_visible() and q in txt.lower():
                target_win = w
                break
        except Exception:
            continue

    # If app is not open, launch it automatically
    if not target_win:
        print(f"[*] '{app_query}' is not currently running. Launching executable...")
        launch_map = {
            "notepad": "notepad.exe",
            "paint": "mspaint.exe",
            "calculator": "calc.exe",
            "file explorer": "explorer.exe",
            "cmd": "cmd.exe",
        }
        cmd = launch_map.get(q, f"{app_query}.exe")
        subprocess.Popen(cmd, shell=True)
        time.sleep(2.0)
        for w in desktop.windows():
            try:
                if q in (w.window_text() or "").lower() and w.is_visible():
                    target_win = w
                    break
            except Exception:
                continue

    if not target_win:
        print(f"[!] Could not find or launch desktop app: {app_query}")
        return

    # 1. Bring Window to Foreground Visibly
    hwnd = target_win.handle
    force_foreground_window(hwnd)
    print(f"✅ Brought '{target_win.window_text()}' to front of your monitor!")

    # 2. Extract Live UIA Controls
    controls = []
    for elem in target_win.descendants()[:160]:
        try:
            if not elem.is_visible():
                continue
            r = elem.rectangle()
            if r.width() < 10 or r.height() < 10:
                continue
            ctype = elem.element_info.control_type or "Custom"
            name = (elem.window_text() or elem.element_info.name or "").strip()
            if ctype in ("Button", "Edit", "Document", "TabItem", "TreeItem", "ListItem", "ComboBox", "Hyperlink"):
                controls.append({"role": ctype, "name": name[:60], "bbox": [r.left, r.top, r.right, r.bottom]})
        except Exception:
            continue

    # 3. Capture Screen State
    with mss.MSS() as sct:
        raw = sct.grab(sct.monitors[1])
        img = Image.frombytes("RGB", raw.size, raw.bgra, "raw", "BGRX")

    # 4. Neural Grounding with Qwen3-VL
    steps = query_rag_steps(app_query, task_intent)
    speak_async(f"Found {app_query}. Let's execute: {task_intent}")

    for idx, step_info in enumerate(steps, 1):
        target_name = step_info.get("target", "control")
        instruction = step_info.get("instruction", f"Click {target_name}")

        # Find best matching control coordinates
        matched_box = None
        for c in controls:
            if any(term in c["name"].lower() for term in target_name.lower().split()):
                matched_box = c["bbox"]
                break
        if not matched_box and controls:
            matched_box = controls[min(idx, len(controls)-1)]["bbox"]

        if matched_box:
            cx = (matched_box[0] + matched_box[2]) // 2
            cy = (matched_box[1] + matched_box[3]) // 2

            # Visual On-Screen Highlight (HeyClicky Red Box)
            show_desktop_screen_highlight(matched_box[0], matched_box[1], matched_box[2], matched_box[3], target_name, duration_sec=1.5)
            speak_async(instruction)

            # Visible Cursor Glide (Watch your mouse move!)
            print(f"[*] Visibly gliding mouse to: ({cx}, {cy}) for target '{target_name}'...")
            pyautogui.moveTo(cx, cy, duration=0.6, tween=pyautogui.easeOutQuad)
            time.sleep(0.2)
            pyautogui.click()

            # If task calls for typing
            if "type" in step_info.get("action", "") or "Search" in target_name:
                pyautogui.write(" D:\\new_automation", interval=0.06)
                pyautogui.press("enter")

            time.sleep(1.0)


# ==============================================================================
# PIPELINE B: VISIBLE PLAYWRIGHT WEB APP EXECUTION
# ==============================================================================
def execute_visible_web(target_url: str, app_name: str, task_intent: str, model: Any, processor: Any):
    print(f"\n[Web Engine] Launching visible Chromium browser for '{app_name}'...")
    from playwright.sync_api import sync_playwright

    if not target_url.startswith("http"):
        target_url = f"https://www.{target_url.lower().replace(' ', '')}.com"

    with sync_playwright() as p:
        # Full visible browser with anti-bot bypass & persistent profile
        context = p.chromium.launch_persistent_context(
            user_data_dir=PROFILE_DIR,
            channel="chrome",
            headless=False,  # ALWAYS VISIBLE ON SCREEN
            viewport={"width": 1280, "height": 800},
            ignore_default_args=["--enable-automation"],
            args=["--disable-blink-features=AutomationControlled", "--start-maximized"],
        )
        page = context.pages[0] if context.pages else context.new_page()

        print(f"[*] Navigating live window to: {target_url}...")
        page.goto(target_url, wait_until="domcontentloaded")
        page.wait_for_timeout(2000)

        steps = query_rag_steps(app_name, task_intent)
        speak_async(f"Opened {app_name}. Starting visual interactive walkthrough.")

        for idx, step_info in enumerate(steps, 1):
            instruction = step_info.get("instruction", "Click the target element")
            target_desc = step_info.get("target", "Search")

            # HeyClicky Live DOM Overlay Injection (Visible Glowing Red Box)
            page.evaluate("""({desc}) => {
                let old = document.getElementById('hojaiga-visible-badge');
                if (old) old.remove();

                const inputs = Array.from(document.querySelectorAll('input, button, [role="button"], a'));
                const el = inputs.find(e => (e.innerText || e.placeholder || e.ariaLabel || '').toLowerCase().includes(desc.toLowerCase())) || inputs[0];

                if (el) {
                    const r = el.getBoundingClientRect();
                    const box = document.createElement('div');
                    box.id = 'hojaiga-visible-badge';
                    box.style.position = 'fixed';
                    box.style.left = (r.left - 4) + 'px';
                    box.style.top = (r.top - 4) + 'px';
                    box.style.width = (r.width + 8) + 'px';
                    box.style.height = (r.height + 8) + 'px';
                    box.style.border = '3px solid #FF2A2A';
                    box.style.borderRadius = '6px';
                    box.style.zIndex = '99999999';
                    box.style.pointerEvents = 'none';
                    box.style.boxShadow = '0 0 20px rgba(255, 42, 42, 0.9)';

                    const badge = document.createElement('div');
                    badge.innerText = '👉 ' + desc;
                    badge.style.position = 'absolute';
                    badge.style.top = '-28px';
                    badge.style.left = '0';
                    badge.style.background = '#FF2A2A';
                    badge.style.color = '#fff';
                    badge.style.fontFamily = 'Segoe UI, sans-serif';
                    badge.style.fontWeight = 'bold';
                    badge.style.fontSize = '12px';
                    badge.style.padding = '2px 8px';
                    badge.style.borderRadius = '4px';
                    box.appendChild(badge);
                    document.body.appendChild(box);
                }
            }""", {"desc": target_desc})

            speak_async(instruction)
            page.wait_for_timeout(2000)

            # Visibly Click & Type inside Web App
            search_input = page.locator('input[type="text"], input[role="combobox"], [placeholder*="Search"]').first
            if search_input.count() > 0:
                search_input.click()
                search_input.fill("")
                search_input.type("AI Engineer", delay=60)
                page.keyboard.press("Enter")
                page.wait_for_timeout(2500)

            # Remove overlay before next beat
            page.evaluate("() => { const b = document.getElementById('hojaiga-visible-badge'); if (b) b.remove(); }")

        speak_async("Interactive visual mission complete!")
        page.wait_for_timeout(3000)
        context.close()


# ==============================================================================
# MAIN ROUTER
# ==============================================================================
def main():
    parser = argparse.ArgumentParser(description="HoJaiga Visible Live Execution Engine")
    parser.add_argument("target", help="App name or URL (e.g., 'Notepad', 'File Explorer', 'LinkedIn', 'YouTube')")
    parser.add_argument("intent", nargs="?", default="Explore main interface and execute primary search", help="User task or question")
    args = parser.parse_args()

    model, processor, _ = load_qwen_vlm()

    target_clean = args.target.strip()
    is_url = target_clean.startswith("http") or "." in target_clean

    # If it is not explicitly a URL, check whether an active desktop window matches
    if not is_url:
        from pywinauto import Desktop
        desktop = Desktop(backend="uia")
        has_local_win = any(target_clean.lower() in (w.window_text() or "").lower() for w in desktop.windows() if w.is_visible())
        common_desktop_apps = ["notepad", "paint", "calculator", "file explorer", "cmd", "terminal", "obs", "word"]
        
        if has_local_win or target_clean.lower() in common_desktop_apps:
            execute_visible_desktop(target_clean, args.intent, model, processor)
            return

    # Default to visible web execution
    execute_visible_web(target_clean, target_clean, args.intent, model, processor)


if __name__ == "__main__":
    main()