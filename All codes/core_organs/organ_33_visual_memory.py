"""
Organ 33 — Visual UI Memory
Hojaiga Automation OS

Authority: Constitution -> LawBook -> Diagrams -> Legacy Guide -> PolicyManual
           -> MasterArchitectureBlueprint -> Organ_Specification

Responsibility: Builds persistent visual memory of application UIs through
repeated scanning. The system learns what apps LOOK like, remembers element
positions and visual descriptions, and eventually recognizes known UIs on
sight — skipping deep scanning for apps that have been thoroughly trained.

Training Gate: Visual memory lookup is ONLY used after rigorous training:
  - N confirmed scans (default 5)
  - Success rate >= 75% (elements found / scanned)
  - Only THEN is the app marked "ready" for recognition-based automation

Flow:
  1. First Contact: Deep scan (organ_30) + screenshot (organ_31) + DOM tree (organ_19)
  2. Store snapshot: element positions, visual description, UI state hash
  3. Build element profiles: track each element across scans, compute confidence
  4. Training gate: update scan count + success rate, check if gate opens
  5. Recognition: on subsequent encounters, match current screen against memory
  6. Drift detection: if UI changed significantly, trigger re-scan
"""

import hashlib
import json
import logging
import os
import sys
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

if r"D:\new_automation\All codes" not in sys.path:
    sys.path.insert(0, r"D:\new_automation\All codes")

try:
    from core_organs.database_manager import DatabaseManager
except ImportError:
    from database_manager import DatabaseManager

logger = logging.getLogger("hojaiga.organ33.visual_memory")

SCREENSHOT_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "var", "hojaiga", "visual_memory", "screenshots"
)
os.makedirs(SCREENSHOT_DIR, exist_ok=True)


# ═══════════════════════════════════════════════════════════════════════════
# DATA STRUCTURES
# ═══════════════════════════════════════════════════════════════════════════

@dataclass
class VisualSnapshot:
    """One encounter with an app's UI."""
    app_name: str
    window_title: str
    scan_number: int
    screenshot_path: str
    ui_state_hash: str
    element_count: int
    scan_mode: str  # "first_contact", "training", "recognition", "drift_check"
    vlm_description: str = ""
    elements: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self):
        return {
            "app_name": self.app_name,
            "window_title": self.window_title,
            "scan_number": self.scan_number,
            "screenshot_path": self.screenshot_path,
            "ui_state_hash": self.ui_state_hash,
            "element_count": self.element_count,
            "scan_mode": self.scan_mode,
            "vlm_description": self.vlm_description,
            "element_count_stored": len(self.elements),
        }


@dataclass
class ElementProfile:
    """Tracked identity of a UI element across multiple scans."""
    app_name: str
    element_name: str
    element_type: str
    control_type: str
    visual_description: str
    region: Tuple[int, int, int, int]  # x, y, w, h
    tab_location: str
    group_location: str
    spatial_context: str = ""
    times_scanned: int = 1
    times_found: int = 0
    confidence: float = 0.0

    def to_dict(self):
        return {
            "app_name": self.app_name,
            "element_name": self.element_name,
            "element_type": self.element_type,
            "control_type": self.control_type,
            "visual_description": self.visual_description,
            "region": {"x": self.region[0], "y": self.region[1],
                       "w": self.region[2], "h": self.region[3]},
            "tab_location": self.tab_location,
            "group_location": self.group_location,
            "spatial_context": self.spatial_context,
            "times_scanned": self.times_scanned,
            "times_found": self.times_found,
            "confidence": self.confidence,
        }


@dataclass
class TrainingGate:
    """Tracks whether an app is ready for recognition-based automation."""
    app_name: str
    total_scans: int = 0
    successful_scans: int = 0
    elements_confirmed: int = 0
    elements_total: int = 0
    gate_status: str = "learning"  # "learning" | "ready"
    min_scans_required: int = 5
    min_confidence: float = 0.75

    @property
    def success_rate(self):
        return self.successful_scans / max(self.total_scans, 1)

    @property
    def element_coverage(self):
        return self.elements_confirmed / max(self.elements_total, 1)

    @property
    def is_ready(self):
        return (self.gate_status == "ready" and
                self.total_scans >= self.min_scans_required and
                self.success_rate >= self.min_confidence)

    def to_dict(self):
        return {
            "app_name": self.app_name,
            "total_scans": self.total_scans,
            "successful_scans": self.successful_scans,
            "success_rate": round(self.success_rate, 3),
            "elements_confirmed": self.elements_confirmed,
            "elements_total": self.elements_total,
            "element_coverage": round(self.element_coverage, 3),
            "gate_status": self.gate_status,
            "is_ready": self.is_ready,
            "min_scans_required": self.min_scans_required,
            "min_confidence": self.min_confidence,
        }


# ═══════════════════════════════════════════════════════════════════════════
# VISUAL MEMORY ORGAN
# ═══════════════════════════════════════════════════════════════════════════

class VisualMemoryOrgan:
    """
    Master orchestrator for the Visual UI Memory system.

    Coordinates:
      - organ_30 (AppScanner): deep UI probing, element discovery
      - organ_31 (VisualPerception): screenshot capture, vision description
      - organ_19 (ChromeCDP): web DOM + Accessibility tree
      - organ_ml.VisualEngine: screenshot storage, template matching
      - SSMS DatabaseManager: persistent visual memory storage
    """

    def __init__(self, cns=None):
        self.cns = cns
        self.db = DatabaseManager()
        self._ensure_tables()

    def _ensure_tables(self):
        """Create visual memory tables if they don't exist."""
        self.db.ensure_visual_memory_tables()
        self.db.ensure_app_ui_table()
        logger.info("Visual Memory tables ensured.")

    # ── 1. DEEP SCAN PIPELINE ────────────────────────────────────────────

    def deep_scan(self, app_name: str, window_title: str = "",
                  scanner=None, visual_perception=None,
                  chrome_cdp=None, session_id: Optional[str] = None,
                  mode: str = "first_contact",
                  elements: Optional[List[Dict[str, Any]]] = None) -> VisualSnapshot:
        """
        Perform a full deep scan of an app's UI.

        This orchestrates:
          1. organ_30 scanner: Walk UIA tree, probe buttons, scan menus
          2. organ_31: Take screenshot + vision description
          3. organ_19 (if web): Get DOM + Accessibility tree
          4. Store everything as a visual snapshot
          5. Build/update element profiles
          6. Update training gate

        Returns: VisualSnapshot with all captured data.
        """
        logger.info(f"[VISUAL MEMORY] Deep scan: {app_name} (mode={mode})")
        elements = list(elements) if elements else []
        screenshot_path = None
        vlm_description = ""
        ui_state_hash = ""
        dom_elements = []

        # Step 1: Capture screenshot
        try:
            import pyautogui
            from PIL import Image
            screenshot = pyautogui.screenshot()
            ts = int(time.time() * 1000)
            screenshot_path = os.path.join(SCREENSHOT_DIR, f"{app_name}_{ts}.png")
            screenshot.save(screenshot_path)
            logger.info(f"Screenshot saved: {screenshot_path}")
        except Exception as e:
            logger.warning(f"Screenshot capture failed: {e}")

        # Step 2: Vision description (Eye sees the UI)
        if visual_perception and screenshot_path:
            try:
                vlm_description = visual_perception.describe_screen_vision(
                    f"Describe this {app_name} interface in detail. List all visible buttons, "
                    f"menus, tabs, input fields, links, and their approximate positions. "
                    f"Focus on elements a user would click or interact with."
                ) or ""
                logger.info(f"VLM description: {vlm_description[:200]}...")
            except Exception as e:
                logger.warning(f"Vision description failed: {e}")

        # Step 3: Desktop UIA tree scan (organ_30)
        if scanner:
            try:
                scan_result = scanner.scan(app_name)
                if scan_result and scan_result.get("status") == "completed":
                    elements = scan_result.get("elements", [])
                    logger.info(f"Desktop scan found {len(elements)} elements")
            except Exception as e:
                logger.warning(f"Desktop scan failed: {e}")

        # Step 4: Web DOM + Accessibility tree (organ_19)
        if chrome_cdp:
            try:
                dom_result = chrome_cdp.get_dom_tree(session_id=session_id)
                if dom_result:
                    dom_elements = dom_result if isinstance(dom_result, list) else []
                    logger.info(f"Web DOM scan found {len(dom_elements)} elements")
            except Exception as e:
                logger.warning(f"Web DOM scan failed: {e}")

        # Step 5: Compute UI state hash
        state_data = {
            "app": app_name,
            "elements": [e.get("name", "") for e in elements],
            "dom_count": len(dom_elements),
            "vlm_hash": hashlib.md5(vlm_description.encode()).hexdigest()[:16] if vlm_description else "",
        }
        ui_state_hash = hashlib.sha256(json.dumps(state_data, sort_keys=True).encode()).hexdigest()[:32]

        # Step 6: Get previous scan count
        scan_count = self.db.get_visual_snapshot_count(app_name)

        # Step 7: Build visual snapshot
        snapshot = VisualSnapshot(
            app_name=app_name,
            window_title=window_title or app_name,
            scan_number=scan_count + 1,
            screenshot_path=screenshot_path or "",
            ui_state_hash=ui_state_hash,
            element_count=len(elements) + len(dom_elements),
            scan_mode=mode,
            vlm_description=vlm_description,
            elements=elements,
        )

        # Step 8: Store snapshot
        self.db.log_visual_snapshot(
            app_name=app_name,
            window_title=window_title or app_name,
            scan_number=snapshot.scan_number,
            screenshot_path=screenshot_path or "",
            ui_state_hash=ui_state_hash,
            element_count=snapshot.element_count,
            scan_mode=mode,
            vlm_description=vlm_description,
            elements_json=json.dumps(elements[:500]),  # limit for SSMS NVARCHAR
        )

        # Step 9: Build/update element profiles — one batched DB round trip set
        # for the whole scan instead of SELECT+write+commit per element
        profile_upserts = []
        for el in elements:
            name = el.get("name", "")
            if not name:
                continue
            el_type = el.get("type", "")
            coords = el.get("coords", {})
            box = coords.get("box", [0, 0, 0, 0])
            cx, cy = coords.get("x", 0), coords.get("y", 0)
            w = (box[2] - box[0]) if len(box) >= 4 else 0
            h = (box[3] - box[1]) if len(box) >= 4 else 0

            # Determine tab/group from element path or name
            tab_loc = self._infer_tab_location(el)
            group_loc = self._infer_group_location(el)

            # Generate visual description from VLM context
            visual_desc = self._generate_element_visual_desc(el, vlm_description)

            profile_upserts.append({
                "element_name": name,
                "element_type": el_type,
                "control_type": el_type,
                "visual_description": visual_desc,
                "region_x": cx, "region_y": cy, "region_w": w, "region_h": h,
                "tab_location": tab_loc,
                "group_location": group_loc,
            })

        stored_profiles = self.db.upsert_element_profiles_batch(app_name, profile_upserts)
        logger.info(f"[VISUAL MEMORY] Element profiles upserted in batch: {stored_profiles} rows")

        # Step 10: Update training gate
        elements_found = len(elements)
        gate_status = self.db.update_training_gate(
            app_name=app_name,
            scan_success=(elements_found > 0),
            elements_found=elements_found,
            elements_total=elements_found,
        )

        logger.info(f"[VISUAL MEMORY] Scan complete: {app_name}, "
                    f"elements={len(elements)}, gate={gate_status}, "
                    f"scan_number={snapshot.scan_number}")

        return snapshot

    # ── 2. RECOGNITION ───────────────────────────────────────────────────

    def recognize(self, app_name: str) -> Optional[Dict[str, Any]]:
        """
        Check if we have a trained visual memory for this app.

        Returns element profiles + gate status if ready,
        None if not yet trained enough.
        """
        gate = self.db.get_training_gate(app_name)
        if not gate:
            return None

        gate_obj = TrainingGate(
            app_name=app_name,
            total_scans=gate.get("total_scans", 0),
            successful_scans=gate.get("successful_scans", 0),
            elements_confirmed=gate.get("elements_confirmed", 0),
            elements_total=gate.get("elements_total", 0),
            gate_status=gate.get("gate_status", "learning"),
        )

        if not gate_obj.is_ready:
            logger.info(f"[VISUAL MEMORY] {app_name}: gate not ready "
                       f"(scans={gate_obj.total_scans}/{gate_obj.min_scans_required}, "
                       f"rate={gate_obj.success_rate:.1%})")
            return None

        # Gate is open — return element profiles
        profiles = self.db.get_element_profiles(app_name, confirmed_only=True)
        logger.info(f"[VISUAL MEMORY] {app_name}: RECOGNIZED "
                   f"({len(profiles)} confirmed elements)")

        return {
            "status": "recognized",
            "app_name": app_name,
            "gate": gate_obj.to_dict(),
            "elements": profiles,
        }

    # ── 3. DRIFT DETECTION ──────────────────────────────────────────────

    def detect_drift(self, app_name: str, current_elements: List[Dict]) -> Dict[str, Any]:
        """
        Compare current scan against stored visual memory.
        Detects if the UI has changed significantly.
        """
        profiles = self.db.get_element_profiles(app_name, confirmed_only=True)
        if not profiles:
            return {"drifted": False, "reason": "no_memory", "elements_stored": 0}

        stored_names = {p["element_name"] for p in profiles}
        current_names = {e.get("name", "") for e in current_elements if e.get("name")}

        missing = stored_names - current_names
        new = current_names - stored_names
        overlap = stored_names & current_names

        total_stored = len(stored_names)
        overlap_ratio = len(overlap) / max(total_stored, 1)

        drifted = overlap_ratio < 0.5  # Less than 50% overlap = UI changed significantly

        return {
            "drifted": drifted,
            "overlap_ratio": round(overlap_ratio, 3),
            "elements_stored": total_stored,
            "elements_current": len(current_names),
            "missing_elements": list(missing)[:20],
            "new_elements": list(new)[:20],
            "reason": "significant_change" if drifted else "stable",
        }

    # ── 4. ASSIST BRAIN COMPILATION ──────────────────────────────────────

    def assist_compilation(self, app_name: str, task_description: str) -> Optional[Dict[str, Any]]:
        """
        Called by Brain BEFORE compiling a task.
        If we have a trained visual memory for this app, provide element
        hints so Brain can compile better instructions.
        """
        recognition = self.recognize(app_name)
        if not recognition:
            return None

        elements = recognition.get("elements", [])

        # Build a context summary for Brain
        element_hints = []
        for el in elements:
            hint = {
                "name": el["element_name"],
                "type": el.get("element_type", ""),
                "location": f"tab={el.get('tab_location', '?')}, group={el.get('group_location', '?')}",
                "confidence": el.get("confidence_score", 0),
            }
            if el.get("visual_description"):
                hint["visual"] = el["visual_description"][:100]
            element_hints.append(hint)

        return {
            "app_known": True,
            "app_name": app_name,
            "scan_count": recognition["gate"]["total_scans"],
            "confidence": recognition["gate"]["success_rate"],
            "element_hints": element_hints[:50],
            "instruction": (
                f"The system has thoroughly learned the {app_name} interface through "
                f"{recognition['gate']['total_scans']} scans. "
                f"Use the element hints below to compile precise automation steps. "
                f"Elements are confirmed with {recognition['gate']['success_rate']:.0%} confidence."
            ),
        }

    # ── HELPERS ──────────────────────────────────────────────────────────

    def _infer_tab_location(self, element: Dict) -> str:
        """Infer which ribbon tab an element belongs to."""
        parent = element.get("parent_path", "")
        name = element.get("name", "")
        # Common tab patterns
        if any(t in parent.lower() for t in ("file", "edit", "view", "insert", "format", "tools")):
            for t in ("file", "edit", "view", "insert", "format", "tools"):
                if t in parent.lower():
                    return t.title()
        return ""

    def _infer_group_location(self, element: Dict) -> str:
        """Infer which UI group an element belongs to."""
        parent = element.get("parent_path", "")
        if parent:
            parts = parent.split(">")
            if len(parts) > 1:
                return parts[-2].strip()
        return ""

    def _generate_element_visual_desc(self, element: Dict, vlm_context: str) -> str:
        """Generate a visual description for an element."""
        name = element.get("name", "")
        ctype = element.get("type", "")
        coords = element.get("coords", {})
        box = coords.get("box", [])

        desc_parts = [f"{ctype} labeled '{name}'"]
        if box and len(box) == 4:
            w = box[2] - box[0]
            h = box[3] - box[1]
            desc_parts.append(f"size {w}x{h}")
            if box[1] < 100:
                desc_parts.append("at top of window")
            if box[0] < 100:
                desc_parts.append("at left side")

        return ", ".join(desc_parts)

    # ── STATUS ───────────────────────────────────────────────────────────

    def get_status(self) -> Dict[str, Any]:
        """Return status of all known visual memories."""
        try:
            import pyodbc
            conn = self.db._connect()
            cur = conn.cursor()
            cur.execute("SELECT app_name, total_scans, successful_scans, gate_status FROM visual_training_gate ORDER BY total_scans DESC")
            gates = []
            for row in cur.fetchall():
                gates.append({
                    "app": row[0],
                    "scans": row[1],
                    "success": row[2],
                    "status": row[3],
                })

            cur.execute("SELECT COUNT(*) FROM visual_snapshots")
            row = cur.fetchone()
            total_snapshots = row[0] if row else 0

            cur.execute("SELECT COUNT(*) FROM element_profiles")
            row = cur.fetchone()
            total_profiles = row[0] if row else 0

            return {
                "total_snapshots": total_snapshots,
                "total_element_profiles": total_profiles,
                "apps": gates,
            }
        except Exception as e:
            logger.warning(f"Status query failed: {e}")
            return {"error": str(e)}


# ═══════════════════════════════════════════════════════════════════════════
# SINGLETON
# ═══════════════════════════════════════════════════════════════════════════

_visual_memory = None

def get_visual_memory(cns=None):
    global _visual_memory
    if _visual_memory is None:
        _visual_memory = VisualMemoryOrgan(cns=cns)
    return _visual_memory
