"""
popup_splash_handler.py
=======================
100% DYNAMIC, APP-AGNOSTIC SPLASH, POPUP & MISCLICK-CONSEQUENCE ENGINE
- Detects Greeting/Splash Overlays vs. Active Workspaces using geometry & verb semantics.
- Records 'Before -> Action -> After' deltas into popup_consequence_fts in RAG.
"""

from __future__ import annotations
import hashlib
import json
import re
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

RAG_DB = Path(r"D:\new_automation\data\hojaiga_master_rag.db")


class UniversalPopupSplashHandler:
    WORKSPACE_ENTRY_VERBS = (
        "new", "blank", "start", "create", "general", "empty", "skip",
        "continue", "get started", "open workspace", "dismiss", "close"
    )
    SAFE_MODAL_DISMISS_VERBS = (
        "ok", "got it", "accept", "reject non-essential", "allow", "yes, i trust",
        "continue", "close", "cancel", "later", "not now"
    )
    DESTRUCTIVE_VERBS = (
        "delete", "remove", "format", "uninstall", "don't save", "discard",
        "pay", "purchase", "send", "publish", "terminate"
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
        if not visible_controls:
            return {"state": "BLIND_OR_LOADING", "confidence": 0.0}

        wx1, wy1, wx2, wy2 = window_rect
        win_w = max(wx2 - wx1, 1)
        win_h = max(wy2 - wy1, 1)
        win_area = win_w * win_h

        texts = [str(c.get("name", c.get("text", ""))).strip() for c in visible_controls]
        joined_low = " | ".join(t.lower() for t in texts if t)

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

        error_cues = ("error", "warning", "failed", "cannot", "already exists", "replace it",
                      "save changes", "permission", "cookie", "privacy", "trust the authors", "locked")
        if any(ec in joined_low for ec in error_cues):
            return {"state": "BLOCKING_MODAL_OR_ERROR", "centered_overlay": has_centered_overlay}

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
        preserve_midway_work: bool = True,
        window_rect: Tuple[int, int, int, int] = (0, 0, 1920, 1080),
    ) -> Optional[Dict[str, Any]]:
        diag = cls.classify_screen_state_dynamically(visible_controls, window_rect)
        state = diag["state"]
        if state == "DIRECT_WORKSPACE_READY":
            return None

        # Check RAG popup_consequence_fts for previously learned popup resolutions
        cls.ensure_consequence_table()
        texts = [str(c.get("name", c.get("text", ""))).strip() for c in visible_controls if c.get("name") or c.get("text")]
        joined_low = " | ".join(t.lower() for t in texts)

        if RAG_DB.exists() and texts:
            try:
                conn = sqlite3.connect(str(RAG_DB), timeout=10.0)
                tokens = [w for w in re.findall(r"[A-Za-z0-9]{4,}", joined_low)[:10]]
                if tokens:
                    q = " OR ".join(f'"{t}"' for t in set(tokens))
                    row = conn.execute(
                        "SELECT action_taken, observed_consequence, recovery_rule "
                        "FROM popup_consequence_fts WHERE popup_consequence_fts MATCH ? AND was_correct = '1' "
                        "ORDER BY bm25(popup_consequence_fts) LIMIT 1",
                        (q,),
                    ).fetchone()
                    if row:
                        conn.close()
                        act_json = json.loads(row[0])
                        act_json["screen_state"] = state
                        act_json["learned_from_rag_consequence"] = row[1]
                        return act_json
                conn.close()
            except Exception:
                pass

        # Dynamic Splash Resolution
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
                            "reason": f"Dynamic Splash Resolver: '{c_name}' transitions to active workspace",
                        }
            return {"screen_state": state, "action": "hotkey", "target": "Escape", "reason": "Pressing Escape to clear splash overlay"}

        # Dynamic Error/Modal Resolution
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
                            "reason": f"Dynamic Modal Resolver: Selected safe dismiss option '{c_name}'",
                        }
        return {"screen_state": state, "action": "none", "target": "none"}
