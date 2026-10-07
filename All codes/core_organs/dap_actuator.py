"""
dap_actuator.py -- the ONE place where an action leaves Hojaiga (the actuation backbone)

    ok, note = get_actuator().act(elem, "click")          # elem = a grounded element (any tier), verb = click/type/scroll/key/...

Every click / type / scroll / key the loop performs is routed through here. The actuator is organ_24's provider model made operational:
the element is described neutrally (a DAPNode: hwnd, bounds, role, name), the app FAMILY decides which providers are asked and in what order
(Chromium / WinUI / classic UIA / classic Win32 are DATA, not per-app code), and the first provider that DELIVERS wins. A provider answers

    None            "not mine / not applicable" - the next provider is asked
    (True, note)    delivered (still only a delivery: the verifier judges the effect)
    (False, note)   tried and failed - reported honestly, the chain continues

The virtual cursor sprite is only the visual proxy of the action. There is NO physical pointer or keyboard provider: when no provider can
deliver the result is (False, 'UNDELIVERABLE: ...') - a new app family is supported by ADDING a provider here (or in organ_24), never by
moving the real mouse.

Providers (all headless: UIA patterns, window messages to the exact HWND, OCR box + posted click):
  KeyProvider, ScrollProvider, TextAppendProvider, UIAPatternProvider (+ the extra patterns WinUI needs: Transform / Scroll /
  RangeValue / LegacyIAccessible), ChromiumProvider (Chromium / CEF / WebView2 / Electron: wakes the accessibility tree, redirects a
  frame to its content host, appends text through ValuePattern), MessageClickProvider, ParkedPixelProvider.
"""

from __future__ import annotations

import ctypes
import logging
import re
import threading
import time
from typing import Any, Callable, Dict, List, Optional, Tuple

from core_organs import headless_input as hin

logger = logging.getLogger("hojaiga.dap_actuator")

Result = Optional[Tuple[bool, str]]

_CHROMIUM_CLASS_PREFIXES = ("chrome_widgetwin", "chrome_renderwidgethosthwnd", "cefbrowserwindow", "intermediate d3d window")
_XAML_FRAME_CLASSES = ("winuidesktopwin32windowclass", "applicationframewindow", "windows.ui.core.corewindow")


# ----------------------------------------------------------------------------------------------------------------- app family

def _cls(hwnd: int) -> str:
    try:
        return (hin._class_name(hwnd) or "").lower()
    except Exception:
        return ""


_CONTENT_CACHE: Dict[int, Tuple[float, int]] = {}


def chromium_content_hwnd(hwnd: int) -> int:
    """The Chromium content window (Chrome_WidgetWin_*) that holds this app's DOM accessibility tree, or 0.
    The window itself when it IS one; otherwise the largest-tree Chromium widget window of the SAME process (a WinUI / WPF frame hosting a
    WebView2, a Win32 frame hosting CEF). Cached for 20 s."""
    now = time.time()
    hit = _CONTENT_CACHE.get(hwnd)
    if hit and now - hit[0] < 20.0:
        return hit[1]
    out = 0
    try:
        if _cls(hwnd).startswith(_CHROMIUM_CLASS_PREFIXES[0]) or _cls(hwnd) == "cefbrowserwindow":
            out = hwnd
        else:
            cands = [w for w in hin.process_windows(hwnd, include_hidden=True) if _cls(w).startswith("chrome_widgetwin")]
            if cands:
                best, best_n = 0, -1
                from core_organs import fast_uia
                for w in cands[:4]:
                    snap = fast_uia.snapshot(w, timeout_ms=2500) or []
                    if len(snap) > best_n:
                        best, best_n = w, len(snap)
                out = best if best_n >= 3 else 0
    except Exception as exc:  # noqa: BLE001
        logger.debug("[actuator] content-host lookup failed: %s", exc)
    _CONTENT_CACHE[hwnd] = (now, out)
    return out


_FAMILY_CACHE: Dict[int, Tuple[float, str]] = {}


def family_of(hwnd: int) -> str:
    """'chromium' | 'winui' | 'win32' (cached 30 s per window)."""
    hit = _FAMILY_CACHE.get(hwnd)
    if hit and time.time() - hit[0] < 30.0:
        return hit[1]
    fam = _family_of(hwnd)
    _FAMILY_CACHE[hwnd] = (time.time(), fam)
    return fam


def _family_of(hwnd: int) -> str:
    """Decided from window classes and process siblings (what the window IS), never from a name."""
    if not hwnd:
        return "win32"
    c = _cls(hwnd)
    if c.startswith(_CHROMIUM_CLASS_PREFIXES) or c == "cefbrowserwindow":
        return "chromium"
    try:
        if any(_cls(w).startswith("chrome_widgetwin") for w in hin.process_windows(hwnd, include_hidden=True)):
            return "chromium"                       # a frame hosting a Chromium content window (WebView2 / CEF)
    except Exception:  # noqa: BLE001
        pass
    try:
        if hin.is_xaml_host(hwnd):
            return "winui"
    except Exception:  # noqa: BLE001
        pass
    return "win32"


# ----------------------------------------------------------------------------------------------------------------- context + providers

class Ctx:
    """Everything one action needs, shared by the providers of that action."""

    def __init__(self, elem: Any, verb: str, text: str):
        self.elem, self.verb, self.text = elem, verb, text
        self.root = hin._u32.GetAncestor(elem.hwnd, 2) if getattr(elem, "hwnd", 0) else 0
        self.root = int(self.root or getattr(elem, "hwnd", 0) or 0)
        self.native = 0                            # the control's own hwnd when UIA could resolve it (typing appends at the caret there)
        self.family = family_of(self.root) if self.root else "win32"


class Provider:
    name = "provider"

    def applies(self, ctx: Ctx) -> bool:
        return True

    def act(self, ctx: Ctx) -> Result:           # pragma: no cover - interface
        raise NotImplementedError


class KeyProvider(Provider):
    name = "key"

    def applies(self, ctx):
        return ctx.verb in ("key", "shortcut")

    def act(self, ctx):
        return hin.post_key_combo(ctx.root, ctx.text or ctx.elem.name)


class ScrollProvider(Provider):
    name = "scroll"

    def applies(self, ctx):
        return ctx.verb == "scroll"

    def act(self, ctx):
        cx, cy = ctx.elem.center
        return hin.post_scroll(ctx.root, cx, cy, -3)


class TextAppendProvider(Provider):
    """Typing: posting characters to the control's OWN hwnd appends at the caret; ValuePattern.SetValue REPLACES the content (a real unattended
    run once overwrote line 1 with line 2). So characters go first; SetValue is the later rung. Classic controls only: a Chromium
    page has no per-element hwnd (its text fields take a ValuePattern append instead - ChromiumProvider)."""
    name = "text-append"

    def applies(self, ctx):
        return ctx.verb == "type" and bool(ctx.text) and (ctx.elem.role or "").lower() not in ("dataitem", "cell") and ctx.family != "chromium"

    def act(self, ctx):
        from core_organs import desktop_grounding as dg
        if ctx.elem.tier == "uia" and dg.HAS_UIA:
            out = dg._uia_dispatch(ctx.elem, "locate", "")
            ctx.native = out[1] if out else 0
        target = ctx.native or ctx.elem.hwnd
        replaced = ""
        if target and re.search(r"file ?name", ctx.elem.name or "", re.I) and re.match(r"^[A-Za-z]:[\\/]", ctx.text.strip()):
            # a FILE NAME field holds a default name ('Book1'): a full path typed after it is not a path. A person selects it all first.
            res = ctypes.c_size_t(0)
            hin._u32.SendMessageTimeoutW(target, 0x00B1, 0, -1, 0x2, 800, ctypes.byref(res))      # EM_SETSEL(0, -1)
            hin._u32.SendMessageTimeoutW(target, 0x0303, 0, 0, 0x2, 800, ctypes.byref(res))       # WM_CLEAR
            replaced = "replace:"
            # one WM_CHAR per character: the dialog / pane only enables its Save button on REAL change notifications (EM_REPLACESEL and
            # SetValue change the visible text but leave Save disabled - measured on Office's Save As pane)
            for ch in ctx.text:
                hin._u32.PostMessageW(target, 0x0102, ord(ch), 1)
            time.sleep(0.5)
            return True, "replace:wm_char->" + (hin._class_name(target) or "edit")
        ok, note = hin.post_text(target, ctx.text)
        return (True, f"{replaced or 'append:'}{note}") if ok else None


class CellEditProvider(Provider):
    """A grid cell is not a text control: it is a box that holds an EDIT IN PROGRESS, and an edit that is never
    closed is never content. Measured on a spreadsheet: the cell's own UIA value read back the number that was
    written into it, so every step 'verified' - while the document model held nothing, the app called the document
    'Saved', and the file written afterwards was an empty sheet.

    The route is the one a person uses, all of it headless: open the cell's editor (the cell's own Invoke/Select
    pattern), post the characters to the window that owns the grid, then close the edit with the universal
    'finish this' key. Nothing is trusted: the cell is read back and the write is claimed only when the value is
    really there - otherwise the ladder carries on to the pattern rung."""
    name = "cell-edit"

    def applies(self, ctx):
        return (ctx.verb == "type" and bool(ctx.text)
                and (ctx.elem.role or "").lower() in CELL_ROLES)

    def act(self, ctx):
        from core_organs import desktop_grounding as dg
        if not (ctx.elem.tier == "uia" and dg.HAS_UIA):
            return None
        opened, note = dg._act_on_element(ctx.elem, "click", "")      # the cell's own pattern opens its editor
        if not opened:
            return False, f"cell editor could not be opened ({note})"
        time.sleep(0.35)
        target = ctx.root or ctx.elem.hwnd
        ok, posted = hin.post_text(target, ctx.text)
        if not ok:
            return False, f"cell text not posted ({posted})"
        time.sleep(0.3)
        hin.post_key_combo(target, CELL_CONFIRM_KEY)                  # an unconfirmed edit is not content
        time.sleep(0.4)
        out = dg._uia_dispatch(ctx.elem, "read", "")
        got = str(out[1] or "") if out and out[0] is True else ""
        if ctx.text.strip() and ctx.text.strip() in got:
            return True, f"cell-edit:{note}+{posted}+{CELL_CONFIRM_KEY} read={got[:40]!r}"
        return False, f"cell-edit did not take the text (read back {got[:40]!r})"


class UIAPatternProvider(Provider):
    """UIA patterns on the live element (re-found by identity): Invoke / Select / Toggle / ExpandCollapse / LegacyIAccessible / Value."""
    name = "uia-pattern"

    def applies(self, ctx):
        from core_organs import desktop_grounding as dg
        return ctx.elem.tier == "uia" and dg.HAS_UIA and ctx.verb in ("click", "type")

    def act(self, ctx):
        from core_organs import desktop_grounding as dg
        out = dg._uia_dispatch(ctx.elem, ctx.verb, ctx.text)
        if out and out[0] is True:
            return out
        ctx.native = out[1] if out and out[0] is None else ctx.native
        return None


def _raw_dispatch(elem, verb: str, text: str = ""):
    """Act on a Chromium element found in the RAW UIA view (identity: name + role + box), on the dedicated UIA worker thread. The control-view
    re-find the classic ladder uses cannot see a DOM element at all. Returns (True, note) / (False, note) / None (not found)."""
    from core_organs import desktop_grounding as dg
    from core_organs import fast_uia
    if dg._UIA_EXEC is None:
        from concurrent.futures import ThreadPoolExecutor
        dg._UIA_EXEC = ThreadPoolExecutor(max_workers=1, thread_name_prefix="uia-act", initializer=dg._uia_thread_init)

    def work():
        want = (elem.name or "").strip().lower()
        best, best_d = None, 10 ** 9
        for n in (fast_uia.snapshot(elem.hwnd, max_nodes=4000, timeout_ms=8000) or []):
            if (n.name or "").strip().lower()[:120] != want or n.role != elem.role:
                continue
            d = abs(n.rect[0] - elem.bbox[0]) + abs(n.rect[1] - elem.bbox[1])
            if d < best_d:
                best, best_d = n, d
        if best is None:
            return None
        ctrl = best.ctrl
        if verb == "read":
            for getter in ("GetValuePattern", "GetTextPattern"):
                try:
                    pat = getattr(ctrl, getter)()
                    if pat:
                        return True, str(pat.Value if getter == "GetValuePattern" else pat.DocumentRange.GetText(-1))
                except Exception:  # noqa: BLE001
                    continue
            return None
        if verb == "set":
            pat = ctrl.GetValuePattern()
            if pat is None:
                return None
            pat.SetValue(text)
            return True, "chromium-raw-set-value"
        for getter, call, label in (("GetInvokePattern", "Invoke", "invoke"), ("GetTogglePattern", "Toggle", "toggle"),
                                    ("GetSelectionItemPattern", "Select", "select"), ("GetExpandCollapsePattern", "Expand", "expand"),
                                    ("GetLegacyIAccessiblePattern", "DoDefaultAction", "do-default")):
            try:
                pat = getattr(ctrl, getter)()
                if pat:
                    getattr(pat, call)()
                    return True, f"chromium-raw-{label}"
            except Exception:  # noqa: BLE001
                continue
        return False, "INEFFECTIVE: the page element exposes no pattern that acts"
    try:
        return dg._UIA_EXEC.submit(work).result(timeout=12)
    except Exception as exc:  # noqa: BLE001
        return False, f"chromium raw dispatch failed: {type(exc).__name__}: {str(exc)[:60]}"


class ChromiumProvider(Provider):
    """Chromium / CEF / WebView2 / Electron. (1) The accessibility tree is only built once a client asks: ask (WM_GETOBJECT, read-only).
    (2) A frame that hosts a Chromium content window is redirected to that window. (3) The DOM lives in the RAW UIA view, so the element is
    re-found THERE and acted on through its own patterns (Invoke / Toggle / Select / ExpandCollapse / Value); typing APPENDS through
    ValuePattern (read + set), because a page element has no HWND to post characters to. A page element with no pattern that acts is reported
    INEFFECTIVE: the chain then falls to the message rungs, whose 'delivered' is not proof - the verifier judges."""
    name = "chromium"

    _woken: Dict[int, float] = {}

    def applies(self, ctx):
        return ctx.family == "chromium" and ctx.elem.tier == "uia" and ctx.verb in ("click", "type")

    def _wake(self, hwnd: int) -> None:
        if time.time() - self._woken.get(hwnd, 0) > 60:
            try:
                from core_organs import universal_scan as us
                us.wake_accessibility(hwnd)
            except Exception:  # noqa: BLE001
                pass
            self._woken[hwnd] = time.time()

    def act(self, ctx):
        content = chromium_content_hwnd(ctx.elem.hwnd) or chromium_content_hwnd(ctx.root)
        if content and content != ctx.elem.hwnd:
            ctx.elem.hwnd = content                                        # the element lives in the content host
        self._wake(ctx.elem.hwnd)
        if ctx.verb == "type":
            cur = _raw_dispatch(ctx.elem, "read")
            current = (cur[1] if cur and cur[0] is True else "") or ""
            want = current + ctx.text
            res = _raw_dispatch(ctx.elem, "set", want)
            if res and res[0] is True:
                end = time.time() + 4.0                  # the page applies a value on its next frame (~1 s when the window is hidden)
                while time.time() < end:
                    back = _raw_dispatch(ctx.elem, "read")
                    if back and back[0] is True and back[1] == want:
                        return True, "chromium-value-append (read back)"
                    time.sleep(0.4)
                return False, "INEFFECTIVE: SetValue was accepted but the page never reflected the text"
            return False, "INEFFECTIVE: the page control exposes no ValuePattern (typing needs a focused DOM element)"
        res = _raw_dispatch(ctx.elem, "click")
        if res is None:
            return None
        return (True, res[1]) if res[0] else (False, res[1])


class UIAScrollProvider(Provider):
    """Scrolling through UIA's ScrollPattern: delivered by the control itself, so it works where a posted mouse wheel is ignored (XAML /
    WinUI hosts, Chromium). Honest: no ScrollPattern on the element = None (the wheel rung is asked next)."""
    name = "uia-scroll"

    def applies(self, ctx):
        from core_organs import desktop_grounding as dg
        return ctx.verb == "scroll" and ctx.elem.tier == "uia" and dg.HAS_UIA

    def act(self, ctx):
        out = _uia_extra(ctx.elem, "scroll", ctx.text or "down")
        return out if out and out[0] else None


def _uia_extra(elem, verb: str, value: Any = None):
    """Patterns the click/type ladder does not use (ScrollPattern, RangeValuePattern, TransformPattern): run on the SAME dedicated, COM-initialised
    UIA worker thread as every other UIA action. Returns (True, note) delivered, (False, note) tried, None unavailable."""
    from core_organs import desktop_grounding as dg
    if dg._UIA_EXEC is None:
        from concurrent.futures import ThreadPoolExecutor
        dg._UIA_EXEC = ThreadPoolExecutor(max_workers=1, thread_name_prefix="uia-act", initializer=dg._uia_thread_init)

    def work():
        import uiautomation as auto
        target = dg._find_control_by_identity(auto.ControlFromHandle(elem.hwnd), elem)
        if target is None:
            return None
        if verb == "scroll":
            pat = target.GetScrollPattern()
            if pat is None:
                return None
            v = str(value or "down").lower()
            small_inc, small_dec, none = 4, 1, 2                      # UIA ScrollAmount: SmallIncrement / SmallDecrement / NoAmount
            if v in ("left", "right"):
                pat.Scroll(small_dec if v == "left" else small_inc, none)
            else:
                pat.Scroll(none, small_dec if v == "up" else small_inc)
            return True, f"uia-scroll-{v}"
        if verb == "set_range":
            pat = target.GetRangeValuePattern()
            if pat is None:
                return None
            pat.SetValue(float(value))
            return True, f"uia-range-value={value}"
        if verb in ("move", "resize"):
            pat = target.GetTransformPattern()
            if pat is None:
                return None
            a, b = value
            (pat.Move if verb == "move" else pat.Resize)(a, b)
            return True, f"uia-transform-{verb}"
        return None
    try:
        return dg._UIA_EXEC.submit(work).result(timeout=10)
    except Exception as exc:  # noqa: BLE001
        return False, f"uia-extra {verb} failed: {type(exc).__name__}: {str(exc)[:60]}"


class MessageClickProvider(Provider):
    """A posted click to the exact HWND under the element's centre (classic windows, covered or partly off-screen)."""
    name = "message-click"

    def applies(self, ctx):
        return ctx.verb == "click" and bool(ctx.root)

    def act(self, ctx):
        # A XAML/WinUI host (Windows.UI.Core.CoreWindow) routes input through the XAML stack and DROPS
        # posted mouse messages, so a coordinate click into it does nothing. The UIA-pattern rung already had
        # its turn ahead of us in the ladder; if a UIA-found element still reaches here on a XAML host,
        # reporting post_click's 'message sent' as delivery is a FAKE success (the verifier then sees NO_CHANGE
        # and re-presses the same dead control). Answer honestly by declining the rung - the chain ends in
        # UNDELIVERABLE, exactly as the 'XAML ignores posted keys' guard does for shortcuts.
        if ctx.verb == "click" and getattr(ctx.elem, "tier", "") == "uia" and ctx.family == "winui":
            return None
        cx, cy = ctx.elem.center
        return hin.post_click(ctx.root, cx, cy)


class ParkedPixelProvider(Provider):
    """A pixel-found element (OCR / vision) in a MINIMIZED window: its screen coordinates only mean something while the window is laid out, so
    the click is delivered while the window is parked off-screen (the rect the capture used), then it is re-minimized. Never a visible restore."""
    name = "parked-pixel"

    def applies(self, ctx):
        return ctx.verb == "click" and bool(ctx.root) and ctx.elem.tier in ("ocr", "vision") and hin.is_minimized(ctx.root)

    def act(self, ctx):
        from core_organs import background_window as bw
        cx, cy = ctx.elem.center
        with bw.BackgroundSession(ctx.root) as sess:
            if sess.mode == "parked":
                ok, note = hin.post_click(ctx.root, cx, cy)
                time.sleep(0.4)
                return ok, note + " [delivered while parked off-screen]"
        return False, f"{hin.UNDELIVERABLE}: pixel-found element in a minimized window and it could not be parked ({sess.mode})"


class TextPostProvider(Provider):
    """Last typing rung: characters posted to the resolved control (or the element's own hwnd)."""
    name = "text-post"

    def applies(self, ctx):
        return ctx.verb == "type" and bool(ctx.native or ctx.elem.hwnd)

    def act(self, ctx):
        ok, note = hin.post_text(ctx.native or ctx.elem.hwnd, ctx.text)
        return (True, note) if ok else (False, note)


# ----------------------------------------------------------------------------------------------------------------- the actuator

# What a grid cell is called in UIA vocabulary, and the key that ENDS an edit in one. Both are interface
# conventions shared by every grid family, not knowledge about a particular app.
CELL_ROLES = ("dataitem", "cell")
CELL_CONFIRM_KEY = "enter"


# family -> ordered provider names. DATA: a new family or a new order is a table edit, not code in the loop.
LADDERS: Dict[str, List[str]] = {
    "win32":    ["key", "scroll", "text-append", "cell-edit", "uia-pattern", "parked-pixel", "message-click", "text-post"],
    "winui":    ["key", "uia-scroll", "scroll", "text-append", "cell-edit", "uia-pattern", "parked-pixel", "message-click", "text-post"],
    # a Chromium page has no per-element HWND: posted characters / clicks into the frame are never meaningful there, and after a SetValue that the
    # page applies late they DOUBLE the text (measured on a tray-parked app). The chain ends at the page's own patterns, honestly.
    "chromium": ["key", "uia-scroll", "scroll", "chromium", "parked-pixel"],
}


class DAPActuator:
    def __init__(self) -> None:
        self.providers: Dict[str, Provider] = {p.name: p for p in
                                               (KeyProvider(), ScrollProvider(), UIAScrollProvider(), TextAppendProvider(), CellEditProvider(), UIAPatternProvider(), ChromiumProvider(),
                                                ParkedPixelProvider(), MessageClickProvider(), TextPostProvider())}
        self.last_trace: List[Dict[str, Any]] = []
        self.stats: Dict[str, Dict[str, int]] = {}
        self._lock = threading.Lock()

    def register(self, provider: Provider, *, families: Optional[List[str]] = None, before: str = "") -> None:
        """Add a provider (a NEW app family's way in) to the named families' ladders, optionally ahead of an existing rung."""
        self.providers[provider.name] = provider
        for fam in (families or list(LADDERS)):
            lad = LADDERS.setdefault(fam, [])
            if provider.name in lad:
                continue
            lad.insert(lad.index(before) if before in lad else len(lad), provider.name)

    def act(self, elem: Any, verb: str, text: str = "") -> Tuple[bool, str]:
        if verb == "wait":
            time.sleep(min(2.0, 0.8))
            return True, "waited"
        if verb == "done":
            return True, "declared-done"
        if verb == "invoke":
            verb = "click"
        ctx = Ctx(elem, verb, text)
        trace: List[Dict[str, Any]] = []
        last_fail: Optional[Tuple[bool, str]] = None
        for name in LADDERS.get(ctx.family, LADDERS["win32"]):
            p = self.providers.get(name)
            if p is None:
                continue
            try:
                if not p.applies(ctx):
                    continue
                r = p.act(ctx)
            except Exception as exc:  # noqa: BLE001 - one provider's crash must not end the ladder
                r = (False, f"{hin.UNDELIVERABLE}: {name} raised {type(exc).__name__}: {str(exc)[:60]}")
            if r is None:
                continue
            trace.append({"provider": name, "ok": bool(r[0]), "note": str(r[1])[:90]})
            with self._lock:
                s = self.stats.setdefault(name, {"delivered": 0, "failed": 0})
                s["delivered" if r[0] else "failed"] += 1
            if r[0]:
                self.last_trace = trace
                return r
            last_fail = r
            if name in ("text-post", "message-click", "parked-pixel") and verb in ("click", "type"):
                break                                               # the last honest answer of a message rung is final
        self.last_trace = trace
        if last_fail is not None:
            return last_fail
        return False, f"{hin.UNDELIVERABLE}: no UIA pattern and no addressable HWND for '{getattr(elem, 'name', '')}' ({verb})"


    def act_pattern(self, elem: Any, verb: str, value: Any = None) -> Tuple[bool, str]:
        """Pattern verbs outside the loop's click/type vocabulary: 'set_range' (sliders / spinners), 'move' / 'resize' (TransformPattern),
        'scroll' (ScrollPattern). Honest INEFFECTIVE when the element does not expose the pattern."""
        out = _uia_extra(elem, verb, value)
        if out is None:
            self.last_trace = [{"provider": "uia-extra", "ok": False, "note": f"INEFFECTIVE: no {verb} pattern on '{getattr(elem, 'name', '')}'"}]
            return False, f"INEFFECTIVE: '{getattr(elem, 'name', '')}' exposes no pattern for {verb}"
        self.last_trace = [{"provider": "uia-extra", "ok": bool(out[0]), "note": str(out[1])[:90]}]
        return bool(out[0]), str(out[1])


_ACTUATOR: Optional[DAPActuator] = None


def get_actuator() -> DAPActuator:
    global _ACTUATOR
    if _ACTUATOR is None:
        _ACTUATOR = DAPActuator()
    return _ACTUATOR
