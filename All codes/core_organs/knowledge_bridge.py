"""
knowledge_bridge.py -- the seam between what is KNOWN about an app (behavior model: unified commands, routes, state) and the
live decision loop (desktop_grounding.DesktopAutonomyLoop).

Before this bridge the free-form loop consulted only organ_47's step memory; everything a scan or an exploration learned
(menu IDs, accelerators, menu paths, dialog schemas, how the app accepts input) was visible only to the template runner.
Now, for every goal the loop asks the bridge:

  consult(app, goal)      the best unified command for the goal and the ordered ROUTES to execute it, or None
  direct_ok(kb)           may it run WITHOUT the judge? Only a verified command: >= 2 independent verified successes
                          (6.4: one lucky trace never enables muscle memory), no recent failure, a machine-checkable
                          postcondition, not destructive (E2), the goal is not a typing goal, and the route is one this
                          app is known to accept (a posted key on a host that ignores keys is never used)
  as_hint(kb)             the same knowledge as a ranked HINT for the judge (never takes control)
  execute(...)            deliver the first applicable route through the effector ladder (no physical input)
  record(...)             after the verifier's verdict: reinforce / erode the command, record the effector outcome, and
                          write the (state, action, effector) -> (state', evidence) TRANSITION (3.3)

Everything is data lookup; there is no per-app branch and no LLM call.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import time
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("hojaiga.knowledge_bridge")

ENABLED = os.environ.get("HOJAIGA_KNOWLEDGE_BRIDGE", "1") != "0"
DIRECT_MIN_SUCCESSES = int(os.environ.get("HOJAIGA_DIRECT_MIN_SUCCESSES", "2"))
HINT_MIN_SCORE = float(os.environ.get("HOJAIGA_KB_HINT_MIN_SCORE", "2.5"))
DIRECT_MIN_COVERAGE = 1.0          # every word of the goal must be covered by the command's label


class KnowledgeBridge:
    def __init__(self, model=None):
        self._model = model
        self._reg_cache: Dict[str, Tuple[float, List[Dict[str, Any]]]] = {}

    @property
    def model(self):
        if self._model is None:
            from core_organs import organ_48_app_behavior_model as bm
            self._model = bm.get_model()
        return self._model

    def key(self, app_hint: str) -> str:
        from core_organs import organ_48_app_behavior_model as bm
        return bm._app_key(app_hint)

    def registry(self, key: str, ttl: float = 20.0) -> List[Dict[str, Any]]:
        from core_organs import command_registry as cr
        now = time.time()
        hit = self._reg_cache.get(key)
        if hit and now - hit[0] < ttl:
            return hit[1]
        reg = cr.build(self.model, key)
        self._reg_cache[key] = (now, reg)
        return reg

    def _bust(self, key: str) -> None:
        self._reg_cache.pop(key, None)

    # ------------------------------------------------------------------ consult
    def consult(self, app_hint: str, goal: str, *, wants_text: bool = False) -> Optional[Dict[str, Any]]:
        """Best unified command for the goal (with routes), or None. Typing goals are not command goals."""
        if not ENABLED or wants_text or not (goal or "").strip():
            return None
        try:
            key = self.key(app_hint)
            n = self.model._conn.execute("SELECT COUNT(*) FROM bm_commands WHERE app_key=?", (key,)).fetchone()[0]
            if not n:
                return None
            from core_organs import command_registry as cr
            hits = cr.lookup(self.model, key, goal, limit=4, registry=self.registry(key))
            if not hits or hits[0]["score"] < HINT_MIN_SCORE:
                return None
            top = hits[0]
            top["app_key"] = key
            top["goal"] = goal
            return top
        except Exception as exc:
            logger.debug("[bridge] consult failed: %s", exc)
            return None

    # ------------------------------------------------------------------ gate
    def direct_ok(self, kb: Dict[str, Any], goal: str) -> Tuple[bool, str]:
        """May this command run without the judge? Returns (ok, reason). The reason is always reported."""
        if kb["risk"] == "E2":
            return False, "destructive class (E2): never direct"
        if not kb.get("verified") or kb["successes"] < DIRECT_MIN_SUCCESSES:
            return False, f"{kb['successes']} verified success(es) < {DIRECT_MIN_SUCCESSES} required (a single trace is not muscle memory)"
        if kb["failures"] and kb["successes"] < 2 * kb["failures"]:
            return False, f"failures ({kb['failures']}) outweigh successes ({kb['successes']})"
        if not kb["post"]:
            return False, "no machine-checkable postcondition recorded"
        if kb.get("coverage", 0) < DIRECT_MIN_COVERAGE:
            return False, f"command label covers only {kb.get('coverage', 0):.0%} of the goal's words"
        usable = [r for r in kb["routes"] if r["effector"] in ("wm_command", "menu_path", "key", "invoke_control")]
        if not usable:
            return False, "no route this app is known to accept"
        return True, f"verified x{kb['successes']}, {len(kb['sources'])} source(s), route {usable[0]['effector']}"

    def accelerator_ok(self, kb: Dict[str, Any], goal: str) -> Tuple[bool, str]:
        """4.2: the keyboard route as a VERIFIED ATTEMPT (not muscle memory). Allowed only when the shortcut is DECLARED by the app
        itself in >= 2 independent sources (e.g. its resource accelerator table AND the live menu), key delivery is proven on this
        app (the registry only lists a key route first then), the command is not destructive, the label covers the whole goal and
        it has never failed. The postcondition verifier still judges it, and a failure erodes the route."""
        if kb["risk"] == "E2":
            return False, "destructive class"
        if not kb["routes"] or kb["routes"][0]["effector"] != "key":
            return False, "key delivery not proven on this app (or no accelerator)"
        if kb.get("shortcut_agreement", 0) < 2 and kb["corroborated"] < 2:
            return False, "accelerator declared by one source only"
        if kb.get("coverage", 0) < DIRECT_MIN_COVERAGE:
            return False, "label does not cover the whole goal"
        if kb["failures"]:
            return False, f"{kb['failures']} earlier failure(s)"
        return True, f"accelerator {kb['shortcut']} declared by {kb['corroborated']} source(s), delivery proven"

    def as_hint(self, kb: Dict[str, Any]) -> Dict[str, Any]:
        """The command as a judge hint (organ_47's shape): ranks elements, never executes."""
        name = kb["name"]
        return {"kind": "element", "element_name": name, "element_role": "menuitem", "menu_path": kb["menu_path"],
                "shortcut": kb["shortcut"], "verb": "click",
                "kb_route": kb["shortcut"] if any(r["effector"] == "key" for r in kb["routes"]) else "",
                "confidence": round(min(0.9, 0.35 + 0.1 * kb["trust"] + 0.05 * kb["corroborated"]), 2),
                "source": "learned" if kb["verified"] else "catalog", "step_id": "kb:" + (kb["cmd_ids"][0] if kb["cmd_ids"] else name),
                "goal": kb.get("goal", ""), "accelerator": kb["shortcut"], "alt_accelerators": kb.get("alt_shortcuts", []),
                "routes": [r["effector"] for r in kb["routes"]]}

    # ------------------------------------------------------------------ execute
    def execute(self, kb: Dict[str, Any], hwnd: int, grounding=None, max_routes: int = 2, only: str = "") -> Tuple[bool, str, str]:
        """Deliver the first applicable route(s) (only the `only` effector when given). Returns (delivered, effector, note).
        No physical input."""
        from core_organs import organ_48_app_behavior_model as bm
        from core_organs import desktop_grounding as dg
        from core_organs import headless_input as hin
        ladder = bm.EffectorLadder(self.model, grounding)
        ladder._cur_app = kb.get("app_key", "")
        trail: List[str] = []
        tried = 0
        for r in kb["routes"]:
            if tried >= max_routes:
                break
            eff = r["effector"]
            if only and eff != only:
                continue
            if eff == "wm_command":
                ok, note = ladder._try("wm_command", "invoke", {"menu_id": r["menu_id"], "name": kb["name"]}, hwnd, dg, hin)
            elif eff == "menu_path":
                ok, note = ladder._try("menu_command", "menu", {"path": r["path"]}, hwnd, dg, hin)
            elif eff == "key":
                ok, note = ladder._try("key", "key", {"keys": r["keys"]}, hwnd, dg, hin)
            elif eff == "invoke_control":
                ok, note = ladder._try("snapshot_invoke", "invoke", {"label": r["label"]}, hwnd, dg, hin)
            else:
                continue
            tried += 1
            if ok:
                return True, eff, note
            trail.append(f"{eff}: {note}")
        return False, "none", " | ".join(trail) or "no executable route"

    # ------------------------------------------------------------------ preconditions (3.2)
    def precheck(self, app_hint: str, target: str, hwnd: int, grounding=None) -> Optional[Dict[str, Any]]:
        """The command the loop is about to fire (by control label) may need the app in a MODE ('extrude' needs edit mode). If
        the learned command carries preconditions: observe, evaluate, and when a mode is wrong walk the learned mode graph
        (path_to_mode) to repair it. Returns None when the command has no preconditions (zero cost), else
        {'ok': bool, 'why': str, 'repaired': [commands run]}. A command whose precondition cannot be met is NOT fired."""
        try:
            from core_organs import organ_48_app_behavior_model as bm
            key = self.key(app_hint)
            cmd = self.model.command_by_name(key, target)
            if not cmd:
                return None
            pre = json.loads(cmd.get("pre_json") or "[]")
            if not pre:
                return None
            st = bm.observe(hwnd, grounding=grounding, want_ocr=bm.needs_ocr(pre))
            st.mode = self.model.current_mode([key], st)
            res = bm.evaluate(pre, None, st)
            if res.verdict == "PASS":
                return {"ok": True, "why": "precondition holds: " + res.text()[:120], "repaired": []}
            want_mode = next((a["mode"] for a in pre if a.get("kind") == "mode_is"), "")
            repaired: List[str] = []
            if want_mode and st.mode != want_mode:
                path = self.model.path_to_mode([key], st.mode, want_mode)
                if path:
                    ladder = bm.EffectorLadder(self.model, grounding)
                    for step in path:
                        ladder.perform(key, hwnd, {"verb": "key" if step["shortcut"] else "invoke", "keys": step["shortcut"],
                                                   "name": step["name"], "menu_id": step["menu_id"], "path": step["menu_path"]})
                        repaired.append(step["name"])
                        time.sleep(0.4)
                    st = bm.observe(hwnd, grounding=grounding, want_ocr=bm.needs_ocr(pre))
                    st.mode = self.model.current_mode([key], st)
                    res = bm.evaluate(pre, None, st)
                    if res.verdict == "PASS":
                        return {"ok": True, "why": f"mode repaired via {repaired}", "repaired": repaired}
            return {"ok": False, "why": f"precondition not met ({res.text()[:100]}); mode='{st.mode or '?'}' want '{want_mode or '-'}'"
                                        + ("" if repaired else "; no learned path to the required mode"), "repaired": repaired}
        except Exception as exc:
            logger.debug("[bridge] precheck failed: %s", exc)
            return None

    # ------------------------------------------------------------------ record
    def observe_light(self, hwnd: int, title: str, names: List[str], modes: List[str]):
        """ObservedState from what the loop already holds (no extra UIA walk)."""
        from core_organs import organ_48_app_behavior_model as bm
        try:
            wins = sorted({(bm._win_title(w) or bm._win_class(w)).lower() for w in bm._open_popups(hwnd)[:8]})
        except Exception:
            wins = []
        st = bm.ObservedState(title=title or "", names=[n for n in names if n], windows=wins, hwnd=hwnd)
        st.mode = hashlib.md5("|".join(sorted(modes)).encode()).hexdigest()[:10] if modes else ""
        return st

    def record(self, app_hint: str, goal: str, *, verb: str, target: str, effector: str, verdict: str,
               before_state=None, after_state=None, evidence: str = "", kb: Optional[Dict[str, Any]] = None,
               strong: bool = False) -> Dict[str, Any]:
        """Verified-step learning: command reinforcement, effector outcome, state transition. Never raises."""
        out = {"transition": False, "command": ""}
        try:
            key = self.key(app_hint)
            m = self.model
            if effector and verb in ("click", "invoke", "key", "shortcut", "menu"):
                m.record_effector(key, {"click": "invoke", "shortcut": "key"}.get(verb, verb), effector.split("+")[0].split(":")[0],
                                  verdict == "PASS")
            cmd_ids: List[str] = list(kb["cmd_ids"]) if kb else []
            if not cmd_ids and target:
                c = m.command_by_name(key, target)
                if c:
                    cmd_ids = [c["cmd_id"]]
            for cid in cmd_ids[:3]:
                if verdict == "PASS":
                    m.command_outcome(cid, "PASS", evidence[:200], promote=strong)
                elif verdict in ("NO_CHANGE", "WRONG_STATE"):
                    m.command_outcome(cid, "FAIL", evidence[:200])
            if cmd_ids:
                out["command"] = cmd_ids[0]
                self._bust(key)
            if verdict == "PASS" and before_state is not None and after_state is not None:
                m.record_transition(key, before_state, f"{verb}:{target or goal}"[:120], effector or "judge", after_state, evidence[:300])
                out["transition"] = True
        except Exception as exc:
            logger.debug("[bridge] record failed: %s", exc)
        return out


_BRIDGE: Optional[KnowledgeBridge] = None


def get_bridge() -> KnowledgeBridge:
    global _BRIDGE
    if _BRIDGE is None:
        _BRIDGE = KnowledgeBridge()
    return _BRIDGE
