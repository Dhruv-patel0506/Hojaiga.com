"""
organ_49_scan_knowledge.py — knowledge that works SIDE BY SIDE with the scan.

The scanner (organ_30) finds controls. The behavior model (organ_48) knows what controls DO.
This file is the seam: one `ScanKnowledgeSession` per scan, the same for every app, that

  1. front-loads READ-ONLY knowledge (E0): app-version check (stale trust is demoted), the app's
     own menu tree + accelerators (Win32 HMENU / UIA ExpandCollapse), and any machine-readable
     artifacts a knowledge pack declares (keymaps, settings schemas, command registries) —
     the artifact harvest runs in a background thread while the scan proceeds;
  2. consults knowledge PER CONTROL before the scanner touches it:
         catalog_only  E2 / destructive class — recorded, never actuated
         skip_known    already verified in this app version — never re-probed
         probe         unknown or unverified — worth an E1 probe
  3. turns every probe into knowledge: (state, action, effector) -> (state', evidence)
     transitions, the full tree of any child window (regions), and promotion of a command to
     `learned` only when its effect was OBSERVED and the app returned to baseline;
  4. decides WHEN TO STOP from yield, not from app labels: a discovery budget that extends while
     probes keep yielding something new and ends when they flatten. A tiny app finishes fast,
     a sprawling one earns more time — nothing is classified easy or hard in advance.

Everything degrades: if organ_48 or UIA is unavailable, `open_session()` returns None and the
scanner runs exactly as before.
"""

from __future__ import annotations

import logging
import os
import threading
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

logger = logging.getLogger("hojaiga.organ_49_scan_knowledge")

ENABLED = os.environ.get("HOJAIGA_SCAN_KNOWLEDGE", "1") != "0"
# Active-probe budget (per scan). Generic controls mostly do nothing when pressed, so patience
# counts *probed* controls with zero yield, and is deliberately generous.
PROBE_BASE_S = float(os.environ.get("HOJAIGA_PROBE_BASE_S", "30"))
PROBE_EXTEND_S = float(os.environ.get("HOJAIGA_PROBE_EXTEND_S", "8"))
PROBE_MAX_S = float(os.environ.get("HOJAIGA_PROBE_MAX_S", "180"))
PROBE_PATIENCE = int(os.environ.get("HOJAIGA_PROBE_PATIENCE", "15"))
UNWIND_FAIL_LIMIT = 2


@dataclass
class ProbeDecision:
    action: str            # probe | skip_known | catalog_only
    risk: str = "EU"
    reason: str = ""
    cmd_id: str = ""


class ScanKnowledgeSession:
    def __init__(self, app_name: str, hwnd: int, model=None, grounding=None):
        from core_organs import organ_48_app_behavior_model as bm
        from core_organs import desktop_grounding as dg
        self.bm = bm
        self.app_name = app_name
        self.hwnd = hwnd
        self.model = model or bm.get_model()
        self.g = grounding or dg.DesktopGrounding()
        self.key = bm._app_key(app_name)
        self.run_id = "scan_" + str(int(time.time()))
        self.budget = bm.DiscoveryBudget(base_s=PROBE_BASE_S, extend_s=PROBE_EXTEND_S,
                                         max_s=PROBE_MAX_S, patience=PROBE_PATIENCE)
        self.stats: Dict[str, Any] = {
            "e0": {}, "known_before": 0, "skipped_known": 0, "catalog_only": 0, "probes": 0,
            "effects_observed": 0, "promoted": 0, "eroded": 0, "transitions": 0, "regions": 0,
            "unwind_failures": 0, "pack": {}, "stopped": ""}
        self._pack_thread: Optional[threading.Thread] = None
        self._menu_cache: Dict[str, List[Dict[str, Any]]] = {}
        self._bg = None

    # ---- 1. front-load read-only knowledge ------------------------------------------------
    def start(self) -> Dict[str, Any]:
        bm = self.bm
        try:
            from core_organs import popup_mode
            popup_mode.set_policy("probe")                  # cancel-only dialogs while we explore
        except Exception:
            pass
        # whole-scan background session: a minimized app is parked off-screen (never shown, never
        # focused) from here until finish(); nested crawler/mapper sessions just ref-count
        try:
            self._bg = bm._bg(self.hwnd)
            self._bg.__enter__()
            self.stats["window_mode"] = getattr(self._bg, "mode", "") or "visible"
        except Exception:
            self._bg = None
        exe = bm._exe_of_hwnd(self.hwnd)
        vh = bm.app_version_hash(exe)
        self.stats["version_hash"] = vh
        self.stats["demoted_on_version_change"] = self.model.check_version(self.key, vh)
        # packs: load once per process, then harvest this app's declared artifacts in the background
        try:
            loaded = self.model.load_pack_dir()
            self.stats["pack"]["loaded"] = sum(1 for r in loaded if r.get("loaded"))
        except Exception as exc:
            self.stats["pack"]["error"] = type(exc).__name__
        self._start_pack_harvest(exe)
        existing = self.model.commands(self.key, limit=5000)
        self.stats["known_before"] = len(existing)
        e0_cached = any((c.get("origin") or "").startswith("e0:") and not c.get("stale") for c in existing)
        if e0_cached:
            self.stats["e0"] = {"skipped": "e0 map already cached for this app version"}
        else:
            try:
                self.stats["e0"] = bm.crawl_e0(self.model, self.app_name, self.hwnd)
            except Exception as exc:
                self.stats["e0"] = {"error": f"{type(exc).__name__}: {exc}"}
        self._menu_cache.clear()
        # sections + every control + where it sits (organ_50); cached per app version
        try:
            from core_organs import organ_50_layout_map as lm
            cached = None if os.environ.get("HOJAIGA_REMAP_LAYOUT") == "1" else lm.layout_cached(self.model, self.key, vh)
            if cached:
                self.stats["layout"] = {"skipped": "layout map cached for this app version", **cached}
            else:
                self.stats["layout"] = lm.map_layout(self.model, self.app_name, self.hwnd, version_hash=vh)
        except Exception as exc:
            self.stats["layout"] = {"error": f"{type(exc).__name__}: {exc}"}
        return self.stats["e0"]

    def _start_pack_harvest(self, exe: str) -> None:
        bm = self.bm
        rows = self.model._conn.execute(
            "SELECT sources_json FROM bm_packs WHERE app_key=?", (self.key,)).fetchall()
        sources: List[dict] = []
        import json as _json
        for r in rows:
            try:
                sources += _json.loads(r["sources_json"] or "[]")
            except Exception:
                continue
        if not sources:
            self.stats["pack"]["sources"] = 0
            return
        self.stats["pack"]["sources"] = len(sources)

        def _run():
            try:
                m2 = bm.BehaviorModel(self.model.db_path)         # own connection: thread-safe
                self.stats["pack"]["harvest"] = bm.harvest_pack_sources(m2, self.app_name, sources, exe=exe)
                m2.close()
            except Exception as exc:
                self.stats["pack"]["harvest"] = {"error": type(exc).__name__}
        self._pack_thread = threading.Thread(target=_run, daemon=True, name="scan-pack-harvest")
        self._pack_thread.start()

    # ---- 2. per-control consultation --------------------------------------------------------
    def menu_elements(self, header_name: str) -> List[Dict[str, Any]]:
        """Scanner-compatible element dicts for a menu header, from the E0 map (no popup opened)."""
        if header_name in self._menu_cache:
            return self._menu_cache[header_name]
        want = self.bm._norm(header_name.replace("&", ""))
        out = []
        for c in self.model.commands(self.key, limit=5000):
            mp = c.get("menu_path") or ""
            parts = [self.bm._norm(x.replace("&", "")) for x in mp.split(">")]
            if len(parts) >= 2 and parts[0] == want and (c.get("origin") or "").startswith("e0:"):
                e = {"name": c["name"], "type": "MenuItem",
                     "coords": {"x": -1, "y": -1, "box": [-1, -1, -1, -1]},
                     "parent_menu": header_name, "menu_path": mp, "source": "organ_48_e0"}
                if c.get("shortcut"):
                    e["accelerator"] = c["shortcut"]
                out.append(e)
        self._menu_cache[header_name] = out
        return out

    def policy(self, item: Dict[str, Any]) -> ProbeDecision:
        bm = self.bm
        name = item.get("name") or ""
        risk = bm.classify_risk(name)
        cmd = self.model.command_by_name(self.key, name)
        if cmd and cmd["risk"] == "E2":
            risk = "E2"
        if risk == "E2":
            self.stats["catalog_only"] += 1
            return ProbeDecision("catalog_only", "E2", "destructive class: catalogued, never actuated",
                                 cmd["cmd_id"] if cmd else "")
        if cmd and cmd["source"] == "learned" and cmd["successes"] >= 1 and not cmd["stale"] \
                and cmd["verb"] != "setting":
            self.stats["skipped_known"] += 1
            return ProbeDecision("skip_known", cmd["risk"], "verified in this app version", cmd["cmd_id"])
        return ProbeDecision("probe", risk, "unknown or unverified", cmd["cmd_id"] if cmd else "")

    # ---- 3. observation -> knowledge ----------------------------------------------------------
    def light_state(self):
        return self.bm.observe(self.hwnd, grounding=self.g, max_nodes=350)

    def record_probe(self, item: Dict[str, Any], before, effect: str, new_controls: int = 0,
                     dialog_elements: Optional[List[Dict[str, Any]]] = None,
                     dialog_title: str = "", effector: str = "uia_activate",
                     decision: Optional[ProbeDecision] = None) -> None:
        """Turn one probe into knowledge. `effect` in {dialog, modal, expanded, none}."""
        bm = self.bm
        name = item.get("name") or item.get("type", "control")
        self.stats["probes"] += 1
        try:
            after = self.light_state()
        except Exception:
            self.budget.credit(new_controls)
            return
        restored = set(after.windows) == set(before.windows)
        if not restored:
            self.stats["unwind_failures"] += 1
        observed = effect != "none" or new_controls > 0 or after.uia_signature() != before.uia_signature()
        evidence = (f"effect={effect}; new_controls={new_controls}; windows {len(before.windows)}->"
                    f"{len(after.windows)}; baseline={'restored' if restored else 'NOT restored'}")
        gained = new_controls
        try:
            cmd = self.model.command_by_name(self.key, name)
            cid = cmd["cmd_id"] if cmd else self.model.upsert_command(
                self.key, {"name": name, "goal": name, "verb": "invoke", "risk": "E1" if observed else "EU",
                           "post": [{"kind": "window_opened"}] if effect in ("dialog", "modal")
                           else [{"kind": "ui_changed"}]},
                source="catalog", origin="scan-probe")
            if observed:
                self.stats["effects_observed"] += 1
                bm_tid = self.model.record_transition(self.key, before, f"invoke:{name}", effector, after, evidence)
                self.stats["transitions"] += 1
                gained += 1 if not (cmd and cmd["source"] == "learned") else 0
                if restored:
                    self.model.command_outcome(cid, "PASS", evidence, promote=True)
                    self.stats["promoted"] += 1
                if dialog_elements:
                    self.model.record_region(self.key, dialog_title or name, dialog_elements,
                                             via=f"invoke:{name}")
                    self.stats["regions"] += 1
            elif cmd and cmd["source"] != "archetype":
                # knowledge expected an effect and the probe saw none: erode, don't ignore
                self.model.command_outcome(cid, "FAIL", evidence)
                self.stats["eroded"] += 1
            self.model.audit(self.run_id, self.key, "probe", name,
                             "EFFECT" if observed else "NO_EFFECT", effect, evidence)
        except Exception as exc:
            logger.debug("[scan-knowledge] record_probe failed: %s", exc)
        self.budget.credit(gained)

    # ---- 4. stop rule + summary ------------------------------------------------------------------
    def should_stop(self) -> str:
        if self.stats["unwind_failures"] >= UNWIND_FAIL_LIMIT:
            self.stats["stopped"] = "unwind-failed"
            return "unwind-failed"
        why = self.budget.reason_to_stop()
        if why:
            self.stats["stopped"] = why
        return why

    def finish(self) -> Dict[str, Any]:
        try:
            from core_organs import popup_mode
            popup_mode.set_policy("task")
        except Exception:
            pass
        if self._bg is not None:
            try:
                self._bg.__exit__(None, None, None)         # back to minimized, original placement
            except Exception:
                pass
            self._bg = None
        if self._pack_thread is not None:
            self._pack_thread.join(timeout=3.0)
            if self._pack_thread.is_alive():
                self.stats["pack"]["harvest"] = "still running (continues in background)"
        known_after = len(self.model.commands(self.key, limit=5000))
        self.stats.update(known_after=known_after, elapsed_s=round(self.budget.elapsed(), 2),
                          regions_known=len(self.model.regions(self.key)),
                          stopped=self.stats["stopped"] or "completed")
        return dict(self.stats)


def open_session(app_name: str, hwnd: int) -> Optional[ScanKnowledgeSession]:
    """Safe factory for the scanner: None means 'run exactly as before'."""
    if not ENABLED:
        return None
    try:
        return ScanKnowledgeSession(app_name, hwnd)
    except Exception as exc:
        logger.debug("[scan-knowledge] unavailable: %s", exc)
        return None
