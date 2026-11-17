"""
harvest.shortcut_verify -- does a shortcut READ OFF A TUTORIAL actually do something in the live app? A controlled experiment with screenshots, never a belief.

    python -m core_organs.harvest.shortcut_verify plan   --app webapp:excalidraw.com                   print the plan, touch nothing (no browser, no network)
    python -m core_organs.harvest.shortcut_verify run    --app webapp:excalidraw.com [--only "Zen mode" ...] [--url https://excalidraw.com]
    python -m core_organs.harvest.shortcut_verify promote --results reports/shortcut_verify/<stamp>/results.json     (separate step: marks the proven ones verified in the RAG)

How one shortcut is tested (the same protocol for all, nothing per-shortcut except the oracle words below):
  1. a FRESH page, clean storage, a known test scene (three overlapping shapes seeded through the app's own saved-scene format); the page is a headless Chromium with an empty profile:
     no window on the person's screen, not their Chrome, no cookies, keys are sent to the PAGE (browser protocol), never to Windows.
  2. a precondition ladder P0 nothing selected -> P1 one shape -> P2 two -> P3 three selected (a shortcut that needs a selection only shows its effect from there); a 'paste' step
     first runs its 'copy' sibling in the same session.
  3. a CONTROL run first (same preconditions, no key pressed): whatever changes by itself (autosave, animation, cursor blink) is noise and is subtracted.
  4. the chord is pressed; after it settles three independent kinds of evidence are compared with the control:
        dom       the accessibility tree text (which controls exist / are named what)
        pixel     the screenshot (fraction of the picture that changed and where)
        semantic  the app's own saved scene + settings (shapes, order, groups, locks, versions, app state) and the clipboard
  5. verdict:  VERIFIED  an effect beyond the noise AND the effect matches what the name says (an oracle keyed on the NAME's verb: duplicate, group, lock, copy, cut, paste, flip, order, zen...)
               EFFECT_ONLY  an effect beyond the noise, no oracle for that name -> the shortcut does something, WHAT is not confirmed
               MISMATCH  an effect, but the oracle says it is not what the name claims
               NO_EFFECT  nothing beyond the noise on any rung of the ladder
               ENV_BLOCKED  the page could not be loaded
  Every attempt saves before / after / control-after / marked-up difference pictures and a sha256 manifest. `run` never writes to the RAG; `promote` is a separate command and only
  touches rows whose verdict is VERIFIED.
"""
from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import os
import re
import sys
import time
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

import numpy as np

ROOT = os.path.dirname(os.environ.get("HOJAIGA_DATA", os.path.join("D:" + os.sep, "new_automation", "data")))
OUT_ROOT = os.path.join(ROOT, "reports", "shortcut_verify")
VIEWPORT = (1280, 800)
SETTLE_S = 0.8
PIXEL_MIN_FRAC = 0.0015                 # share of the picture that must change (beyond the control) to count as a visible effect
PIXEL_NOISE_FRAC = 0.0005               # a control run that changes more than this makes the pixel tier unusable for that attempt

SCENE = [  # three overlapping filled rectangles at a known place: (x, y, w, h, fill)
    (200, 200, 220, 140, "#ffc9c9"),
    (320, 260, 220, 140, "#a5d8ff"),
    (480, 420, 220, 140, "#b2f2bb"),
]
CLICK_AT = [(260, 230), (330, 370), (600, 520)]      # a point inside each shape that is not covered by a later one


# ------------------------------------------------------------------------------------------------------------------ chords
_KEYNAME = {"/": "Slash", "]": "BracketRight", "[": "BracketLeft", ",": "Comma", ".": "Period", "-": "Minus", "=": "Equal", ";": "Semicolon", "'": "Quote", "\\": "Backslash",
            "enter": "Enter", "return": "Enter", "esc": "Escape", "escape": "Escape", "tab": "Tab", "space": "Space", "delete": "Delete", "backspace": "Backspace",
            "up": "ArrowUp", "down": "ArrowDown", "left": "ArrowLeft", "right": "ArrowRight"}
_MODNAME = {"ctrl": "Control", "alt": "Alt", "shift": "Shift", "win": "Meta", "meta": "Meta", "cmd": "Control", "option": "Alt"}


def playwright_chord(chord: str) -> str:
    """'ctrl+alt+]' -> 'Control+Alt+BracketRight' (key CODES, so a shifted key is the same key)."""
    out = []
    for part in [p for p in chord.lower().split("+") if p] or []:
        if part in _MODNAME:
            out.append(_MODNAME[part])
        elif part in _KEYNAME:
            out.append(_KEYNAME[part])
        elif re.fullmatch(r"[a-z]", part):
            out.append("Key" + part.upper())
        elif re.fullmatch(r"[0-9]", part):
            out.append("Digit" + part)
        elif re.fullmatch(r"f\d{1,2}", part):
            out.append(part.upper())
        else:
            out.append(part)
    if chord.endswith("++"):                                            # a literal '+' key
        out.append("Equal")
    return "+".join(out)


# ------------------------------------------------------------------------------------------------------------------ seeding and summaries
def seed_elements() -> List[Dict[str, Any]]:
    els = []
    for i, (x, y, w, h, fill) in enumerate(SCENE):
        els.append({"id": f"vtest{i}", "type": "rectangle", "x": x, "y": y, "width": w, "height": h, "angle": 0, "strokeColor": "#1e1e1e", "backgroundColor": fill, "fillStyle": "solid",
                    "strokeWidth": 2, "strokeStyle": "solid", "roughness": 1, "opacity": 100, "groupIds": [], "frameId": None, "roundness": {"type": 3}, "seed": 1000 + i, "version": 1,
                    "versionNonce": 2000 + i, "isDeleted": False, "boundElements": None, "updated": 1, "link": None, "locked": False})
    return els


def scene_summary(elements_json: str, state_json: str = "") -> Dict[str, Any]:
    """What the app saved, reduced to what a shortcut can change."""
    els, state = [], {}
    with contextlib.suppress(Exception):
        els = json.loads(elements_json or "[]")
    with contextlib.suppress(Exception):
        state = json.loads(state_json or "{}")
    live = [e for e in els if not e.get("isDeleted")]
    groups = {}
    for e in live:
        for g in e.get("groupIds") or []:
            groups.setdefault(g, []).append(e["id"])
    return {"n": len(live), "deleted": len(els) - len(live), "order": [e["id"] for e in els],
            "geom": {e["id"]: [round(e.get("x", 0), 1), round(e.get("y", 0), 1), round(e.get("width", 0), 1), round(e.get("height", 0), 1), round(e.get("angle", 0), 3)] for e in live},
            "style": {e["id"]: [e.get("strokeColor"), e.get("backgroundColor"), e.get("strokeWidth"), e.get("opacity"), e.get("roughness")] for e in live},
            "version": {e["id"]: e.get("version", 0) for e in live}, "locked": sorted(e["id"] for e in live if e.get("locked")),
            "groups": {g: sorted(v) for g, v in groups.items() if len(v) >= 2}, "state": {k: state[k] for k in sorted(state) if isinstance(state[k], (bool, int, float, str, type(None)))}}


def diff_scene(a: Dict[str, Any], b: Dict[str, Any]) -> Dict[str, Any]:
    d: Dict[str, Any] = {}
    if a["n"] != b["n"]:
        d["count"] = [a["n"], b["n"]]
    if a["deleted"] != b["deleted"]:
        d["deleted"] = [a["deleted"], b["deleted"]]
    if a["order"] != b["order"]:
        d["order"] = [a["order"], b["order"]]
    for key in ("geom", "style", "version"):
        ch = [i for i in b[key] if a[key].get(i) != b[key][i] and i in a[key]]
        if ch:
            d[key] = ch
    if a["locked"] != b["locked"]:
        d["locked"] = [a["locked"], b["locked"]]
    if sorted(map(tuple, a["groups"].values())) != sorted(map(tuple, b["groups"].values())):
        d["groups"] = [sorted(map(list, a["groups"].values())), sorted(map(list, b["groups"].values()))]
    sk = [k for k in set(a["state"]) | set(b["state"]) if a["state"].get(k) != b["state"].get(k) and k not in ("scrolledOutside",)]
    if sk:
        d["state"] = {k: [a["state"].get(k), b["state"].get(k)] for k in sk}
    return d


def pixel_delta(a: np.ndarray, b: np.ndarray) -> Dict[str, Any]:
    """Fraction of the picture that changed and the box around it (both pictures the same size)."""
    import cv2
    ga, gb = (cv2.cvtColor(x, cv2.COLOR_BGR2GRAY) if x.ndim == 3 else x for x in (a, b))
    if ga.shape != gb.shape:
        gb = cv2.resize(gb, (ga.shape[1], ga.shape[0]))
    m = (cv2.absdiff(cv2.GaussianBlur(ga, (3, 3), 0), cv2.GaussianBlur(gb, (3, 3), 0)) > 25)
    frac = float(m.mean())
    box = None
    if m.any():
        ys, xs = np.where(m)
        box = [int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max())]
    return {"frac": round(frac, 5), "box": box}


def aria_delta(a: str, b: str) -> Dict[str, Any]:
    la, lb = [l.strip() for l in a.splitlines() if l.strip()], [l.strip() for l in b.splitlines() if l.strip()]
    sa, sb = set(la), set(lb)
    return {"removed": len(sa - sb), "added": len(sb - sa), "lines": [len(la), len(lb)], "removed_sample": sorted(sa - sb)[:4], "added_sample": sorted(sb - sa)[:4]}


# ------------------------------------------------------------------------------------------------------------------ oracles: what a NAME promises, keyed on the name's words
def _words(action: str) -> set:
    return set(re.findall(r"[a-z]+", (action or "").lower()))


def oracle(action: str, ev: Dict[str, Any]) -> Optional[bool]:
    """True / False when the name's verb has a checkable meaning, None when it has not. `ev` = {scene: diff, before: summary, after: summary, aria: delta, pixel: delta, clip_after, clip_before}."""
    w = _words(action)
    sd, aft, bef = ev["scene"], ev["after"], ev["before"]
    sel = list(ev.get("selected", []))
    if w & {"duplicate"}:
        return aft["n"] == bef["n"] + 1
    if "ungroup" in w:
        return len(aft["groups"]) < len(bef["groups"])
    if "group" in w:
        return len(aft["groups"]) > len(bef["groups"])
    if "lock" in w and "all" in w:
        return len(aft["locked"]) == aft["n"] > 0
    if "lock" in w:
        return len(aft["locked"]) > len(bef["locked"])
    if "cut" in w:
        return (aft["n"] < bef["n"] or aft["deleted"] > bef["deleted"]) and bool(ev["clip_after"].get("any"))
    if ("copy" in w and bool(w & {"png", "svg"})) or "copytoclipboardaspng" in w:
        return bool(ev["clip_after"].get("image") or ev["clip_after"].get("any"))
    if "copy" in w and "styles" not in w:                          # copying NOTHING still writes an empty clipboard payload: only a copy of a selection proves the shortcut copies
        return bool(sel) and bool(ev["clip_after"].get("any")) and aft["n"] == bef["n"]
    if "paste" in w and "styles" in w:
        return bool(sd.get("style"))
    if "paste" in w:
        return aft["n"] == bef["n"] + 1
    if "flip" in w:
        return bool(sd.get("version") or sd.get("geom"))
    if bool(w & {"forward", "front", "backward", "back"}) and bool(w & {"bring", "send"}):
        live_b = [i for i in bef["order"] if i in bef["geom"]]
        live_a = [i for i in aft["order"] if i in aft["geom"]]
        if not sd.get("order") or not sel or not all(i in live_a for i in sel):
            return bool(sd.get("order")) if not sel else False
        n = len(live_a)
        if len(sel) != 1:                                           # with several shapes selected 'one place up' and 'to the front' can look the same (2 of 3 selected, moved up one = at the top): only a SINGLE shape's final position tells them apart, the other rungs cannot judge and must not pass
            return None
        pb, pa = [live_b.index(i) for i in sel if i in live_b], [live_a.index(i) for i in sel]
        if len(sel) == 1:                                         # one shape: the exact place it ends up tells FRONT from FORWARD
            if "front" in w:
                return pa[0] == n - 1
            if "back" in w and "backward" not in w:
                return pa[0] == 0
            if "forward" in w:
                return pa[0] == pb[0] + 1
            return pa[0] == pb[0] - 1
        if "front" in w:
            return sorted(pa) == list(range(n - len(sel), n))
        if "back" in w and "backward" not in w:
            return sorted(pa) == list(range(len(sel)))
        return pa != pb
    if "select" in w and "all" in w:
        px = ev["pixel"]
        return bool(px.get("box")) and px["frac"] > 0.0
    if "zen" in w or ("view" in w and "mode" in w):
        return ev["aria"]["removed"] > ev["aria"]["added"] or (ev["pixel"]["frac"] >= 0.01)
    flipped = sd.get("state") or {}
    words = [x for x in w if len(x) >= 4 and x not in {"mode", "show", "toggle", "enable", "objects"}] or [x for x in w if len(x) >= 4]
    if flipped and any(x in re.sub(r"[^a-z]", "", k.lower()) for k in flipped for x in words):
        return True                                                    # a setting named like the action flipped in the app's own saved state
    return None


# ------------------------------------------------------------------------------------------------------------------ drivers
class PlaywrightDriver:
    """One headless Chromium with an empty profile. Keys go to the page through the browser protocol."""

    def __init__(self, url: str, headless: bool = True):
        from playwright.sync_api import sync_playwright
        self._pw = sync_playwright().start()
        self.browser = self._pw.chromium.launch(headless=headless)
        self.url = url
        self.ctx = self.browser.new_context(viewport={"width": VIEWPORT[0], "height": VIEWPORT[1]}, permissions=["clipboard-read", "clipboard-write"])
        self.page = None

    def load(self, elements: Sequence[Dict[str, Any]]) -> None:
        if self.page:
            self.page.close()
        self.page = self.ctx.new_page()
        seed = json.dumps(list(elements))
        self.page.add_init_script(f"try{{localStorage.setItem('excalidraw', {json.dumps(seed)});localStorage.removeItem('excalidraw-state');}}catch(e){{}}")
        self.page.goto(self.url, wait_until="domcontentloaded", timeout=45000)
        self.page.wait_for_selector("canvas", timeout=30000)
        time.sleep(2.0)

    def click(self, x: int, y: int, shift: bool = False) -> None:
        if shift:
            self.page.keyboard.down("Shift")
        self.page.mouse.click(x, y)
        if shift:
            self.page.keyboard.up("Shift")
        time.sleep(0.3)

    def press(self, chord: str) -> None:
        self.page.keyboard.press(playwright_chord(chord))

    def wait(self, s: float) -> None:
        time.sleep(s)

    def screenshot(self) -> np.ndarray:
        import cv2
        return cv2.imdecode(np.frombuffer(self.page.screenshot(type="png"), np.uint8), cv2.IMREAD_COLOR)

    def aria(self) -> str:
        with contextlib.suppress(Exception):
            return self.page.locator("body").aria_snapshot()
        return ""

    def scene(self) -> Dict[str, Any]:
        raw = self.page.evaluate("[localStorage.getItem('excalidraw'), localStorage.getItem('excalidraw-state')]")
        return scene_summary(raw[0] or "[]", raw[1] or "{}")

    def clipboard(self) -> Dict[str, Any]:
        with contextlib.suppress(Exception):
            return self.page.evaluate("""async () => { try { const items = await navigator.clipboard.read(); const types = []; for (const it of items) for (const t of it.types) types.push(t);
                 let text = ''; try { text = await navigator.clipboard.readText(); } catch (e) {} let h = 0; for (let i = 0; i < text.length; i++) h = (h * 31 + text.charCodeAt(i)) | 0;
                 const img = types.some(t => t.startsWith('image/')); return {types, text_len: text.length, image: img, any: (img || text.length > 0), sig: types.join(',') + ':' + text.length + ':' + h}; } catch (e) { return {error: String(e), any: false}; } }""")
        return {"any": False}

    def clear_clipboard(self) -> None:
        with contextlib.suppress(Exception):
            self.page.evaluate("async () => { try { await navigator.clipboard.writeText(''); } catch (e) {} }")

    def close(self) -> None:
        with contextlib.suppress(Exception):
            self.browser.close()
        with contextlib.suppress(Exception):
            self._pw.stop()


# ------------------------------------------------------------------------------------------------------------------ the experiment
def _sha(path: str) -> str:
    return hashlib.sha256(open(path, "rb").read()).hexdigest()


def _save(img: np.ndarray, path: str, box: Optional[Sequence[int]] = None, label: str = "") -> str:
    import cv2
    im = img.copy()
    if box:
        cv2.rectangle(im, (box[0] - 2, box[1] - 2), (box[2] + 2, box[3] + 2), (0, 0, 255), 3)
    if label:
        cv2.rectangle(im, (0, 0), (im.shape[1], 22), (0, 0, 0), -1)
        cv2.putText(im, label[:120], (6, 16), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    cv2.imencode(".png", im)[1].tofile(path)
    return path


LADDER = [("P0 nothing selected", []), ("P1 one shape selected", [0]), ("P2 two shapes selected", [0, 1]), ("P3 three shapes selected", [0, 1, 2])]


def _prepare(drv: Any, selected: Sequence[int], prerequisite: Optional[str]) -> bool:
    # (the clipboard belongs to the whole browser: it is emptied after every load, or a copy from an earlier attempt would hide - or fake - this one)
    """Fresh page, the test scene, the shapes of this rung selected, the prerequisite chord pressed. Returns whether the selection was SEEN (the accessibility text changed when the
    shapes were clicked): a click that missed would make a P1..P3 rung meaningless, and the proof says so instead of hiding it."""
    drv.load(seed_elements())
    if hasattr(drv, "clear_clipboard"):
        drv.clear_clipboard()
    loaded = drv.aria()
    for k, i in enumerate(selected):
        drv.click(*CLICK_AT[i], shift=k > 0)
    seen = (not selected) or (drv.aria() != loaded)
    if prerequisite:
        drv.press(prerequisite)
        drv.wait(SETTLE_S)
    return seen


def attempt(drv: Any, fact: Dict[str, Any], rung: Tuple[str, List[int]], prerequisite: Optional[str], out_dir: str, tag: str) -> Dict[str, Any]:
    """One rung: control run, then the chord run, evidence compared. Pictures saved under out_dir."""
    name, sel = rung
    chord = fact["windows"]
    # CONTROL: identical preparation, no key
    _prepare(drv, sel, prerequisite)
    c_before, c_scene, c_aria = drv.screenshot(), drv.scene(), drv.aria()
    drv.wait(SETTLE_S)
    c_after, c_scene2, c_aria2 = drv.screenshot(), drv.scene(), drv.aria()
    noise = {"pixel": pixel_delta(c_before, c_after), "scene": diff_scene(c_scene, c_scene2), "aria": aria_delta(c_aria, c_aria2)}
    # EXPERIMENT
    selection_seen = _prepare(drv, sel, prerequisite)
    before, s_before, a_before, clip_before = drv.screenshot(), drv.scene(), drv.aria(), drv.clipboard()
    drv.press(chord)
    drv.wait(SETTLE_S)
    after, s_after, a_after, clip_after = drv.screenshot(), drv.scene(), drv.aria(), drv.clipboard()
    px, ad, sd = pixel_delta(before, after), aria_delta(a_before, a_after), diff_scene(s_before, s_after)
    noisy_px = noise["pixel"]["frac"] > PIXEL_NOISE_FRAC
    tiers = {"pixel": (px["frac"] >= PIXEL_MIN_FRAC and not noisy_px), "dom": (ad["removed"] + ad["added"] > 0 and (noise["aria"]["removed"] + noise["aria"]["added"]) == 0),
             "semantic": (bool(sd) and not noise["scene"]) or bool(clip_after.get("any") and clip_after.get("sig") != clip_before.get("sig"))}
    ev = {"scene": sd, "before": s_before, "after": s_after, "aria": ad, "pixel": px, "clip_after": clip_after, "clip_before": clip_before, "selected": [f"vtest{i}" for i in sel]}
    name_ok = oracle(fact["action"], ev)
    base = os.path.join(out_dir, tag)
    files = {"before": _save(before, base + "_before.png", label=f"{fact['action']} [{chord}] {name}: BEFORE"),
             "control_after": _save(c_after, base + "_control_after.png", label=f"{name}: CONTROL (no key) after {SETTLE_S}s"),
             "after": _save(after, base + "_after.png", px["box"], f"{fact['action']} [{chord}] {name}: AFTER (red = changed region)")}
    return {"rung": name, "selection_seen": selection_seen, "tiers": tiers, "effect": any(tiers.values()), "name_check": name_ok, "pixel": px, "dom": ad, "scene_diff": {k: (v if not isinstance(v, list) or len(str(v)) < 300 else str(v)[:300]) for k, v in sd.items()},
            "clipboard_after": clip_after, "noise": noise, "files": {k: os.path.basename(v) for k, v in files.items()}, "hashes": {k: _sha(v) for k, v in files.items()}}


def prerequisite_for(fact: Dict[str, Any], facts: Sequence[Dict[str, Any]]) -> Optional[str]:
    """A 'paste ...' needs its 'copy ...' sibling first in the same session: the chord of the fact whose action starts with 'copy' and shares the rest of the words."""
    w = _words(fact["action"])
    if "paste" not in w:
        return None
    rest = w - {"paste"}
    for f in facts:
        fw = _words(f["action"])
        if "copy" in fw and (fw - {"copy"}) == rest:
            return f["windows"]
    return None


def chord_variants(fact: Dict[str, Any]) -> List[str]:
    """Other Windows forms worth trying when the direct translation of a MAC chord fails: apps often put on Shift what the Mac puts on Option (cmd+option+] on Mac is ctrl+shift+] on Windows)."""
    if not fact.get("mac_style"):
        return []
    parts = fact["windows"].split("+")
    if "alt" in parts and "shift" not in parts:
        return ["+".join("shift" if p == "alt" else p for p in parts)]
    return []


def verify_fact(drv: Any, fact: Dict[str, Any], facts: Sequence[Dict[str, Any]], out_dir: str, ladder: Sequence[Tuple[str, List[int]]] = LADDER, log: Callable[[str], None] = print) -> Dict[str, Any]:
    res = _verify_one(drv, fact, facts, out_dir, ladder, log)
    if res["verdict"] in ("MISMATCH", "NO_EFFECT"):
        for k, alt in enumerate(chord_variants(fact)):
            r2 = _verify_one(drv, dict(fact, windows=alt, action=fact["action"], _tag=f"v{k + 1}"), facts, out_dir, ladder, log)
            if r2["verdict"] == "VERIFIED":
                r2.update({"chord_from_video": fact["windows"], "variant_of": fact["windows"], "first_try": {"chord": fact["windows"], "verdict": res["verdict"]}})
                return r2
    return res


def _verify_one(drv: Any, fact: Dict[str, Any], facts: Sequence[Dict[str, Any]], out_dir: str, ladder: Sequence[Tuple[str, List[int]]] = LADDER, log: Callable[[str], None] = print) -> Dict[str, Any]:
    slug = re.sub(r"[^a-z0-9]+", "_", fact["action"].lower()).strip("_")[:40] + (("_" + fact["_tag"]) if fact.get("_tag") else "")
    pre = prerequisite_for(fact, facts)
    attempts = []
    verdict, used = "NO_EFFECT", None
    mismatch = effect_only = None
    for k, rung in enumerate(ladder):
        try:
            a = attempt(drv, fact, rung, pre, out_dir, f"{slug}_{k}")
        except Exception as exc:                                                    # a page that cannot be driven is an environment problem, not a verdict about the shortcut
            attempts.append({"rung": rung[0], "error": f"{type(exc).__name__}: {str(exc)[:160]}"})
            verdict = "ENV_BLOCKED"
            break
        attempts.append(a)
        if not a["effect"]:
            continue
        if a["name_check"] is True:
            verdict, used = "VERIFIED", a
            break
        if a["name_check"] is False:
            mismatch = mismatch or a
        else:
            effect_only = effect_only or a
            if mismatch is None:                                                    # the name has no checkable meaning: more rungs would learn nothing
                break
    if verdict != "VERIFIED" and verdict != "ENV_BLOCKED":
        if mismatch is not None:
            verdict, used = "MISMATCH", mismatch
        elif effect_only is not None:
            verdict, used = "EFFECT_ONLY", effect_only
    log(f"  {fact['action']:<28} {fact['windows']:<14} -> {verdict}" + (f" ({used['rung']})" if used else ""))
    return {"action": fact["action"], "chord": fact["windows"], "shown_as": fact.get("chord"), "authors": fact.get("videos"), "prerequisite": pre, "verdict": verdict,
            "rung": used["rung"] if used else None, "attempts": attempts}


def run(app_key: str, url: str, only: Sequence[str] = (), driver_factory: Optional[Callable[[], Any]] = None, out_root: str = "", log: Callable[[str], None] = print) -> Dict[str, Any]:
    from core_organs.harvest import consolidate as C
    g = C.AppGraph.load(app_key)
    facts = g.facts()
    if only:
        keep = [o.lower() for o in only]
        facts = [f for f in facts if any(k in f["action"].lower() for k in keep)]
    stamp = time.strftime("%Y%m%d_%H%M%S")
    out_dir = os.path.join(out_root or OUT_ROOT, stamp)
    os.makedirs(out_dir, exist_ok=True)
    drv = (driver_factory or (lambda: PlaywrightDriver(url)))()
    results = []
    t0 = time.time()
    try:
        for f in facts:
            results.append(verify_fact(drv, f, g.facts(), out_dir, log=log))
    finally:
        drv.close()
    from collections import Counter
    summary = dict(Counter(r["verdict"] for r in results))
    rep = {"app_key": app_key, "url": url, "when": stamp, "seconds": round(time.time() - t0, 1), "summary": summary, "results": results}
    json.dump(rep, open(os.path.join(out_dir, "results.json"), "w", encoding="utf-8"), indent=1, default=str)
    write_markdown(rep, out_dir)
    return dict(rep, out_dir=out_dir)


def write_markdown(rep: Dict[str, Any], out_dir: str) -> str:
    md = [f"# Shortcut verification: `{rep['app_key']}` ({rep['url']})", "", f"{len(rep['results'])} shortcuts, {rep['seconds']} s. Verdicts: {rep['summary']}", "",
          "VERIFIED = an effect beyond the control's noise AND the effect matches the name. EFFECT_ONLY = it does something, what is not confirmed. MISMATCH / NO_EFFECT = do NOT promote.", ""]
    for r in rep["results"]:
        md.append(f"## {r['action']} - `{r['chord']}` (shown as `{r['shown_as']}` by {r['authors']} authors): **{r['verdict']}**")
        if r.get("prerequisite"):
            md.append(f"- needs `{r['prerequisite']}` first (its copy sibling)")
        for a in r["attempts"]:
            if "error" in a:
                md.append(f"- {a['rung']}: ERROR {a['error']}")
                continue
            md.append(f"- {a['rung']}{'' if a.get('selection_seen', True) else ' (SELECTION NOT SEEN: the click may have missed)'}: tiers {a['tiers']}, name check {a['name_check']}, pixel {a['pixel']['frac']:.4f}, dom -{a['dom']['removed']}/+{a['dom']['added']}, scene {list(a['scene_diff'])}")
            if a["effect"] or a is r["attempts"][-1]:
                base = a["files"]["after"].rsplit("_after.png", 1)[0]
                md.append(f"  ![before]({base}_before.png) ![control]({base}_control_after.png) ![after]({base}_after.png)")
        md.append("")
    path = os.path.join(out_dir, "report.md")
    open(path, "w", encoding="utf-8").write("\n".join(md))
    return path


def plan(app_key: str, only: Sequence[str] = ()) -> Dict[str, Any]:
    """What `run` would do. No browser, no network."""
    from core_organs.harvest import consolidate as C
    g = C.AppGraph.load(app_key)
    facts = g.facts()
    if only:
        facts = [f for f in facts if any(k.lower() in f["action"].lower() for k in only)]
    rows = [{"action": f["action"], "press": playwright_chord(f["windows"]), "authors": f["videos"], "shown_as": f["chord"], "needs_first": prerequisite_for(f, g.facts())} for f in facts]
    return {"app_key": app_key, "shortcuts": len(rows), "ladder": [r[0] for r in LADDER], "attempts_max": len(rows) * len(LADDER) * 2, "est_minutes": round(len(rows) * 4 * 2 * 4.5 / 60, 1), "rows": rows}


def promote(results_path: str, rag: Any, only_verified: bool = True) -> Dict[str, Any]:
    """Mark the proven shortcuts proven IN PLACE: the row the harvest wrote is found (app + goal + payload) and set verified through the store's own overlay (no duplicate row, same id).
    A shortcut whose proven chord differs from the one the video showed (variant) gets its proven row (found or created), and the video's row is annotated REFUTED and left unverified.
    Only VERIFIED verdicts act. A promoted.json with the row ids and the proof pictures is written next to results.json."""
    from core_organs.harvest import bridge as BR
    rep = json.load(open(results_path, encoding="utf-8"))
    folder, key, when = os.path.dirname(results_path), rep["app_key"], rep["when"]
    run_id = f"shortcut_verify:{when}"
    out: Dict[str, Any] = {"promoted": 0, "in_place": 0, "inserted_new": 0, "refuted_rows_annotated": 0, "skipped": 0}
    proof: List[Dict[str, Any]] = []
    for r in rep["results"]:
        if r["verdict"] != "VERIFIED":
            out["skipped"] += 1
            continue
        kind, payload = BR.norm_keys(r["chord"])
        row = rag.fast.find(key, r["action"], payload)
        if row:
            rag.fast.set_verified(row["fast_id"], True, run_id)
            out["in_place"] += 1
        else:
            hit = rag.lex.best(key, r["action"])
            rag.fast.upsert([{"app_key": key, "kind": kind, "command_id": hit.command_id if hit else "", "task_pattern": r["action"], "payload": payload, "source": "web_table", "trust": "web",
                              "verified": True, "context": f"verified live {when}; proof {folder}", "params_schema_json": BR.infer_schema(payload)}])
            row = rag.fast.find(key, r["action"], payload)
            if row and hasattr(rag.fast, "set_verified"):
                rag.fast.set_verified(row["fast_id"], True, run_id)             # the new row carries the same overlay (trust 'verified', this run as its first ok run)
            out["inserted_new"] += 1
        out["promoted"] += 1
        last = next((a for a in r["attempts"] if a.get("effect") and a.get("name_check") is True), {})
        proof.append({"fast_id": (row or {}).get("fast_id", ""), "action": r["action"], "chord": r["chord"], "rung": r["rung"], "pictures": list((last.get("files") or {}).values())})
        if r.get("variant_of"):
            k2, p2 = BR.norm_keys(r["variant_of"])
            old = rag.fast.find(key, r["action"], p2)
            if old:
                rag.fast.annotate(old["fast_id"], f"REFUTED live {when}: {r['variant_of']} does not do '{r['action']}' on this platform; {r['chord']} does. proof {folder}")
                rag.fast.set_verified(old["fast_id"], False)
                out["refuted_rows_annotated"] += 1
    with contextlib.suppress(Exception):
        json.dump({"run": run_id, "app_key": key, "promoted": proof}, open(os.path.join(folder, "promoted.json"), "w", encoding="utf-8"), indent=1)
    return out


def export_training_rows(results_path: str, out_jsonl: str = "", som_fn: Optional[Callable[..., Dict[str, Any]]] = None, root: str = "") -> Dict[str, Any]:
    """Turn every LIVE-VERIFIED shortcut into one training row for the vision model, in the shape the other rows use (picture + Set-of-Marks list + goal -> JSON action): the picture is the page as
    it was BEFORE the key, the answer is the hotkey that was proven to work on it. These are the opposite of synthetic template rows: a person could check each one against its proof pictures.
    Written to its own file (default data/ai_root/harvest/training/video_verified_rows.jsonl), never into the main dataset; a row already written (same pair id) is skipped."""
    from core_organs.harvest import video_explain as VE, video_pipeline as VP
    from core_organs.harvest.paths import harvest_dir
    som_fn = som_fn or VP.som_of_frame
    rep = json.load(open(results_path, encoding="utf-8"))
    folder = os.path.dirname(results_path)
    root = root or harvest_dir()[0]
    out_jsonl = out_jsonl or os.path.join(root, "training", "video_verified_rows.jsonl")
    os.makedirs(os.path.dirname(out_jsonl), exist_ok=True)
    seen = set()
    if os.path.isfile(out_jsonl):
        for l in open(out_jsonl, encoding="utf-8"):
            with contextlib.suppress(Exception):
                seen.add(json.loads(l).get("meta", {}).get("pair_id"))
    rows, skipped = [], {"not_verified": 0, "no_picture": 0, "duplicate": 0, "sparse": 0}
    for r in rep["results"]:
        if r["verdict"] != "VERIFIED":
            skipped["not_verified"] += 1
            continue
        a = next((x for x in r["attempts"] if x.get("effect") and x.get("name_check") is True), None)
        pre = os.path.join(folder, (a or {}).get("files", {}).get("before", ""))
        post = os.path.join(folder, (a or {}).get("files", {}).get("after", ""))
        if not a or not os.path.isfile(pre):
            skipped["no_picture"] += 1
            continue
        pid = hashlib.sha1(f"sv|{rep['app_key']}|{r['action']}|{r['chord']}|{rep['when']}".encode()).hexdigest()[:16]
        if pid in seen:
            skipped["duplicate"] += 1
            continue
        som = som_fn(pre)
        if len(som.get("elements", [])) < 1:
            skipped["sparse"] += 1
            continue
        box = (a.get("pixel") or {}).get("box")
        action = {"step": 1, "action": "hotkey", "target_id": None, "hotkey": r["chord"], "text": None,
                  "verify_expectation": f"the screen changes in the region {box}" if box else "the app's saved state changes"}
        ev = {"pre": pre, "post": post if os.path.isfile(post) else "", "t": 0.0, "bbox": box}
        rows.append(VE.build_row(root, rep["app_key"], "live-verified", ev, som, f"{r['action']}", [action], pid, True, True,
                                 {"source": "live-verified-shortcut", "verified": True, "rung": r["rung"], "proof": folder, "pixel_changed": (a.get("pixel") or {}).get("frac")}))
    if rows:
        with open(out_jsonl, "a", encoding="utf-8") as f:
            for row in rows:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
    return {"rows": len(rows), "skipped": skipped, "jsonl": out_jsonl}


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(prog="shortcut_verify")
    ap.add_argument("cmd", choices=["plan", "run", "promote", "training-rows"])
    ap.add_argument("--app", default="webapp:excalidraw.com")
    ap.add_argument("--url", default="https://excalidraw.com")
    ap.add_argument("--only", nargs="*", default=[])
    ap.add_argument("--results", default="")
    a = ap.parse_args(argv)
    if a.cmd == "plan":
        print(json.dumps(plan(a.app, a.only), indent=1))
        return 0
    if a.cmd == "run":
        r = run(a.app, a.url, a.only)
        print(json.dumps({k: r[k] for k in ("summary", "seconds", "out_dir")}, indent=1))
        return 0
    if a.cmd == "training-rows":
        print(json.dumps(export_training_rows(a.results), indent=1))
        return 0
    from core_organs import rag as R
    print(json.dumps(promote(a.results, R.get_rag()), indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
