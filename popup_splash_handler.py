"""
core_organs/popup_splash_handler.py
===================================
100% DYNAMIC, APP-AGNOSTIC SPLASH, POPUP & MISCLICK-CONSEQUENCE ENGINE
- ZERO Hardcoded App Names: Works on any unseen desktop app, website, or web app.
- Structural Geometry Detection: Distinguishes an Opening Greeting/Splash Overlay
  from a Direct Active Workspace by measuring container bounds, z-order, and control verbs.
- Live Error Reading & Consequence Recording: Reads any unknown popup/error on the spot,
  selects the safest resolution, measures the Before->After state delta, and stores
  the learned consequence in `popup_consequence_fts` so the RAG self-grows automatically.
"""

from __future__ import annotations
import hashlib
import json
import re
import sqlite3
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

RAG_DB = Path(r"D:\new_automation\data\hojaiga_master_rag.db")


class UniversalPopupSplashHandler:
    # Universal semantic verb polarities (App-Agnostic)
    WORKSPACE_ENTRY_VERBS = (
        "new", "blank", "start", "create", "general", "empty", "skip",
        "continue", "get started", "open workspace", "dismiss", "close",
    )
    SAFE_MODAL_DISMISS_VERBS = (
        "ok", "got it", "accept", "reject non-essential", "allow", "yes, i trust",
        "continue", "close", "cancel", "later", "not now",
    )
    DESTRUCTIVE_VERBS = (
        "delete", "remove", "format", "uninstall", "don't save", "discard",
        "pay", "purchase", "send", "publish", "terminate",
    )
    PRIMARY_WORKSPACE_ROLES = (
        "document", "canvas", "viewport", "edit", " table", "grid", "main",
        "workspace", "pane", "custom", "tabcontrol",
    )

    @classmethod
    def ensure_consequence_table(cls) -> None:
        if not RAG_DB.exists():
            return
        conn = sqlite3.connect(str(RAG_DB), timeout=20.0)
        conn.execute(
            "CREATE VIRTUAL TABLE IF NOT EXISTS popup_consequence_fts USING fts5("
            "signature_hash, screen_topology, popup_text_signature, action_taken, "
            "observed_consequence, was_correct, recovery_rule, tokenize='porter unicode61'"
            ")"
        )
        conn.commit()
        conn.close()

    @classmethod
    def classify_screen_state_dynamically(
        cls,
        visible_controls: List[Dict[str, Any]],
        window_rect: Tuple[int, int, int, int] = (0, 0, 1920, 1080),
    ) -> Dict[str, Any]:
        """
        Determines dynamically (with ZERO app-name checks) whether the live screen is:
        1. 'DIRECT_WORKSPACE_READY' (ready to execute tasks immediately)
        2. 'OPENING_GREETING_OR_SPLASH' (startup chooser/overlay blocking the workspace)
        3. 'BLOCKING_MODAL_OR_ERROR' (error alert, permission prompt, file dialog, cookie wall)
        """
        if not visible_controls:
            return {"state": "BLIND_OR_LOADING", "confidence": 0.0}

        wx1, wy1, wx2, wy2 = window_rect
        win_w = max(wx2 - wx1, 1)
        win_h = max(wy2 - wy1, 1)
        win_area = win_w * win_h

        texts = [str(c.get("name", c.get("text", ""))).strip() for c in visible_controls]
        roles = [str(c.get("role", c.get("control_type", ""))).lower() for c in visible_controls]
        joined_low = " | ".join(t.lower() for t in texts if t)

        # Check for centered modal/dialog container geometry (10% to 75% of window area near center)
        has_centered_overlay = False
        for c in visible_controls:
            bbox = c.get("bbox")
            role = str(c.get("role", c.get("control_type", ""))).lower()
            if bbox and len(bbox) == 4 and any(r in role for r in ("dialog", "window", "pane", "alert", "modal")):
                cw = max(0, bbox[2] - bbox[0])
                ch = max(0, bbox[3] - bbox[1])
                ratio = (cw * ch) / win_area
                cx = (bbox[0] + bbox[2]) / 2.0
                cy = (bbox[1] + bbox[3]) / 2.0
                if 0.08 <= ratio <= 0.78 and (0.25 * win_w <= cx - wx1 <= 0.75 * win_w):
                    has_centered_overlay = True
                    break

        # Check semantic cues for Error / Blocking Modal
        error_cues = ("error", "warning", "failed", "cannot", "already exists", "replace it",
                      "save changes", "permission", "cookie", "privacy", "trust the authors", "locked")
        if any(ec in joined_low for ec in error_cues):
            return {"state": "BLOCKING_MODAL_OR_ERROR", "centered_overlay": has_centered_overlay}

        # Check semantic + geometric cues for Opening Splash / Greeting Chooser
        splash_cues = ("welcome", "new file", "blank", "recent", "get started", "start drawing",
                       "template", "recover last", "auto-configuration", "sign in to continue")
        splash_hits = sum(1 for sc in splash_cues if sc in joined_low)
        if splash_hits >= 2 or (has_centered_overlay and splash_hits >= 1):
            return {"state": "OPENING_GREETING_OR_SPLASH", "centered_overlay": True}

        return {"state": "DIRECT_WORKSPACE_READY", "centered_overlay": False}

    @classmethod
    def inspect_and_resolve(
        cls,
        visible_controls: List[Dict[str, Any]],
        task_goal: str = "",
        preserve_midway_work: bool = True,
        window_rect: Tuple[int, int, int, int] = (0, 0, 1920, 1080),
    ) -> Optional[Dict[str, Any]]:
        """
        App-agnostic resolver: inspects live controls, checks learned consequences in RAG,
        and outputs the safest immediate action to clear any splash screen or popup.
        """
        diag = cls.classify_screen_state_dynamically(visible_controls, window_rect)
        state = diag["state"]
        if state == "DIRECT_WORKSPACE_READY":
            return None

        texts = [str(c.get("name", c.get("text", ""))).strip() for c in visible_controls if c.get("name") or c.get("text")]
        joined_low = " | ".join(t.lower() for t in texts)

        # 1. First consult RAG `popup_consequence_fts` for previously learned consequences
        cls.ensure_consequence_table()
        if RAG_DB.exists() and texts:
            try:
                conn = sqlite3.connect(str(RAG_DB), timeout=10.0)
                tokens = [w for w in re.findall(r"[A-Za-z0-9]{4,}", joined_low)[:8]]
                if tokens:
                    # Use AND on key tokens or require exact action validity
                    q = " AND ".join(f'"{t}"' for t in set(tokens[:4]))
                    row = conn.execute(
                        "SELECT action_taken, observed_consequence, recovery_rule "
                        "FROM popup_consequence_fts WHERE popup_consequence_fts MATCH ? AND was_correct = '1' "
                        "ORDER BY bm25(popup_consequence_fts) LIMIT 1",
                        (q,),
                    ).fetchone()
                    if row:
                        conn.close()
                        act_json = json.loads(row[0])
                        # Ignore synthetic placeholder targets during live control resolution
                        if not str(act_json.get("target", "")).startswith("Control_in_PAT_"):
                            act_json.setdefault("screen_state", state)
                            act_json["learned_from_rag_consequence"] = row
                            act_json["recovery_rule"] = row[2]
                            return act_json
                conn.close()
            except Exception:
                pass
        # 2. Dynamic Inference for Opening Greeting / Splash Screen
        if state == "OPENING_GREETING_OR_SPLASH":
            for verb in cls.WORKSPACE_ENTRY_VERBS:
                for ctrl in visible_controls:
                    c_name = str(ctrl.get("name", ctrl.get("text", ""))).strip()
                    if c_name and (c_name.lower() == verb or verb in c_name.lower()):
                        if any(d in c_name.lower() for d in cls.DESTRUCTIVE_VERBS):
                            continue
                        return {
                            "screen_state": state,
                            "action": "click",
                            "target": c_name,
                            "control_id": ctrl.get("id"),
                            "bbox": ctrl.get("bbox"),
                            "fallback_hotkey": "Escape",
                            "reason": f"Dynamic Splash Resolver: '{c_name}' transitions from greeting screen to active workspace",
                        }
            return {
                "screen_state": state,
                "action": "hotkey",
                "target": "Escape",
                "reason": "Dynamic Splash Resolver: No explicit entry button matched; pressing Escape to dismiss overlay",
            }

        # 3. Dynamic Inference for Blocking Modal / Error Popup
        if state == "BLOCKING_MODAL_OR_ERROR":
            for verb in cls.SAFE_MODAL_DISMISS_VERBS:
                for ctrl in visible_controls:
                    c_name = str(ctrl.get("name", ctrl.get("text", ""))).strip()
                    if c_name and (c_name.lower() == verb or verb in c_name.lower()):
                        if preserve_midway_work and any(d in c_name.lower() for d in cls.DESTRUCTIVE_VERBS):
                            continue
                        return {
                            "screen_state": state,
                            "action": "click",
                            "target": c_name,
                            "control_id": ctrl.get("id"),
                            "bbox": ctrl.get("bbox"),
                            "reason": f"Dynamic Error/Modal Resolver: Selected non-destructive control '{c_name}'",
                        }
        return None

    @classmethod
    def record_action_consequence(
        cls,
        before_controls: List[Dict[str, Any]],
        action_taken: Dict[str, Any],
        after_controls: List[Dict[str, Any]],
        goal_progressed: bool,
    ) -> Dict[str, Any]:
        """
        Self-Growth Loop: Records what happened after clicking ANY popup button or misclicking
        a control so the RAG permanently remembers the consequence and how to recover.
        """
        cls.ensure_consequence_table()
        before_names = {str(c.get("name", "")).strip() for c in before_controls if c.get("name")}
        after_names = {str(c.get("name", "")).strip() for c in after_controls if c.get("name")}
        appeared = sorted(after_names - before_names)[:10]
        disappeared = sorted(before_names - after_names)[:10]

        consequence_summary = (
            f"Disappeared: {disappeared[:4]} | Appeared: {appeared[:4]} | "
            f"ControlCount: {len(before_controls)}->{len(after_controls)}"
        )
        recovery_rule = (
            "Action succeeded; promote path."
            if goal_progressed
            else f"Action caused unintended state ({appeared[:3]}); rollback via Escape/Ctrl+Z and avoid '{action_taken.get('target')}'."
        )
        sig_text = " | ".join(sorted(before_names)[:15])
        sig_hash = hashlib.sha256(f"{sig_text}|{action_taken}".encode("utf-8")).hexdigest()[:16]

        if RAG_DB.exists():
            try:
                conn = sqlite3.connect(str(RAG_DB), timeout=15.0)
                conn.execute(
                    "INSERT INTO popup_consequence_fts VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (
                        sig_hash,
                        f"controls_{len(before_controls)}",
                        sig_text[:500],
                        json.dumps(action_taken, ensure_ascii=False),
                        consequence_summary,
                        "1" if goal_progressed else "0",
                        recovery_rule,
                    ),
                )
                conn.commit()
                conn.close()
            except Exception:
                pass

        return {
            "signature_hash": sig_hash,
            "consequence": consequence_summary,
            "was_correct": goal_progressed,
            "recovery_rule": recovery_rule,
        }
