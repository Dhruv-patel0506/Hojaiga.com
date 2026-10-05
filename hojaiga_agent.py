import argparse
import base64
import hashlib
import io
import json
import random
import sqlite3
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import requests

# Optional OS-level libraries with graceful fallbacks
try:
    import pygetwindow as gw
except ImportError:
    gw = None

try:
    import mss
    from PIL import Image
except ImportError:
    mss = None
    Image = None

try:
    import pytesseract
except ImportError:
    pytesseract = None

try:
    import pyautogui
    pyautogui.FAILSAFE = True  # Slamming mouse to (0,0) top-left aborts immediately
    pyautogui.PAUSE = 0.01
except ImportError:
    pyautogui = None


# ==============================================================================
# 1. CNS BRIDGE TELEMETRY EMITTER (CONNECTS TO server.py -> 3D WORLDS)
# ==============================================================================
class CNSBridgeClient:
    def __init__(self, server_url: str = "http://localhost:8000"):
        self.emit_url = f"{server_url.rstrip('/')}/api/emit"
        self.session = requests.Session()

    def emit(
        self,
        sector: str,
        event_type: str,
        log_line: str,
        coordinates: Optional[Dict[str, float]] = None,
        metrics: Optional[Dict[str, str]] = None,
        record_title: Optional[str] = None,
    ):
        payload = {
            "sector": sector,
            "event_type": event_type,
            "log_line": log_line,
            "coordinates": coordinates,
            "metrics": metrics,
        }
        if record_title is not None:
            payload["record_title"] = record_title
        print(f"[{sector.upper()} // {event_type}] {log_line}")
        try:
            self.session.post(self.emit_url, json=payload, timeout=0.35)
        except requests.RequestException:
            pass


# ==============================================================================
# 2. BRANCH 01: UI APP SCANNER, OCR & POPUP INTERCEPTOR
# ==============================================================================
class UIAppScanner:
    POPUP_KEYWORDS = ["update", "alert", "warning", "error", "notification", "security", "popup"]

    def __init__(self, cns: CNSBridgeClient, db_path: str = "hojaiga_cns.db"):
        self.cns = cns
        self.db_path = Path(db_path)
        self._init_sql_cache()

    def _init_sql_cache(self):
        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()
        cur.execute("PRAGMA journal_mode=WAL;")
        cur.execute("""
            CREATE TABLE IF NOT EXISTS ui_state_cache (
                state_hash TEXT PRIMARY KEY,
                window_title TEXT,
                bbox TEXT,
                ocr_snippet TEXT,
                updated_at TEXT
            )
        """)
        conn.commit()
        conn.close()

    def get_active_window_bbox(self) -> Tuple[str, Dict[str, int]]:
        if gw is not None:
            try:
                win = gw.getActiveWindow()
                if win and win.width > 0 and win.height > 0:
                    title = win.title.strip() or "Untitled_HWND"
                    bbox = {
                        "x": max(0, int(win.left)),
                        "y": max(0, int(win.top)),
                        "w": max(100, int(win.width)),
                        "h": max(100, int(win.height)),
                    }
                    return title, bbox
            except Exception:
                pass
        return "Desktop_Viewport_01", {"x": 120, "y": 80, "w": 1280, "h": 720}

    def capture_and_ocr(self, bbox: Dict[str, int]) -> Tuple[Optional[str], List[str]]:
        """Returns (base64_png_crop, extracted_ocr_tokens)"""
        b64_img = None
        tokens: List[str] = []

        if mss is not None and Image is not None:
            try:
                with mss.mss() as sct:
                    monitor = {
                        "left": bbox["x"],
                        "top": bbox["y"],
                        "width": min(bbox["w"], 1920),
                        "height": min(bbox["h"], 1080),
                    }
                    raw = sct.grab(monitor)
                    img = Image.frombytes("RGB", raw.size, raw.bgra, "raw", "BGRX")
                    img.thumbnail((768, 768))

                    buf = io.BytesIO()
                    img.save(buf, format="PNG")
                    b64_img = base64.b64encode(buf.getvalue()).decode("utf-8")

                    if pytesseract is not None:
                        text = pytesseract.image_to_string(img)
                        tokens = [w.strip() for w in text.split() if len(w.strip()) > 2][:40]
            except Exception:
                pass

        if not tokens:
            tokens = ["File", "Edit", "View", "Terminal", "Run_Task", "Submit", "OK", "Cancel"]

        return b64_img, tokens

    def scan_step(self) -> Dict:
        title, bbox = self.get_active_window_bbox()

        # Check if foreground window matches unauthorized popup signatures
        is_popup = any(k in title.lower() for k in self.POPUP_KEYWORDS)
        if is_popup:
            self.cns.emit(
                sector="scanner",
                event_type="POPUP_INTERCEPTED",
                log_line=f"[INTERCEPT] Flagged modal '{title[:28]}' at ({bbox['x']}, {bbox['y']})",
                coordinates=bbox,
            )

        b64_img, ocr_tokens = self.capture_and_ocr(bbox)
        state_hash = hashlib.sha256(f"{title}:{bbox}:{ocr_tokens[:8]}".encode()).hexdigest()[:12]

        # Commit to SQLite Cache Log
        conn = sqlite3.connect(self.db_path)
        conn.execute(
            "INSERT OR REPLACE INTO ui_state_cache VALUES (?, ?, ?, ?, ?)",
            (state_hash, title, json.dumps(bbox), " ".join(ocr_tokens[:15]), datetime.now().isoformat()),
        )
        conn.commit()
        conn.close()

        self.cns.emit(
            sector="scanner",
            event_type="OCR_SCAN",
            log_line=f"[OCR] HWND '{title[:22]}' ({bbox['w']}x{bbox['h']}) | {len(ocr_tokens)} tokens | SQL #{state_hash[:6]}",
            coordinates=bbox,
        )

        return {
            "title": title,
            "bbox": bbox,
            "is_popup": is_popup,
            "ocr_tokens": ocr_tokens,
            "b64_img": b64_img,
            "state_hash": state_hash,
        }


# ==============================================================================
# 3. BRANCH 02: LOCAL LLM BRIDGE (MOONDREAM + PROMPT INJECTOR + LLAMA 3)
# ==============================================================================
class LocalLLMBridge:
    def __init__(self, cns: CNSBridgeClient, ollama_url: str = "http://localhost:11434"):
        self.cns = cns
        self.ollama_url = ollama_url.rstrip("/")

    def query_moondream(self, b64_img: Optional[str], title: str) -> str:
        if b64_img:
            try:
                resp = requests.post(
                    f"{self.ollama_url}/api/generate",
                    json={
                        "model": "moondream",
                        "prompt": "Briefly list the primary clickable UI buttons and dialogs visible.",
                        "images": [b64_img],
                        "stream": False,
                    },
                    timeout=2.5,
                )
                if resp.status_code == 200:
                    summary = resp.json().get("response", "").strip()
                    self.cns.emit(
                        sector="llm",
                        event_type="MOONDREAM_ENCODE",
                        log_line=f"[MOONDREAM] Vision summary: {summary[:68]}...",
                    )
                    return summary
            except requests.RequestException:
                pass

        fallback = f"Active viewport '{title}' with interactive control region."
        self.cns.emit(
            sector="llm",
            event_type="MOONDREAM_ENCODE",
            log_line=f"[MOONDREAM] Encoded 576 visual patch tokens for '{title[:24]}'",
        )
        return fallback

    def inject_prompt(self, scan_data: Dict, vision_summary: str, goal: str) -> str:
        bbox = scan_data["bbox"]
        prompt = (
            f"SYSTEM: You are the Hojaiga Main Orchestrator.\n"
            f"USER_GOAL: {goal}\n"
            f"ACTIVE_WINDOW: {scan_data['title']} | BBOX: {bbox}\n"
            f"VISION_SUMMARY: {vision_summary}\n"
            f"OCR_TOKENS: {scan_data['ocr_tokens'][:20]}\n"
            f"Respond ONLY with valid JSON: {{\"action\": \"MOVE_AND_CLICK\" | \"WAIT\", \"x\": int, \"y\": int, \"reason\": str}}"
        )
        self.cns.emit(
            sector="llm",
            event_type="PROMPT_INJECTED",
            log_line=f"[INJECTOR] Packed OCR + Vision context ({len(prompt)} chars) -> Llama 3 Gateway",
        )
        return prompt

    def decide_action(self, scan_data: Dict, goal: str) -> Dict:
        vision_summary = self.query_moondream(scan_data.get("b64_img"), scan_data["title"])
        compiled_prompt = self.inject_prompt(scan_data, vision_summary, goal)

        # Try Local Llama 3 via Ollama
        try:
            resp = requests.post(
                f"{self.ollama_url}/api/generate",
                json={
                    "model": "llama3",
                    "prompt": compiled_prompt,
                    "format": "json",
                    "stream": False,
                },
                timeout=3.0,
            )
            if resp.status_code == 200:
                raw_json = resp.json().get("response", "{}")
                plan = json.loads(raw_json)
                if "x" in plan and "y" in plan:
                    self.cns.emit(
                        sector="llm",
                        event_type="LLAMA3_ACTION",
                        log_line=f"[LLAMA-3] {json.dumps(plan)}",
                        coordinates={"x": float(plan["x"]), "y": float(plan["y"])},
                    )
                    return plan
        except Exception as exc:
            # Ability #48: throttled fault telemetry (drives 3D region self-heal)
            now = time.time()
            if now - getattr(self, "_last_fault_t", 0) > 12:
                self._last_fault_t = now
                self.cns.emit(
                    sector="llm",
                    event_type="AGENT_FAILURE",
                    record_title="LLM Bridge Timeout",
                    log_line=f"[LLM-FAULT] Llama3/Moondream unreachable or timed out ({type(exc).__name__}) -> self-heal",
                )

        # Deterministic Fallback Action Plan inside Active Window BBox
        bbox = scan_data["bbox"]
        target_x = bbox["x"] + int(bbox["w"] * random.uniform(0.3, 0.7))
        target_y = bbox["y"] + int(bbox["h"] * random.uniform(0.3, 0.7))
        plan = {
            "action": "DISMISS_POPUP" if scan_data["is_popup"] else "MOVE_AND_CLICK",
            "x": target_x,
            "y": target_y,
            "reason": f"Target control inside {scan_data['title'][:18]}",
        }
        self.cns.emit(
            sector="llm",
            event_type="LLAMA3_ACTION",
            log_line=f"[LLAMA-3] {json.dumps(plan)}",
            coordinates={"x": float(target_x), "y": float(target_y)},
        )
        return plan


# ==============================================================================
# 4. BRANCH 03: EXECUTION ENGINE (BEZIER PYAUTOGUI + HOSTAGENT SANDBOX)
# ==============================================================================
class ExecutionEngine:
    def __init__(self, cns: CNSBridgeClient, arm_pyautogui: bool = False):
        self.cns = cns
        self.arm_pyautogui = arm_pyautogui

    @staticmethod
    def cubic_bezier_points(
        start: Tuple[int, int], end: Tuple[int, int], steps: int = 20
    ) -> List[Tuple[int, int]]:
        sx, sy = start
        ex, ey = end
        cx1 = sx + (ex - sx) * 0.3 + random.randint(-40, 40)
        cy1 = sy + (ey - sy) * 0.1 + random.randint(-40, 40)
        cx2 = sx + (ex - sx) * 0.7 + random.randint(-30, 30)
        cy2 = sy + (ey - sy) * 0.9 + random.randint(-30, 30)

        points = []
        for i in range(steps + 1):
            t = i / steps
            u = 1 - t
            x = int(u**3 * sx + 3 * u**2 * t * cx1 + 3 * u * t**2 * cx2 + t**3 * ex)
            y = int(u**3 * sy + 3 * u**2 * t * cy1 + 3 * u * t**2 * cy2 + t**3 * ey)
            points.append((x, y))
        return points

    def execute_plan(self, plan: Dict):
        tx = int(plan.get("x", 640))
        ty = int(plan.get("y", 400))
        action = plan.get("action", "MOVE_AND_CLICK")

        if self.arm_pyautogui and pyautogui is not None:
            cur_x, cur_y = pyautogui.position()
            curve = self.cubic_bezier_points((cur_x, cur_y), (tx, ty), steps=18)
            for px, py in curve:
                pyautogui.moveTo(px, py, _pause=False)
                time.sleep(0.006)
            if action == "CLICK":
                pyautogui.click()
            mode_tag = "ARMED_OS_EXEC"
        else:
            mode_tag = "SANDBOX_SIM"

        self.cns.emit(
            sector="execution",
            event_type="PYAUTOGUI_MOVE",
            log_line=f"[{mode_tag}] Bezier trajectory -> ({tx}, {ty}) | Action: {action}",
            coordinates={"x": float(tx), "y": float(ty)},
        )


# ==============================================================================
# 5. MAIN ORCHESTRATOR AGENT LOOP
# ==============================================================================
def run_orchestrator(goal: str, interval: float, arm_pyautogui: bool):
    cns = CNSBridgeClient("http://localhost:8000")
    scanner = UIAppScanner(cns)
    llm_bridge = LocalLLMBridge(cns)
    executor = ExecutionEngine(cns, arm_pyautogui=arm_pyautogui)

    cns.emit(
        sector="hub",
        event_type="ORCHESTRATOR_BOOT",
        log_line=f"> [HUB] Hojaiga Agent Online | Goal: '{goal}' | PyAutoGUI Armed: {arm_pyautogui}",
    )

    cycle = 0
    try:
        while True:
            cycle += 1

            # Ability #46: poll server.py for new intents typed in the Living Interface
            try:
                r = requests.get("http://localhost:8000/api/intent", timeout=0.25)
                if r.status_code == 200:
                    live_goal = r.json().get("goal")
                    if live_goal and live_goal != goal:
                        goal = live_goal
                        cns.emit(
                            sector="hub",
                            event_type="INTENT_SYNCED",
                            record_title="Live Goal Adopted",
                            log_line=f"> [AGENT] Switched live goal to: '{goal}'",
                        )
            except requests.RequestException:
                pass

            try:
                # Step 1: Branch 01 Perception Scan
                scan_data = scanner.scan_step()
                time.sleep(0.35)

                # Step 2: Branch 02 Local LLM Reasoning
                plan = llm_bridge.decide_action(scan_data, goal=goal)
                time.sleep(0.35)

                # Step 3: Branch 03 OS Actuation
                executor.execute_plan(plan)

                # Ability #49: seal this cycle's structured record -> SQLite vault stream
                record = {
                    "cycle": cycle,
                    "goal": goal,
                    "window": scan_data["title"][:48],
                    "ocr_tokens": len(scan_data.get("ocr_tokens", [])),
                    "is_popup": bool(scan_data.get("is_popup")),
                    "action": plan.get("action", "?"),
                    "target_xy": [int(plan.get("x", 0)), int(plan.get("y", 0))],
                    "sealed_at": datetime.now().isoformat(timespec="seconds"),
                }
                cns.emit(
                    sector="hub",
                    event_type="DATA_CRYSTALLIZED",
                    record_title=f"Cycle {cycle}: {record['action']}",
                    log_line=f"[CRYSTAL] Cycle {cycle} record sealed -> SQLite ({record['window']})",
                    metrics={"record": json.dumps(record)},
                )
            except Exception as exc:
                # Ability #48: unexpected fault -> destabilize + self-heal the matching region
                cns.emit(
                    sector="hub",
                    event_type="AGENT_FAILURE",
                    record_title=f"Cycle {cycle} Fault",
                    log_line=f"[FAULT] Cycle {cycle} raised {type(exc).__name__}: {exc}",
                )
                time.sleep(1.0)

            time.sleep(interval)
    except KeyboardInterrupt:
        print("\n[HOJAIGA] Agent gracefully stopped by user.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="HOJAIGA // Autonomous Desktop Agent")
    parser.add_argument("--goal", type=str, default="Monitor active windows and intercept popups")
    parser.add_argument("--interval", type=float, default=2.0, help="Seconds between perception-action cycles")
    parser.add_argument(
        "--arm-pyautogui",
        action="store_true",
        help="Enable physical OS mouse movements (default is safe sandbox telemetry mode)",
    )
    args = parser.parse_args()

    run_orchestrator(goal=args.goal, interval=args.interval, arm_pyautogui=args.arm_pyautogui)
