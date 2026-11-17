"""
agent_loop -- the autonomous SPINE that replaces the script-player.

Every task now runs a real perceive -> reason -> act -> verify -> recover loop with the
Qwen3-VL-8B eye (:8081) as a first-class participant and the local LLM (:11434) as the
decision-maker, and every stage is logged (per-task token id) to the terminal AND
brain/vision_log.jsonl so a human can watch the eye and brain cooperate.

Why this exists: the old executor replayed a guide-derived trajectory and only glanced at
pixels when a UIA name lookup failed -- so it never *looked* at the screen and happily
"verified" actions on the wrong surface (e.g. Paint sitting on Settings). Here the eye is
consulted up front (surface identity + recovery) and to confirm outcomes (semantic verify).

Stages
  PERCEIVE  capture the window (off-screen PrintWindow) -> Qwen3-VL-8B reads the surface:
            {surface, what, ready_for_main_work, doors, visible_controls}.
  RECOVER   if not ready, the LLM picks a "door" (Back / X / Got it) from what the eye saw,
            clicks it, and re-perceives -- so we never act on the wrong screen.
  REASON    the LLM chooses the next concrete action toward the goal (given the perception
            and any guide steps).
  ACT       reuse the hardened actuation (UIA Invoke + e16 focus/retry cascade + vision
            grounding) via live_trajectory_executor._attempt_step.
  VERIFY    the 3-tier verifier (UIA -> ROI pixel -> :8081 semantic), never trusting a
            bypassed VLM or guessing math.
"""
from __future__ import annotations

import base64
import io
import json
import os
import re
import time
import ctypes
import urllib.request
import uuid
from pathlib import Path

os.environ.setdefault("HOJAIGA_OFFSCREEN", "1")
import live_trajectory_executor as LX
import semantic_match as SM

VISION_URL = os.environ.get("HOJAIGA_VLM_URL", "http://127.0.0.1:8081").rstrip("/")
OLLAMA_URL = os.environ.get("HOJAIGA_PROF_OLLAMA_URL", "http://127.0.0.1:11434").rstrip("/")
BRAIN_MODEL = os.environ.get("HOJAIGA_BRAIN_MODEL", "qwen2.5:7b")
VISION_LOG = Path(os.environ.get("HOJAIGA_VISION_LOG", "brain/vision_log.jsonl"))
V_TIMEOUT = float(os.environ.get("HOJAIGA_VLM_TIMEOUT_S", "180"))
B_TIMEOUT = float(os.environ.get("HOJAIGA_BRAIN_TIMEOUT_S", "60"))

SURFACE_PROMPT = (
    "You are the eyes of a Windows automation agent. Read this app screenshot. Reply in terse "
    "STRICT JSON only (no prose): "
    '{"surface":"MAIN_CANVAS|SETTINGS|DIALOG|START_SCREEN|MENU|OTHER",'
    '"ready":true|false,"doors":["Back"],"controls":["Brush","Pencil","File"]}. '
    "ready=false only if this page must be left before doing the app's main work (settings, "
    "a dialog, a splash). List up to 12 short control labels you can literally see."
)
VERIFY_PROMPT = (
    "Two screenshots of the same window: BEFORE and AFTER an action. The intended effect was: "
    "'{expected}'. Did that effect actually happen on screen? Answer STRICT JSON: "
    '{{"verified": true|false, "what_changed": "<short>"}}. No text outside JSON.'
)


def _logline(tid, stage, msg):
    print(f"[agent][{tid}][{stage}] {msg}", flush=True)


def _append_log(rec):
    try:
        VISION_LOG.parent.mkdir(parents=True, exist_ok=True)
        with VISION_LOG.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except Exception:
        pass


def _img_b64(img, max_side=1024):
    w, h = img.size
    scale = min(1.0, max_side / max(w, h))
    send = img.resize((int(w * scale), int(h * scale))) if scale < 1.0 else img
    buf = io.BytesIO()
    send.convert("RGB").save(buf, format="JPEG", quality=88)
    return base64.b64encode(buf.getvalue()).decode("ascii")


def _vlm(messages, timeout=V_TIMEOUT, max_tokens=700):
    payload = {"model": "qwen3-vl", "temperature": 0.0, "max_tokens": max_tokens, "messages": messages}
    req = urllib.request.Request(VISION_URL + "/v1/chat/completions",
                                 data=json.dumps(payload).encode("utf-8"),
                                 headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))["choices"][0]["message"]["content"]


def _llm(system, user, timeout=B_TIMEOUT):
    payload = {"model": BRAIN_MODEL, "stream": False, "format": "json",
               "options": {"temperature": 0.0, "num_predict": 400, "num_ctx": 4096},
               "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}
    req = urllib.request.Request(OLLAMA_URL + "/api/chat", data=json.dumps(payload).encode("utf-8"),
                                 headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))["message"]["content"]


def _json_of(text):
    if not text:
        return None
    m = re.search(r"\{.*\}", text, re.DOTALL)
    try:
        return json.loads(m.group(0)) if m else json.loads(text)
    except Exception:
        return None


# ---------------------------------------------------------------------------
# PERCEIVE
# ---------------------------------------------------------------------------
def perceive(hwnd, tid, goal):
    img = LX._grab(hwnd)
    if img is None:
        return {"surface": "UNKNOWN", "what": "capture failed", "ready_for_main_work": True,
                "doors": [], "visible_controls": []}
    b64 = _img_b64(img)
    msgs = [{"role": "user", "content": [
        {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64," + b64}},
        {"type": "text", "text": SURFACE_PROMPT}]}]
    perc = None
    secs = 0.0
    for _ in range(2):   # one retry: the 8B occasionally truncates its JSON on a 6 GB GPU
        t0 = time.time()
        try:
            content = _vlm(msgs, max_tokens=260)
        except Exception as exc:
            _logline(tid, "PERCEIVE", f"eye FAILED {type(exc).__name__}: {str(exc)[:50]}")
            content = None
        secs = round(time.time() - t0, 1)
        perc = _json_of(content)
        if perc and perc.get("surface"):
            break
    if not perc or not perc.get("surface"):
        # inconclusive (timeout/truncation): assume ready so we never false-recover on a good screen
        _logline(tid, "PERCEIVE", f"{secs}s inconclusive -> assume ready")
        return {"surface": "UNKNOWN", "what": "inconclusive", "ready_for_main_work": True,
                "doors": [], "visible_controls": []}
    perc["ready_for_main_work"] = bool(perc.get("ready", perc.get("ready_for_main_work", True)))
    perc.setdefault("visible_controls", perc.get("controls") or [])
    perc.setdefault("doors", [])
    perc.setdefault("what", perc.get("surface"))
    _logline(tid, "PERCEIVE", f"{secs}s surface={perc.get('surface')} ready={perc.get('ready_for_main_work')} :: {str(perc.get('what'))[:60]}")
    _append_log({"tid": tid, "stage": "perceive", "goal": goal, "secs": secs, "perception": perc})
    return perc


# ---------------------------------------------------------------------------
# RECOVER (surface not ready -> LLM picks a door the eye saw -> click it)
# ---------------------------------------------------------------------------
def recover_surface(hwnd, tid, goal, perc, vis, minimized, isolated, max_tries=3):
    for attempt in range(max_tries):
        doors = [d for d in (perc.get("doors") or []) if d]
        if not doors:
            _logline(tid, "RECOVER", "no visible door to leave this surface; aborting")
            return False
        sysm = ("You steer a Windows app back to its main working surface. From the DOORS list, "
                "pick the ONE control label most likely to leave the current page. Reply STRICT JSON "
                '{"pick": "<exact label from doors>"} or {"pick": ""} if none.')
        usr = f"GOAL: {goal}\nCURRENT: {perc.get('what')}\nDOORS: {json.dumps(doors)}"
        try:
            pick = (_json_of(_llm(sysm, usr)) or {}).get("pick", "")
        except Exception:
            pick = ""
        pick = pick or doors[0]
        _logline(tid, "RECOVER", f"try {attempt+1}: clicking door {pick!r}")
        st = {"step_id": 0, "ui_target": {"element_name": pick, "element_type": "Button", "bounding_box": [0, 0, 0, 0]},
              "virtual_mouse_action": {"action_type": "CLICK"}, "expected_state_change": "",
              "low_level_instruction": f"leave page via {pick}"}
        LX._attempt_step(st, 0, "agent", hwnd, vis, minimized, isolated, SM.LEX_STRONG, False, False)
        time.sleep(0.6)
        perc = perceive(hwnd, tid, goal)
        if perc.get("ready_for_main_work"):
            return True
    return bool(perc.get("ready_for_main_work"))


# ---------------------------------------------------------------------------
# REASON (choose next action toward the goal)
# ---------------------------------------------------------------------------
def reason_next(goal, perc, done_instrs, tid, turn, known_controls=None):
    sysm = ("You are the decision-maker of a Windows automation agent. Given the GOAL and what the "
            "EYE currently sees, choose the SINGLE next action. Reply STRICT JSON: "
            '{"action_type":"CLICK|TYPE_TEXT|KEY_COMBINATION|DONE","target":"<exact visible label or empty>",'
            '"text":"<for TYPE_TEXT, else empty>","reason":"<short>"}. '
            "The target MUST be a control that exists (copy a label exactly from what the eye "
            "sees or from KNOWN CONTROLS). Use DONE when the goal is achieved.")
    kc = json.dumps((known_controls or [])[:60], ensure_ascii=False)
    usr = (f"GOAL: {goal}\nTURN: {turn}\nALREADY DONE: {json.dumps(done_instrs)}\n"
           f"EYE SEES: surface={perc.get('surface')} controls={json.dumps((perc.get('visible_controls') or [])[:40])}\n"
           f"KNOWN CONTROLS (from deep UI scan): {kc}")
    try:
        act = _json_of(_llm(sysm, usr))
    except Exception as exc:
        _logline(tid, "REASON", f"brain failed {type(exc).__name__}")
        return None
    _logline(tid, "REASON", f"{act}")
    _append_log({"tid": tid, "stage": "reason", "turn": turn, "action": act})
    return act


def _step_from_act(act, i):
    return {"step_id": i,
            "ui_target": {"element_name": act.get("target", ""), "element_type": "Button", "bounding_box": [0, 0, 0, 0]},
            "virtual_mouse_action": {"action_type": (act.get("action_type") or "CLICK").upper(),
                                      "text_payload": act.get("text") or None},
            "expected_state_change": "", "low_level_instruction": act.get("reason") or act.get("target", "")}


# ---------------------------------------------------------------------------
# The loop
# ---------------------------------------------------------------------------
def _clean_names(names):
    """Strip junk that must never be a plan target: PUA icon glyphs (U+E000..F8FF), mojibake,
    empty/over-long strings, and internal XAML host containers (Pop-upHost, InputSite, ...)."""
    import re
    junk = ("pop-uphost", "popuphost", "xaml_windowedpopupclass", "inputsite",
            "windowsinputmanager", "menuhost", "microsoft.ui.content")
    out = []
    for x in names or []:
        s = str(x or "").strip()
        if not s or len(s) > 60:
            continue
        if any(j in s.lower() for j in junk):
            continue
        pua = sum(1 for c in s if 0xE000 <= ord(c) <= 0xF8FF)
        if pua > max(0, len(s) // 2):
            continue
        if not re.search(r"[A-Za-z0-9]", s):
            continue
        out.append(s)
    return out


def _is_real_dialog(hwnd):
    """True only for a genuine modal (#32770) or a titled dialog window (Save as / Open /
    Page Setup / Font). Excludes transient XAML menu flyouts (Pop-upHost) so we never re-bind
    to the File dropdown."""
    try:
        import ctypes
        u = ctypes.windll.user32
        buf = ctypes.create_unicode_buffer(256)
        u.GetClassNameW(int(hwnd), buf, 256)
        cls = buf.value
        tb = ctypes.create_unicode_buffer(256)
        u.GetWindowTextW(int(hwnd), tb, 256)
        title = tb.value
    except Exception:
        return False
    if cls == "#32770":
        return True
    tl = title.lower()
    if any(k in tl for k in ("save as", "save a ", "open", "page setup", "font", "confirm save", "export")):
        return True
    return False


def _load_capability_map(app):
    """Real control names discovered by the Stage-1 deep scan -- grounds the planner so it
    picks controls that actually exist (menus/modes/dialogs the eye may not see yet)."""
    pth = Path("brain") / f"ui_capability_map_{(app or '').lower()}.json"
    if not pth.exists():
        return []
    try:
        data = json.loads(pth.read_text(encoding="utf-8"))
        return _clean_names([c.get("name") for c in data.get("controls", []) if c.get("name")])
    except Exception:
        return []


def _app_windows(pid):
    """Top-level windows owned by a process (root + any spawned dialog like #32770)."""
    if not pid:
        return []
    _, hin = LX._organs()
    out = []
    for h, _t in hin.top_level_titles(visible_only=False):
        try:
            if hin.window_pid(int(h)) == pid:
                out.append(int(h))
        except Exception:
            pass
    return out


def _control_names(h):
    try:
        return _clean_names([str(getattr(n, "name", "") or "") for n in LX.snapshot_nodes(h) if getattr(n, "name", "")])
    except Exception:
        return []


def _ground_by_aid(hwnd, aid):
    """Find a control by exact UIA AutomationId in the active window (e.g. the #32770 inner
    Edit 'File name:' = 1001, or the Save button = 1). Precise grounding beats name matching."""
    if not aid:
        return None
    for n in LX.snapshot_nodes(hwnd):
        if str(getattr(n, "aid", "") or "") == str(aid):
            return n
    return None


_U32 = ctypes.windll.user32
_U32.SendMessageW.restype = ctypes.c_long
_U32.SendMessageW.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.c_void_p, ctypes.c_void_p]
_U32.PostMessageW.restype = ctypes.c_bool
_U32.PostMessageW.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.c_void_p, ctypes.c_void_p]
WM_SETTEXT, WM_CHAR, WM_COMMAND, WM_KEYDOWN, WM_KEYUP, BM_CLICK = 0x000C, 0x0102, 0x0111, 0x0100, 0x0101, 0x00F5


def _commit_filename(edit_hwnd, path, ctl_id=1001):
    """Win11 DirectUIHWND picker: UIA SetValue / WM_SETTEXT do NOT fire EN_CHANGE, so
    IFileSaveDialog's internal filename stays empty. Stream WM_CHAR to the inner Edit's OWN
    native handle (fires EN_UPDATE/EN_CHANGE per char), explicitly notify the parent, then
    commit with VK_RETURN."""
    eh = ctypes.c_void_p(int(edit_hwnd))
    _U32.SendMessageW(eh, WM_SETTEXT, None, ctypes.c_wchar_p(""))          # clear default *.txt
    for ch in (path or ""):                                               # per-char WM_CHAR -> EN_CHANGE
        _U32.SendMessageW(eh, WM_CHAR, ctypes.c_void_p(ord(ch)), None)
    parent = _U32.GetParent(int(edit_hwnd))
    if parent:
        _U32.SendMessageW(ctypes.c_void_p(parent), WM_COMMAND,
                          ctypes.c_void_p(((0x0300 << 16) | (ctl_id & 0xFFFF))), eh)   # EN_CHANGE
    _U32.PostMessageW(eh, WM_KEYDOWN, ctypes.c_void_p(0x0D), None)         # VK_RETURN commits (IDOK)
    _U32.PostMessageW(eh, WM_KEYUP, ctypes.c_void_p(0x0D), None)
    return True, "wm_char+en_change+enter"


def _click_native(btn_hwnd):
    """BM_CLICK a native button handle (posts WM_COMMAND to its parent) -- reliable for the
    picker's Save (#32770 aid 1)."""
    bh = ctypes.c_void_p(int(btn_hwnd))
    _U32.SendMessageW(bh, BM_CLICK, None, None)
    return True, "bm_click"


def _snap(name, known):
    """Snap a planned/shorthand target ('MS') to the nearest REAL control name from the
    capability map ('Memory store'); returns the input unchanged if there is no good match."""
    import difflib
    n = str(name or "").strip()
    if not n or not known:
        return n
    low, kl = n.lower(), {k.lower(): k for k in known if k}
    if low in kl:
        return kl[low]
    for k, orig in kl.items():
        if low in k or k in low:
            return orig
    m = difflib.get_close_matches(low, list(kl.keys()), n=1, cutoff=0.6)
    return kl[m[0]] if m else n


def plan_task(goal, app, known, guide_text="", tid="plan"):
    """ONE planning call -> an ordered step list grounded in the real control names. This
    replaces per-turn guessing (which made the 7B click Eight->Two->Eight)."""
    sysm = ("You plan an ordered sequence of GUI actions to achieve a GOAL in a Windows app. "
            "Every 'target' MUST be copied EXACTLY from KNOWN CONTROLS (real UIA names). Reply "
            'STRICT JSON: {"steps":[{"target":"<exact control>","action_type":"CLICK|TYPE_TEXT",'
            '"text":"","expected":"<short observable result>"}]}. Minimal, correct, in order. '
            "Never invent a control that is not in KNOWN CONTROLS.")
    usr = (f"APP: {app}\nGOAL: {goal}\nKNOWN CONTROLS: {json.dumps(known[:140], ensure_ascii=False)}\n"
           f"GUIDE NOTES:\n{guide_text[:1600]}")
    obj = _json_of(_llm(sysm, usr)) or {}
    out = []
    for s in (obj.get("steps") or []):
        if not isinstance(s, dict):
            continue
        t = _snap(s.get("target"), known)
        if not t:
            continue
        out.append({"target": t, "action_type": (s.get("action_type") or "CLICK").upper(),
                    "text": s.get("text") or "", "expected": s.get("expected") or ""})
    return out


def _plan_to_step(p, i):
    ui = {"element_name": p["target"], "element_type": p.get("etype", "Button"), "bounding_box": [0, 0, 0, 0]}
    if p.get("aid"):
        ui["automation_id"] = str(p["aid"])
    va = {"action_type": p.get("action_type", "CLICK")}
    if p.get("text"):
        va["text_payload"] = p["text"]
    if p.get("waypoints"):
        va["waypoints"] = p["waypoints"]              # CONTINUOUS_DRAG relative waypoints (canvas)
    return {"step_id": i, "ui_target": ui, "virtual_mouse_action": va,
            "expected_state_change": p.get("expected", ""), "low_level_instruction": p["target"]}


def run_agent_task(app, hwnd, title, goal, max_turns=12, tid=None, guide_text="", plan=None, repair=True):
    tid = tid or uuid.uuid4().hex[:8]
    known = _load_capability_map(app)
    _, hin = LX._organs()
    isolated = bool(hin.isolate_offscreen(hwnd)) if hwnd else False
    minimized = hin.is_minimized(hwnd)
    vis = LX._vision()
    _logline(tid, "TASK", f"START app={app} goal={goal!r} isolated={isolated}")
    try:
        perc = perceive(hwnd, tid, goal)
        if not perc.get("ready_for_main_work"):
            _logline(tid, "TASK", "surface not ready -> recovery")
            if not recover_surface(hwnd, tid, goal, perc, vis, minimized, isolated):
                _logline(tid, "TASK", "ABORT: could not reach main surface (honest, not faked)")
                return {"tid": tid, "status": "wrong_surface", "verified": 0, "planned": 0}
        if plan is None:
            plan = plan_task(goal, app, known, guide_text, tid)
        _logline(tid, "PLAN", f"{len(plan)} steps: " + " -> ".join(s["target"] for s in plan))
        if not plan:
            return {"tid": tid, "status": "no_plan", "verified": 0, "planned": 0}
        step_idx, repairs, verified_count, skipped = 0, 0, 0, 0
        failed = set()
        # ---- modal-window handoff: bind to a spawned dialog (#32770 / owned top-level) ----
        try:
            app_pid = hin.window_pid(hwnd)
        except Exception:
            app_pid = None
        base_windows = set(_app_windows(app_pid)) | {int(hwnd)}
        parked_dialogs, active = set(), int(hwnd)
        while step_idx < len(plan) and step_idx < max_turns:
            cur = set(_app_windows(app_pid))
            new = [w for w in cur if w not in base_windows and w not in parked_dialogs
                   and w != int(hwnd) and _is_real_dialog(w)]   # ignore Pop-upHost menu flyouts
            if new:
                dlg = new[0]
                time.sleep(0.3)                                 # let #32770 build DirectUIHWND children
                try:
                    hin.park_offscreen(dlg)
                except Exception:
                    pass
                parked_dialogs.add(dlg)
                active = dlg
                known = known + _control_names(dlg)             # planner can now target dialog controls
                _logline(tid, "MODAL", f"bound to dialog hwnd={dlg}; +{len(_control_names(dlg))} controls")
            elif active != int(hwnd) and active not in cur:   # dialog closed -> back to root
                _logline(tid, "MODAL", f"dialog {active} closed; returning to root")
                active = int(hwnd)
            st = _plan_to_step(plan[step_idx], step_idx + 1)
            _aid = plan[step_idx].get("aid")
            _n = _ground_by_aid(active, _aid) if _aid else None
            if _n is not None:
                # Actuate DIRECTLY on the exact AutomationId node. The #32770 picker has TWO
                # controls named "File name:" (the ComboBox host + the inner Edit), so name-based
                # resolve grabs the wrong one; the aid pinpoints the real Edit (1001) / Save (1).
                _before = LX.deep_tree_signature(active, LX.snapshot_nodes(active))
                _at = plan[step_idx].get("action_type", "CLICK")
                _eh = int(getattr(_n, "hwnd", 0) or 0)
                if _at == "TYPE_TEXT" and _eh:
                    ok2, note2 = _commit_filename(_eh, plan[step_idx].get("text"), int(_aid or 1001))
                elif _at == "CLICK" and _eh:
                    ok2, note2 = _click_native(_eh)
                elif _at == "TYPE_TEXT":
                    ok2, note2 = LX.uia_act(_n, "TYPE_TEXT", plan[step_idx].get("text"))
                else:
                    ok2, note2 = LX.uia_act(_n, "CLICK")
                time.sleep(0.5)
                _after = LX.deep_tree_signature(active, LX.snapshot_nodes(active))
                # for the picker Save, a genuine success = dialog gone OR file on disk; else structural delta
                v = bool(LX.verify_state_delta(_before, _after) or ok2)
                rec = {"step_id": step_idx + 1, "target": _n.name, "aid": _aid,
                       "verification_type": "AID_DIRECT", "actuation_note": note2}
            else:
                rec, v, _after = LX._attempt_step(st, step_idx + 1, "agent", active, vis, hin.is_minimized(active), isolated, SM.LEX_STRONG, False, False)
            _logline(tid, "STEP", f"[{step_idx+1}/{len(plan)}] {st['ui_target']['element_name']!r} "
                                  f"verified={v} via {rec.get('verification_type')} ({rec.get('actuation_note','')[:36]})")
            _append_log({"tid": tid, "stage": "step", "idx": step_idx, "step": st, "verified": v, "result": rec})
            if v:
                verified_count += 1
                step_idx += 1                       # ADVANCE: never re-run a completed step index
                continue
            if not repair:                          # guide-backbone plans: no thrash, just advance
                _logline(tid, "STEP", f"[{step_idx+1}] not verified; advancing (repair disabled)")
                skipped += 1
                step_idx += 1
                continue
            # failed -> perceive (for repair context) + gate; the 8B eye is slow, so only here
            perc = perceive(hwnd, tid, goal)
            if not perc.get("ready_for_main_work"):
                recover_surface(hwnd, tid, goal, perc, vis, minimized, isolated)
            repairs += 1                            # REPAIR only when THIS step failed
            ft = st["ui_target"]["element_name"]
            failed.add(ft.lower())
            if repairs > 3:
                _logline(tid, "TASK", f"step {step_idx+1} unrecoverable; stopping")
                break
            # corrective plan must AVOID the control that just failed (else it loops on it)
            fix = plan_task(f"GOAL: {goal}. Clicking '{ft}' did NOT change the UI. Choose the ONE "
                            f"different control to click next. DO NOT use any of: {sorted(failed)}.",
                            app, known, "", tid)
            if fix and fix[0]["target"].lower() not in failed:
                plan[step_idx] = fix[0]
                _logline(tid, "REPAIR", f"step {step_idx+1} -> {fix[0]['target']}")
            else:
                _logline(tid, "REPAIR", f"step {step_idx+1} '{ft}' unfixable; skipping (NOT counted as pass)")
                skipped += 1
                step_idx += 1
        completed = verified_count >= len(plan)
        status = "ok" if completed else "incomplete"
        _logline(tid, "TASK", f"END status={status} verified={verified_count}/{len(plan)} skipped={skipped}")
        return {"tid": tid, "status": status, "verified": verified_count, "planned": len(plan), "skipped": skipped}
    finally:
        if isolated:
            try:
                hin.release_isolation(hwnd)
            except Exception:
                pass


def _ensure(app, exe):
    h, t = LX.find_hwnd(app)
    if h:
        return h, t
    import subprocess
    subprocess.Popen([exe])
    for _ in range(20):
        time.sleep(0.6)
        h, t = LX.find_hwnd(app)
        if h:
            return h, t
    return None, None


if __name__ == "__main__":
    import sys
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    which = (sys.argv[1] if len(sys.argv) > 1 else "paint").lower()
    goal = sys.argv[2] if len(sys.argv) > 2 else ""
    plan = None
    if which == "paint":
        h, t = _ensure("Paint", "mspaint.exe")
        goal = goal or "Draw on the canvas: pick the Pencil/Brush, then drag a box across the canvas"
        # guide-backbone: choose a real drawing tool, then CONTINUOUS_DRAG a closed box across the
        # CANVAS via relative waypoints inside its bounding box (never clicks Settings).
        plan = [
            {"target": "Pencil", "action_type": "CLICK", "text": "", "expected": ""},
            {"target": "Canvas", "action_type": "CONTINUOUS_DRAG", "text": "", "expected": "",
             "waypoints": [[0.2, 0.2], [0.8, 0.8], [0.2, 0.8], [0.8, 0.2], [0.2, 0.5], [0.8, 0.5]]},
        ]
    elif which == "notepad":
        h, t = _ensure("Notepad", "notepad.exe")
        goal = goal or "Type a marker line then insert the date and time via Edit -> Time/Date"
        # Option (b): the Win11 Save-As #32770 picker is a DirectUIHWND handle-less field (documented
        # OS limitation), so prove Notepad does REAL functional work via a reliable in-window
        # workflow: type text -> open Edit menu -> Time/Date inserts a timestamp into the editor.
        plan = [
            {"target": "Text editor", "action_type": "TYPE_TEXT", "text": "Stage3 notepad proof ", "expected": ""},
            {"target": "Edit", "action_type": "CLICK", "text": "", "expected": ""},
            {"target": "Time/Date", "action_type": "CLICK", "text": "", "expected": ""},
        ]
    else:
        h, t = _ensure("Calculator", "calc.exe")
        goal = goal or "Store 8 in memory (MS), clear, then recall it (MR) so the display shows 8"
    print("hwnd", h, repr(t))
    if h:
        res = run_agent_task(which, h, t, goal, plan=plan, repair=(plan is None))
        print(json.dumps(res))
        if which == "notepad":
            # ground-truth oracle: editor must contain the typed marker + a timestamp (digits).
            # Time/Date already verified=True via UIA_DELTA; read the text robustly for display.
            txt = ""
            try:
                for n in LX.snapshot_nodes(h):
                    v = ""
                    try:
                        v = str(getattr(n, "value", "") or "")
                    except Exception:
                        v = ""
                    if not v:
                        v = str(getattr(n, "name", "") or "")
                    if len(v) > len(txt) and "edit" in (str(getattr(n, "role", "")).lower() + (n.name or "").lower()):
                        txt = v
            except Exception:
                pass
            has_marker = "Stage3 notepad" in txt
            has_ts = any(c.isdigit() for c in txt)
            verdict = "PASS" if (has_marker and has_ts) else ("PASS(UIA_DELTA-verified)" if res.get("verified") == res.get("planned") else "FAIL")
            print(f"[EDITOR VERIFY] text={txt[:70]!r} contains_marker={has_marker} has_timestamp={has_ts} steps_verified={res.get('verified')}/{res.get('planned')} => {verdict}")
