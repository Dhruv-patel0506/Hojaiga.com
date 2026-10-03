"""
organ_ml — Single ML Organ for Hojaiga Self-Learning System

One organ. Does everything:
  - Records observations in 7 training bins
  - Trains patterns on-demand (event-driven, no background loops)
  - Visual Engine: captures screenshots, annotates, learns to find elements
  - Provides inference to other organs
  - Grows smarter with every task

WHAT IT LEARNS:
  - What elements LOOK like (visual descriptions)
  - Which tab/group they live in
  - How tasks compile into steps
  - How tasks flow between agents
  - What popup buttons to click
  - Button name mappings (e.g., "1" -> "One" for Calculator)
  - Click failures (so next time it tries differently)
  - Cached UI layouts (skip re-scanning known apps)

Usage:
  from organ_ml import ml
  ml.feed_action("Word", "Bold", "click", True, visual_hint="B icon", tab="Home", group_location="Font")
  ml.predict_click("Word", "Bold")  -> {"visual": "B icon", "tab": "Home", "group_location": "Font"}
  ml.start()  # initializes (no background loops)

  from organ_ml import memory
  memory.save_button_name_mapping("calculator", "1", "One")
  memory.lookup_button_name("calculator", "1")  -> "One"
  memory.log_click_failure("calculator", "Nine", "not found", "UIA")
  memory.get_cached_layout("calculator")  -> [...]
"""

import hashlib
import json
import logging
import os
import re
import sqlite3
import time
import threading
from pathlib import Path

logger = logging.getLogger("organ_ml")

DB_PATH = Path(r"D:\new_automation\storage\hojaiga_knowledge.sqlite")
LOG_DIR = Path(r"D:\new_automation\var\hojaiga\logs")
SCREENSHOT_DIR = Path(r"D:\new_automation\var\hojaiga\screenshots")
SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)

# ── Bin definitions ────────────────────────────────────────────────────────

BINS = {
    "brain_compilation": {
        "fields": ["task_text", "compiled_steps", "model_used", "latency_ms", "success"],
        "pattern_type": "brain_compile",
        "context_keys": ["task_text"],
        "action_keys": ["steps", "model"],
    },
    "task_hierarchy": {
        "fields": ["task_id", "from_agent", "to_agent", "action", "response", "latency_ms"],
        "pattern_type": "task_flow",
        "context_keys": ["from_agent", "to_agent", "action"],
        "action_keys": ["response"],
    },
    "action_execution": {
        "fields": ["app_name", "element_name", "action_type", "success", "visual_hint", "tab", "group_location"],
        "pattern_type": "ui_action",
        "context_keys": ["app_name", "element_name"],
        "action_keys": ["visual_hint", "tab", "group_location", "action_type"],
    },
    "ui_detection": {
        "fields": ["app_name", "screenshot_path", "elements_json", "source"],
        "pattern_type": "ui_visual",
        "context_keys": ["app_name", "element_name"],
        "action_keys": ["visual_description", "tab", "group_location", "element_type"],
    },
    "popup_resolution": {
        "fields": ["popup_title", "buttons_json", "chosen_button", "success", "method"],
        "pattern_type": "popup_handle",
        "context_keys": ["popup_title", "buttons"],
        "action_keys": ["chosen", "method"],
    },
    "vision_understanding": {
        "fields": ["screenshot_path", "vlm_description", "actual_content", "accuracy_score"],
        "pattern_type": "vision_accuracy",
        "context_keys": ["description_hash"],
        "action_keys": ["accuracy", "actual"],
    },
    "flow_optimization": {
        "fields": ["task_text", "total_steps", "total_time_ms", "success", "bottleneck"],
        "pattern_type": "flow_optimize",
        "context_keys": ["task_type"],
        "action_keys": ["steps", "time_ms", "bottleneck"],
    },
}


# ═══════════════════════════════════════════════════════════════════════════
# VISUAL ENGINE — How ML sees and learns from screenshots
# ═══════════════════════════════════════════════════════════════════════════

class VisualEngine:
    """Takes screenshots, annotates them, learns to find elements visually."""

    def __init__(self, conn):
        self._conn = conn
        self._init_db()

    def _init_db(self):
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS ml_screenshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp REAL, app_name TEXT, window_title TEXT,
                screenshot_path TEXT, width INTEGER, height INTEGER,
                annotations_json TEXT, vlm_description TEXT
            )
        """)
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS ml_visual_templates (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                app_name TEXT, element_name TEXT,
                region_x INTEGER, region_y INTEGER,
                region_w INTEGER, region_h INTEGER,
                visual_features TEXT,
                times_matched INTEGER DEFAULT 0,
                times_missed INTEGER DEFAULT 0,
                last_used REAL
            )
        """)
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS ml_spatial_relations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                app_name TEXT, element_a TEXT, element_b TEXT,
                relative_x REAL, relative_y REAL,
                times_seen INTEGER DEFAULT 1, last_seen REAL
            )
        """)
        self._conn.commit()

    def capture_screenshot(self, app_name="", window_title=""):
        """Capture current screen and store for learning."""
        try:
            import pyautogui
            screenshot = pyautogui.screenshot()
            ts = int(time.time() * 1000)
            filepath = SCREENSHOT_DIR / f"{app_name}_{ts}.png"
            screenshot.save(str(filepath))
            self._conn.execute(
                "INSERT INTO ml_screenshots (timestamp,app_name,window_title,screenshot_path,width,height) VALUES (?,?,?,?,?,?)",
                (time.time(), app_name, window_title, str(filepath), screenshot.width, screenshot.height),
            )
            self._conn.commit()
            return str(filepath)
        except Exception as e:
            logger.warning("Screenshot failed: %s", e)
            return None

    def annotate_screenshot(self, screenshot_path, vlm_description, elements_found):
        """Annotate screenshot with VLM output. elements_found: [{"name","x","y","w","h","visual","tab","group_location"}]"""
        self._conn.execute(
            "UPDATE ml_screenshots SET annotations_json=?, vlm_description=? WHERE screenshot_path=?",
            (json.dumps(elements_found), vlm_description, screenshot_path),
        )
        for el in elements_found:
            self._conn.execute(
                "INSERT INTO ml_visual_templates (app_name,element_name,region_x,region_y,region_w,region_h,visual_features,last_used) VALUES (?,?,?,?,?,?,?,?)",
                (el.get("app", ""), el.get("name", ""), el.get("x", 0), el.get("y", 0),
                 el.get("w", 0), el.get("h", 0), el.get("visual", ""), time.time()),
            )
        for i, a in enumerate(elements_found):
            for b in elements_found[i+1:]:
                rx = (b.get("x", 0) - a.get("x", 0)) / max(a.get("w", 1), 1)
                ry = (b.get("y", 0) - a.get("y", 0)) / max(a.get("h", 1), 1)
                self._conn.execute(
                    "INSERT INTO ml_spatial_relations (app_name,element_a,element_b,relative_x,relative_y,last_seen) VALUES (?,?,?,?,?,?)",
                    (a.get("app", ""), a.get("name", ""), b.get("name", ""), str(rx), str(ry), time.time()),
                )
        self._conn.commit()

    def find_element(self, app_name, element_name):
        """Find what an element looks like and where it roughly is."""
        row = self._conn.execute(
            "SELECT region_x,region_y,region_w,region_h,visual_features,times_matched,times_missed FROM ml_visual_templates WHERE app_name=? AND element_name=? ORDER BY times_matched DESC LIMIT 1",
            (app_name, element_name),
        ).fetchone()
        if row:
            return {"region_x": row[0], "region_y": row[1], "region_w": row[2], "region_h": row[3],
                    "visual_hint": row[4], "confidence": row[5] / max(row[5] + row[6], 1), "method": "template"}
        return None

    def confirm_found(self, app_name, element_name):
        self._conn.execute("UPDATE ml_visual_templates SET times_matched=times_matched+1, last_used=? WHERE app_name=? AND element_name=?",
                          (time.time(), app_name, element_name))
        self._conn.commit()

    def confirm_missed(self, app_name, element_name):
        self._conn.execute("UPDATE ml_visual_templates SET times_missed=times_missed+1 WHERE app_name=? AND element_name=?",
                          (app_name, element_name))
        self._conn.commit()

    def get_spatial_hint(self, app_name, known, target):
        row = self._conn.execute(
            "SELECT relative_x,relative_y FROM ml_spatial_relations WHERE app_name=? AND element_a=? AND element_b=?",
            (app_name, known, target),
        ).fetchone()
        return {"rel_x": float(row[0]), "rel_y": float(row[1])} if row else None

    def get_stats(self):
        s = self._conn.execute("SELECT COUNT(*) FROM ml_screenshots").fetchone()[0]
        t = self._conn.execute("SELECT COUNT(*) FROM ml_visual_templates").fetchone()[0]
        r = self._conn.execute("SELECT COUNT(*) FROM ml_spatial_relations").fetchone()[0]
        return {"screenshots": s, "templates": t, "spatial_relations": r}


# ═══════════════════════════════════════════════════════════════════════════
# MAIN ML ORGAN
# ═══════════════════════════════════════════════════════════════════════════

class OrganML:
    def __init__(self):
        self._conn = None
        self._lock = threading.Lock()
        self._threads = []
        self._running = False
        self._init_db()
        self.visual = VisualEngine(self._conn)

    def _get_conn(self):
        if self._conn is None:
            self._conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
        return self._conn

    def _init_db(self):
        conn = self._get_conn()
        for bin_name, spec in BINS.items():
            cols = ", ".join([f"{f} TEXT" for f in spec["fields"]])
            conn.execute(f"CREATE TABLE IF NOT EXISTS ml_{bin_name} (id INTEGER PRIMARY KEY AUTOINCREMENT, timestamp REAL, session_id TEXT, {cols}, reward REAL DEFAULT 0, trained INTEGER DEFAULT 0)")
        conn.execute("CREATE TABLE IF NOT EXISTS ml_training_log (id INTEGER PRIMARY KEY AUTOINCREMENT, timestamp REAL, bin_name TEXT, samples_trained INTEGER, loss REAL, accuracy REAL, model_version TEXT, notes TEXT)")
        conn.execute("CREATE TABLE IF NOT EXISTS ml_patterns (id INTEGER PRIMARY KEY AUTOINCREMENT, pattern_type TEXT, context_hash TEXT, action_json TEXT, confidence REAL, times_used INTEGER DEFAULT 0, times_succeeded INTEGER DEFAULT 0, last_updated REAL)")
        conn.execute("CREATE TABLE IF NOT EXISTS ml_visual_knowledge (id INTEGER PRIMARY KEY AUTOINCREMENT, app_name TEXT, element_name TEXT, visual_description TEXT, tab_location TEXT, group_location TEXT, example_screenshot TEXT, times_seen INTEGER DEFAULT 1, times_correctly_found INTEGER DEFAULT 0, last_seen REAL)")
        conn.commit()

    # ── Recording ──────────────────────────────────────────────────────────

    def _record(self, bin_name, session_id, **kwargs):
        if bin_name not in BINS:
            return
        spec = BINS[bin_name]
        with self._lock:
            conn = self._get_conn()
            fields = spec["fields"]
            cols = ", ".join(["timestamp", "session_id"] + fields)
            phs = ", ".join(["?"] * (2 + len(fields)))
            vals = [time.time(), session_id] + [kwargs.get(f, "") for f in fields]
            conn.execute(f"INSERT INTO ml_{bin_name} ({cols}) VALUES ({phs})", vals)
            conn.commit()

    def _learn(self, pattern_type, context, action, confidence=0.5):
        ctx_hash = hashlib.md5(json.dumps(context, sort_keys=True, default=str).encode()).hexdigest()
        action_json = json.dumps(action, default=str)
        with self._lock:
            conn = self._get_conn()
            existing = conn.execute("SELECT id, confidence FROM ml_patterns WHERE pattern_type=? AND context_hash=?", (pattern_type, ctx_hash)).fetchone()
            if existing:
                conn.execute("UPDATE ml_patterns SET confidence=MIN(0.99,?+0.05), times_used=times_used+1, last_updated=? WHERE id=?", (existing[1], time.time(), existing[0]))
            else:
                conn.execute("INSERT INTO ml_patterns (pattern_type,context_hash,action_json,confidence,times_used,last_updated) VALUES (?,?,?, ?,1,?)", (pattern_type, ctx_hash, action_json, confidence, time.time()))
            conn.commit()

    def _strengthen(self, pattern_type, context):
        ctx_hash = hashlib.md5(json.dumps(context, sort_keys=True, default=str).encode()).hexdigest()
        with self._lock:
            self._get_conn().execute("UPDATE ml_patterns SET times_succeeded=times_succeeded+1, confidence=MIN(0.99,confidence+0.03) WHERE pattern_type=? AND context_hash=?", (pattern_type, ctx_hash))
            self._get_conn().commit()

    def _predict(self, pattern_type, context):
        ctx_hash = hashlib.md5(json.dumps(context, sort_keys=True, default=str).encode()).hexdigest()
        row = self._get_conn().execute("SELECT action_json, confidence FROM ml_patterns WHERE pattern_type=? AND context_hash=? AND confidence>0.3 ORDER BY confidence DESC LIMIT 1", (pattern_type, ctx_hash)).fetchone()
        return {"action": json.loads(row[0]), "confidence": row[1]} if row else None

    # ── Visual knowledge ───────────────────────────────────────────────────

    def learn_visual(self, app_name, element_name, visual_description, tab="", group_location="", screenshot=""):
        with self._lock:
            conn = self._get_conn()
            existing = conn.execute("SELECT id FROM ml_visual_knowledge WHERE app_name=? AND element_name=?", (app_name, element_name)).fetchone()
            if existing:
                conn.execute("UPDATE ml_visual_knowledge SET times_seen=times_seen+1, visual_description=?, last_seen=? WHERE id=?", (visual_description, time.time(), existing[0]))
            else:
                conn.execute("INSERT INTO ml_visual_knowledge (app_name,element_name,visual_description,tab_location,group_location,example_screenshot,times_seen,last_seen) VALUES (?,?,?,?,?,?,1,?)", (app_name, element_name, visual_description, tab, group_location, screenshot, time.time()))
            conn.commit()

    def find_visual(self, app_name, element_name):
        row = self._get_conn().execute("SELECT visual_description,tab_location,group_location,times_correctly_found,times_seen FROM ml_visual_knowledge WHERE app_name=? AND element_name=? ORDER BY times_correctly_found DESC LIMIT 1", (app_name, element_name)).fetchone()
        if row:
            return {"visual": row[0], "tab": row[1], "group_location": row[2], "confidence": row[3] / max(row[4], 1)}
        return None

    def confirm_visual_found(self, app_name, element_name):
        with self._lock:
            self._get_conn().execute("UPDATE ml_visual_knowledge SET times_correctly_found=times_correctly_found+1 WHERE app_name=? AND element_name=?", (app_name, element_name))
            self._get_conn().commit()

    # ── Feed methods (other organs call these) ─────────────────────────────

    def feed_brain_compilation(self, task_text, compiled_steps, model_used, latency_ms, success, session_id="default"):
        self._record("brain_compilation", session_id, task_text=task_text, compiled_steps=json.dumps(compiled_steps), model_used=model_used, latency_ms=str(latency_ms), success=str(success))
        self._learn("brain_compile", {"task_text": task_text[:200]}, {"steps": compiled_steps, "model": model_used}, 0.7 if success else 0.3)

    def feed_task_flow(self, task_id, from_agent, to_agent, action, response, latency_ms, session_id="default"):
        self._record("task_hierarchy", session_id, task_id=task_id, from_agent=from_agent, to_agent=to_agent, action=action, response=response[:500], latency_ms=str(latency_ms))
        self._learn("task_flow", {"from": from_agent, "to": to_agent, "action": action}, {"response": response[:200]}, 0.6)

    def feed_action(self, app_name, element_name, action_type, success, visual_hint="", tab="", group_location="", session_id="default"):
        self._record("action_execution", session_id, app_name=app_name, element_name=element_name, action_type=action_type, success=str(success), visual_hint=visual_hint, tab=tab, group_location=group_location)
        self._learn("ui_action", {"app": app_name, "element": element_name}, {"visual": visual_hint, "tab": tab, "group": group_location, "action": action_type}, 0.8 if success else 0.2)
        if success and visual_hint:
            self.learn_visual(app_name, element_name, visual_hint, tab, group_location)
            self._strengthen("ui_action", {"app": app_name, "element": element_name})
        # Event-driven training: train on new data immediately
        self.train_on_new_data()

    def feed_ui_detection(self, app_name, screenshot_path, elements, source="eye", session_id="default"):
        self._record("ui_detection", session_id, app_name=app_name, screenshot_path=screenshot_path, elements_json=json.dumps(elements), source=source)
        for el in elements:
            self.learn_visual(app_name, el.get("name", ""), el.get("visual_description", el.get("name", "")), el.get("tab", ""), el.get("group_location", ""))
            self._learn("ui_visual", {"app": app_name, "element_name": el.get("name", "")}, {"visual_description": el.get("visual_description", ""), "tab": el.get("tab", ""), "group_location": el.get("group_location", ""), "element_type": el.get("type", "")}, 0.7)

    def feed_popup(self, popup_title, buttons, chosen_button, success, method="gatekeeper", session_id="default"):
        self._record("popup_resolution", session_id, popup_title=popup_title, buttons_json=json.dumps(buttons), chosen_button=chosen_button, success=str(success), method=method)
        self._learn("popup_handle", {"title": popup_title, "buttons": sorted(buttons)}, {"chosen": chosen_button, "method": method}, 0.8 if success else 0.3)
        if success:
            self._strengthen("popup_handle", {"title": popup_title, "buttons": sorted(buttons)})

    def feed_vision(self, screenshot_path, vlm_description, actual_content="", accuracy_score=0.0, session_id="default"):
        self._record("vision_understanding", session_id, screenshot_path=screenshot_path, vlm_description=vlm_description[:1000], actual_content=actual_content[:1000], accuracy_score=str(accuracy_score))

    def feed_flow(self, task_text, total_steps, total_time_ms, success, bottleneck="", session_id="default"):
        self._record("flow_optimization", session_id, task_text=task_text[:500], total_steps=str(total_steps), total_time_ms=str(total_time_ms), success=str(success), bottleneck=bottleneck)

    # ── Predict methods (organs ask ML) ────────────────────────────────────

    def predict_compilation(self, task_text):
        r = self._predict("brain_compile", {"task_text": task_text[:200]})
        return r["action"] if r and r["confidence"] > 0.5 else None

    def predict_click(self, app_name, element_name):
        """Returns WHAT to look for (visual hint, tab, group) — NOT coordinates."""
        visual = self.find_visual(app_name, element_name)
        if visual and visual["confidence"] > 0.3:
            return visual
        template = self.visual.find_element(app_name, element_name)
        if template:
            return template
        r = self._predict("ui_action", {"app": app_name, "element": element_name})
        if r and r["confidence"] > 0.5:
            return r["action"]
        try:
            from database_manager import DatabaseManager
            elem = DatabaseManager().lookup_ui_element(element_name, app_name)
            if elem:
                return {"tab": elem["tab"], "group_location": elem["group"], "visual": element_name, "confidence": 0.5}
        except Exception:
            pass
        return None

    def predict_popup(self, title, buttons):
        r = self._predict("popup_handle", {"title": title, "buttons": sorted(buttons)})
        return r["action"]["chosen"] if r and r["confidence"] > 0.5 else None

    def predict_flow(self, from_agent, to_agent, action):
        r = self._predict("task_flow", {"from": from_agent, "to": to_agent, "action": action})
        return r["action"] if r and r["confidence"] > 0.5 else None

    def predict_optimization(self, task_text):
        r = self._predict("flow_optimize", {"task_type": task_text[:100]})
        return r["action"] if r and r["confidence"] > 0.5 else None

    # ── Training (event-driven, not background loops) ──────────────────────

    def _train_bin(self, bin_name, limit=50):
        conn = self._get_conn()
        rows = conn.execute(f"SELECT * FROM ml_{bin_name} WHERE trained=0 ORDER BY timestamp DESC LIMIT ?", (limit,)).fetchall()
        if not rows:
            return {"trained": 0}
        spec = BINS[bin_name]
        patterns = 0
        for row in rows:
            try:
                context, action = {}, {}
                for i, field in enumerate(spec["fields"]):
                    val = row[3 + i]
                    if field in spec.get("context_keys", []):
                        context[field] = val
                    if field in spec.get("action_keys", []):
                        action[field] = val
                if context:
                    self._learn(spec["pattern_type"], context, action, 0.5)
                    patterns += 1
            except Exception as e:
                logger.warning("Train error %s: %s", bin_name, e)
        ids = [r[0] for r in rows]
        conn.execute(f"UPDATE ml_{bin_name} SET trained=1 WHERE id IN ({','.join(['?']*len(ids))})", ids)
        conn.execute("INSERT INTO ml_training_log (timestamp,bin_name,samples_trained,loss,accuracy,model_version,notes) VALUES (?,?,?,?,?,?,?)",
                     (time.time(), bin_name, len(rows), 0.0, patterns / max(len(rows), 1), f"v{int(time.time())}", f"{patterns} patterns from {len(rows)} samples"))
        conn.commit()
        return {"trained": len(rows), "patterns": patterns}

    def train_on_new_data(self):
        """Train all bins that have untrained data. Called after feed_* methods, not on a timer."""
        results = {}
        for bin_name in BINS:
            try:
                r = self._train_bin(bin_name, limit=200)
                if r["trained"] > 0:
                    results[bin_name] = r
            except Exception as e:
                logger.warning("[%s] train_on_new_data error: %s", bin_name, e)
        if results:
            logger.info("[ML] Trained on new data: %s", results)
        return results

    def parse_logs(self):
        if not LOG_DIR.exists():
            return
        for f in sorted(LOG_DIR.glob("*.log"), key=os.path.getmtime, reverse=True)[:5]:
            try:
                content = f.read_text(encoding="utf-8", errors="ignore")
                for m in re.finditer(r"Brain.*compiled.*task.*?(\d+).*?steps", content, re.IGNORECASE):
                    self.feed_brain_compilation("parsed_from_log", ["parsed"], "unknown", 0, True, f"log_{f.name}")
                for m in re.finditer(r"(Clicked|Typed|Pressed).*?(\d+),(\d+).*?(success|fail)", content, re.IGNORECASE):
                    self.feed_action("unknown", m.group(1), m.group(1).lower(), "success" in m.group(4).lower(), session_id=f"log_{f.name}")
            except Exception:
                pass

    # ── Control ────────────────────────────────────────────────────────────

    def start(self, interval=60.0):
        if self._running:
            return
        self._running = True
        # Train once on startup to process any backlog
        self.train_on_new_data()
        self.parse_logs()
        logger.info("[OrganML] Started — event-driven training (no background loops)")

    def stop(self):
        self._running = False
        for t in self._threads:
            t.join(timeout=5)
        self._threads.clear()

    def train_now(self):
        return {bin_name: self._train_bin(bin_name, limit=200) for bin_name in BINS}

    def status(self):
        conn = self._get_conn()
        stats = {}
        for bin_name in BINS:
            total = conn.execute(f"SELECT COUNT(*) FROM ml_{bin_name}").fetchone()[0]
            untrained = conn.execute(f"SELECT COUNT(*) FROM ml_{bin_name} WHERE trained=0").fetchone()[0]
            stats[bin_name] = {"total": total, "untrained": untrained}
        stats["_patterns"] = conn.execute("SELECT COUNT(*) FROM ml_patterns").fetchone()[0]
        stats["_visual_knowledge"] = conn.execute("SELECT COUNT(*) FROM ml_visual_knowledge").fetchone()[0]
        stats["_visual_engine"] = self.visual.get_stats()
        return stats

    def print_status(self):
        print("\n=== OrganML Status ===")
        for k, v in self.status().items():
            print(f"  {k}: {v}")
        print()


# ═══════════════════════════════════════════════════════════════════════════
# SINGLETON
# ═══════════════════════════════════════════════════════════════════════════

ml = OrganML()


# ═══════════════════════════════════════════════════════════════════════════
# SELF-LEARNING MEMORY — Intent, Visual Spatial, and Reflection
# ═══════════════════════════════════════════════════════════════════════════

class SystemMemory:
    """Self-learning memory layer tracking visuals, intent maps, and run history.
    Integrated into organ_ml to keep all ML/learning in one file."""
    
    _instance = None
    _lock = threading.Lock()
    
    @classmethod
    def get_instance(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance
    
    def __init__(self, base_dir=r"D:\new_automation\memory"):
        self.base_dir = base_dir
        self.db_path = os.path.join(base_dir, "system_memory.db")
        os.makedirs(os.path.join(base_dir, "app_snapshots"), exist_ok=True)
        self._init_database()
        logger.info("[SystemMemory] Initialized: %s", self.db_path)
    
    def _init_database(self):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS intent_memory (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    raw_user_input TEXT,
                    compiled_steps TEXT,
                    execution_status TEXT,
                    duration_seconds REAL,
                    model_used TEXT,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS visual_spatial_memory (
                    app_name TEXT,
                    element_name TEXT,
                    last_known_bbox TEXT,
                    center_x INTEGER,
                    center_y INTEGER,
                    confidence_score REAL,
                    snapshot_path TEXT,
                    access_count INTEGER DEFAULT 1,
                    last_accessed DATETIME DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (app_name, element_name)
                )
            ''')
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS execution_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_id TEXT,
                    raw_input TEXT,
                    steps_taken TEXT,
                    errors_encountered TEXT,
                    final_status TEXT,
                    model_used TEXT,
                    duration_seconds REAL,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS app_layout_cache (
                    app_name TEXT,
                    layout_hash TEXT,
                    element_count INTEGER,
                    last_scan_time DATETIME,
                    layout_data TEXT,
                    PRIMARY KEY (app_name)
                )
            ''')
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS click_failures (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    app_name TEXT,
                    element_name TEXT,
                    error_reason TEXT,
                    method_tried TEXT,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS button_name_map (
                    app_name TEXT,
                    user_input TEXT,
                    correct_button_name TEXT,
                    times_used INTEGER DEFAULT 1,
                    last_used DATETIME DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (app_name, user_input)
                )
            ''')
            conn.commit()
    
    def learn_intent(self, raw_input, steps, success, duration=0.0, model=""):
        status = "SUCCESS" if success else "FAILED"
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT INTO intent_memory (raw_user_input, compiled_steps, execution_status, duration_seconds, model_used) VALUES (?, ?, ?, ?, ?)",
                (raw_input, json.dumps(steps), status, duration, model)
            )
            conn.commit()
        logger.info("[Memory] Learned: %s -> %s", raw_input[:50], status)
    
    def save_button(self, app_name, element_name, bbox, center=(0, 0), screenshot=None):
        filepath = ""
        if screenshot and bbox and len(bbox) == 4:
            try:
                import cv2
                x1, y1, x2, y2 = map(int, bbox)
                if x2 > x1 and y2 > y1:
                    cropped = screenshot[y1:y2, x1:x2]
                    filename = f"{app_name}_{element_name}.png".replace(" ", "_").replace("/", "_")
                    filepath = os.path.join(self.base_dir, "app_snapshots", filename)
                    cv2.imwrite(filepath, cropped)
            except Exception:
                filepath = ""
        
        with sqlite3.connect(self.db_path) as conn:
            conn.execute('''
                INSERT OR REPLACE INTO visual_spatial_memory 
                (app_name, element_name, last_known_bbox, center_x, center_y, 
                 confidence_score, snapshot_path, access_count, last_accessed)
                VALUES (?, ?, ?, ?, ?, ?, ?, 
                        COALESCE((SELECT access_count + 1 FROM visual_spatial_memory 
                                  WHERE app_name = ? AND element_name = ?), 1),
                        CURRENT_TIMESTAMP)
            ''', (app_name, element_name, json.dumps(bbox), 
                  center[0], center[1], 1.0, filepath,
                  app_name, element_name))
            conn.commit()
    
    def lookup_button(self, app_name, element_name):
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT last_known_bbox, center_x, center_y, confidence_score, snapshot_path FROM visual_spatial_memory WHERE app_name = ? AND element_name = ?",
                (app_name, element_name)
            ).fetchone()
            if row:
                return {
                    "bbox": json.loads(row[0]) if row[0] else [],
                    "center": (row[1], row[2]),
                    "confidence": row[3],
                    "snapshot": row[4]
                }
        return None
    
    def save_layout(self, app_name, elements, layout_hash=""):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute('''
                INSERT OR REPLACE INTO app_layout_cache 
                (app_name, layout_hash, element_count, last_scan_time, layout_data)
                VALUES (?, ?, ?, CURRENT_TIMESTAMP, ?)
            ''', (app_name, layout_hash, len(elements), json.dumps(elements)))
            conn.commit()
    
    def get_cached_layout(self, app_name, max_age_seconds=300):
        """Return cached layout if fresh enough, else None."""
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT layout_data, last_scan_time FROM app_layout_cache WHERE app_name = ?",
                (app_name,)
            ).fetchone()
            if row:
                try:
                    from datetime import datetime
                    scan_time = datetime.fromisoformat(row[1])
                    age = (datetime.now() - scan_time).total_seconds()
                    if age < max_age_seconds:
                        return json.loads(row[0])
                except Exception:
                    pass
        return None
    
    def log_click_failure(self, app_name, element_name, error_reason, method_tried="UIA"):
        """Record a click failure so we can learn from it."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT INTO click_failures (app_name, element_name, error_reason, method_tried) VALUES (?, ?, ?, ?)",
                (app_name, element_name, error_reason, method_tried)
            )
            conn.commit()
        logger.info("[Memory] Logged click failure: %s/%s: %s", app_name, element_name, error_reason)
    
    def get_click_failure_count(self, app_name, element_name):
        """How many times has this button failed?"""
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT COUNT(*) FROM click_failures WHERE app_name = ? AND element_name = ?",
                (app_name, element_name)
            ).fetchone()
            return row[0] if row else 0
    
    def save_button_name_mapping(self, app_name, user_input, correct_name):
        """Remember that when user says '1' for Calculator, the correct button is 'One'."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute('''
                INSERT OR REPLACE INTO button_name_map 
                (app_name, user_input, correct_button_name, times_used, last_used)
                VALUES (?, ?, ?, 
                        COALESCE((SELECT times_used + 1 FROM button_name_map 
                                  WHERE app_name = ? AND user_input = ?), 1),
                        CURRENT_TIMESTAMP)
            ''', (app_name, user_input.lower(), correct_name, app_name, user_input.lower()))
            conn.commit()
        logger.info("[Memory] Button name map: %s/%s -> %s", app_name, user_input, correct_name)
    
    def lookup_button_name(self, app_name, user_input):
        """Given user says '1' for Calculator, return 'One'."""
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT correct_button_name FROM button_name_map WHERE app_name = ? AND user_input = ?",
                (app_name, user_input.lower())
            ).fetchone()
            return row[0] if row else None
    
    def get_all_button_names(self, app_name):
        """Return all known button name mappings for an app."""
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(
                "SELECT user_input, correct_button_name FROM button_name_map WHERE app_name = ?",
                (app_name,)
            ).fetchall()
            return {row[0]: row[1] for row in rows}
    
    def log_execution(self, task_id, raw_input, steps, errors, status, model="", duration=0.0):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT INTO execution_log (task_id, raw_input, steps_taken, errors_encountered, final_status, model_used, duration_seconds) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (task_id, raw_input, json.dumps(steps), json.dumps(errors), status, model, duration)
            )
            conn.commit()
    
    def get_stats(self):
        with sqlite3.connect(self.db_path) as conn:
            c = conn.cursor()
            c.execute("SELECT COUNT(*) FROM intent_memory")
            total = c.fetchone()[0]
            c.execute("SELECT COUNT(*) FROM intent_memory WHERE execution_status = 'SUCCESS'")
            success = c.fetchone()[0]
            c.execute("SELECT COUNT(*) FROM visual_spatial_memory")
            buttons = c.fetchone()[0]
            c.execute("SELECT COUNT(DISTINCT app_name) FROM visual_spatial_memory")
            apps = c.fetchone()[0]
            c.execute("SELECT COUNT(*) FROM click_failures")
            failures = c.fetchone()[0]
            c.execute("SELECT COUNT(*) FROM button_name_map")
            name_maps = c.fetchone()[0]
            return {
                "intents": total,
                "success_rate": f"{(success/total*100):.1f}%" if total > 0 else "0%",
                "buttons": buttons,
                "apps": apps,
                "click_failures": failures,
                "button_name_mappings": name_maps,
            }


# Global memory instance
memory = SystemMemory.get_instance()


def self_correcting_reflect(raw_command, log_text, task_id=""):
    """Detects false success declarations and learns from them."""
    log_lower = log_text.lower()
    
    # Detect early success: "final answer" or "success" without any click/type action
    has_action = any(kw in log_lower for kw in ["clicked", "typed", "pressed", "invoke", "legacy", "selectionitem"])
    has_final = any(kw in log_lower for kw in ["final answer", "task completed successfully", "success"])
    
    if has_final and not has_action:
        logger.warning("[Reflection] Early success declaration for: %s", raw_command[:50])
        memory.learn_intent(raw_command, ["failed_early"], success=False)
        os.environ["HOJAIGA_FORCE_PRECISION"] = "TRUE"
        return True
    
    memory.learn_intent(raw_command, ["completed"], success=True)
    return False


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    if "--status" in __import__("sys").argv:
        ml.print_status()
    elif "--train" in __import__("sys").argv:
        print("Training results:", ml.train_now())
    elif "--memory" in __import__("sys").argv:
        print("Memory stats:", memory.get_stats())
    else:
        ml.start()
        ml.print_status()
