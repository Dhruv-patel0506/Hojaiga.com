"""
universal_scan.py — ONE function to learn ANY app, website or web app, invisibly.

    from core_organs.universal_scan import scan
    report = scan("notepad")                      # desktop app (launched minimized if not running)
    report = scan("Visual Studio Code")           # Electron
    report = scan("https://news.ycombinator.com") # website  (private headless Chrome, never shown)

The same pipeline for every target, with time that adapts to what the target exposes (nothing is
classified easy or hard in advance):

  desktop   find/launch minimized -> wake accessibility (Chromium/Electron) -> park off-screen ->
            E0 menu crawl (read-only) -> full layout map (sections, every control, position,
            reversible tab/tree/scroll deepening) -> bounded E1 exploration (reversible probes)
            -> restore the window to minimized exactly as it was
  web       headless Chrome -> static DOM map (landmarks, shadow DOM, same-origin iframes) ->
            reversible deepening (tabs, disclosure widgets, lazy scroll) -> commands + layout

Everything lands in the behavior model (organ_48 tables), so the next scan of the same target — and
every later task on it — starts from knowledge instead of from zero.

The report is uniform and honest: window mode, per-phase timings, what was found, what was skipped
and why (a tier or region that could not be read says so; nothing is faked).
"""

from __future__ import annotations

import ctypes
import ctypes.wintypes as wt
import json
import logging
import os
import re
import subprocess
import time
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("hojaiga.universal_scan")

_u32 = ctypes.windll.user32 if os.name == "nt" else None
_k32 = ctypes.windll.kernel32 if os.name == "nt" else None
_initial_desktop = _u32.GetThreadDesktop(_k32.GetCurrentThreadId()) if (_u32 and _k32) else None
_start_apps_cache: Optional[List[Tuple[str, str]]] = None


# ------------------------------------------------------------------ target classification

def classify_target(target: str) -> str:
    t = (target or "").strip()
    if re.match(r"^[a-z][a-z0-9+.-]*://", t, re.I):
        return "web"
    if " " not in t and re.match(r"^([a-z0-9-]+\.)+[a-z]{2,}(/.*)?$", t, re.I) and not t.lower().endswith((".exe", ".lnk")):
        return "web"
    return "desktop"


# ------------------------------------------------------------------ window helpers

def _top_windows() -> Dict[int, Tuple[int, str, str]]:
    """hwnd -> (pid, class, title) for visible top-level windows across interactive and host desktops."""
    from core_organs import headless_input as _hin
    _hin.ensure_input_desktop()
    out: Dict[int, Tuple[int, str, str]] = {}
    seen_hwnds = set()
    desktops = []
    init_desk = _hin.initial_desktop()
    if init_desk and init_desk not in desktops:
        desktops.append(init_desk)
    if _initial_desktop and _initial_desktop not in desktops:
        desktops.append(_initial_desktop)
    cur = _u32.GetThreadDesktop(_k32.GetCurrentThreadId()) if (_u32 and _k32) else None
    if cur and cur not in desktops:
        desktops.append(cur)
    try:
        inp = _u32.OpenInputDesktop(0, False, 0x01FF)
        if inp and inp not in desktops:
            desktops.append(inp)
    except Exception:
        pass
    try:
        def_desk = _u32.OpenDesktopW("Default", 0, False, 0x01FF)
        if def_desk and def_desk not in desktops:
            desktops.append(def_desk)
    except Exception:
        pass

    @ctypes.WINFUNCTYPE(ctypes.c_bool, wt.HWND, wt.LPARAM)
    def cb(h, _):
        ih = int(h)
        if ih in seen_hwnds:
            return True
        try:
            if _u32.IsWindowVisible(h) or _u32.IsIconic(h):
                seen_hwnds.add(ih)
                p = wt.DWORD()
                _u32.GetWindowThreadProcessId(h, ctypes.byref(p))
                c = ctypes.create_unicode_buffer(128)
                _u32.GetClassNameW(h, c, 128)
                from core_organs import headless_input as _hin      # deadlock-safe title read (see safe_window_text)
                out[ih] = (int(p.value), c.value, _hin.safe_window_text(ih, 200)[:200])
        except Exception:
            pass
        return True

    if desktops:
        for d in desktops:
            try:
                _u32.EnumDesktopWindows(d, cb, 0)
            except Exception:
                pass
    else:
        _u32.EnumWindows(cb, 0)
    return out


def launch_target_status(app_name: str) -> Dict[str, Any]:
    """Does what the Start menu would launch for ``app_name`` actually exist? {found, app_id, kind: path|aumid|other,
    exists: True|False|None}. A path-style entry (a classic exe) is checked on disk; a packaged / ProgID entry cannot be
    checked cheaply and says exists=None (unknown, not 'yes'). Used to tell 'the exe is gone' from 'it is just slow'."""
    want = (app_name or "").strip().lower()
    hit = None
    for name, app_id in start_apps():
        if name.strip().lower() == want:
            hit = (name, app_id)
            break
    if hit is None:
        for name, app_id in start_apps():
            if want and want in name.strip().lower():
                hit = (name, app_id)
                break
    if hit is None:
        return {"found": False, "app_id": "", "kind": "none", "exists": None}
    app_id = hit[1]
    if re.match(r"^[A-Za-z]:[\\/]", app_id) or app_id.lower().endswith(".exe"):
        return {"found": True, "app_id": app_id, "kind": "path", "exists": os.path.exists(app_id)}
    if "!" in app_id:
        return {"found": True, "app_id": app_id, "kind": "aumid", "exists": None}
    return {"found": True, "app_id": app_id, "kind": "other", "exists": None}


def start_apps() -> List[Tuple[str, str]]:
    """(display name, AppID) from the Start menu — packaged, Win32 and PWA apps alike.
    The Start menu changes rarely, but every scan runs in its own process, so the in-memory cache is
    worthless there and the ~2 s `Get-StartApps` call was paid on EVERY launch. Persist it to disk with a
    TTL so a fresh process resolves apps instantly and only the first scan (or one after the TTL) pays."""
    global _start_apps_cache
    if _start_apps_cache is not None:
        return _start_apps_cache
    cache = os.path.join(os.environ.get("HOJAIGA_VAR", r"D:\new_automation\var\hojaiga"), "start_apps_cache.json")
    ttl = float(os.environ.get("HOJAIGA_STARTAPPS_TTL_S", str(6 * 3600)))
    apps: List[Tuple[str, str]] = []
    try:
        if os.path.exists(cache) and (time.time() - os.path.getmtime(cache)) < ttl:
            with open(cache, encoding="utf-8") as fh:
                loaded = json.load(fh)
            apps = [(str(x[0]), str(x[1])) for x in loaded if len(x) >= 2]
    except Exception:
        apps = []
    if not apps:
        try:
            r = subprocess.run(["powershell", "-NoProfile", "-Command",
                                "Get-StartApps | ForEach-Object { $_.Name + '|||' + $_.AppID }"],
                               capture_output=True, text=True, timeout=40, creationflags=0x08000000)
            apps = [(l.split("|||", 1)[0], l.split("|||", 1)[1]) for l in r.stdout.splitlines() if "|||" in l]
            if apps:
                os.makedirs(os.path.dirname(cache), exist_ok=True)
                tmp = cache + f".{os.getpid()}.tmp"
                with open(tmp, "w", encoding="utf-8") as fh:
                    json.dump(apps, fh)
                os.replace(tmp, cache)                  # atomic: concurrent scans never read a half file
        except Exception:
            apps = []
    _start_apps_cache = apps
    return apps


def _abbrev_match(n: str, words: List[str]) -> bool:
    """'vscode' is 'visual studio code': every word but the last may be cut to a prefix (>=1 char), the last must be whole. Generic, no per-app table."""
    if len(words) < 2 or " " in n:
        return False
    def rec(i: int, pos: int) -> bool:
        if i == len(words) - 1:
            return n[pos:] == words[i]
        w = words[i]
        return any(n.startswith(w[:k], pos) and rec(i + 1, pos + k) for k in range(1, len(w) + 1))
    return rec(0, 0)


def resolve_app(name: str) -> Optional[Tuple[str, str]]:
    n = re.sub(r"[^a-z0-9 ]", "", (name or "").lower()).strip()
    best, best_score = None, 0
    for disp, appid in start_apps():
        d = re.sub(r"[^a-z0-9 ]", "", disp.lower()).strip()
        if d.startswith(("uninstall ", "install ", "remove ")):          # an installer / uninstaller shortcut is never the program
            continue
        words = d.split()
        score = (100 if d == n else 80 if d.startswith(n) else 70 if n in words else 60 if n in d else
                 55 if _abbrev_match(n.replace(" ", ""), words) else 0)
        if score and (score > best_score or (score == best_score and len(d) < len(re.sub(r"[^a-z0-9 ]", "", best[0].lower())))):
            best, best_score = (disp, appid), score
    return best


def wake_accessibility(hwnd: int) -> str:
    """Chromium-family UIs (Chrome, Electron, CEF clients such as Steam / Spotify) build their UIA tree only once a
    client asks. Ask (WM_GETOBJECT on every Chromium window inside the frame) - a read-only query, nothing is
    clicked or focused. The frame itself may be any class (SDL_app, Qt, a custom host): what matters is whether it
    CONTAINS Chromium windows, so look at the descendants, not at the top-level class."""
    def cls_of(h) -> str:
        b = ctypes.create_unicode_buffer(128)
        _u32.GetClassNameW(h, b, 128)
        return b.value

    targets: List[int] = []
    if cls_of(hwnd).startswith("Chrome_"):
        targets.append(int(hwnd))

    @ctypes.WINFUNCTYPE(ctypes.c_bool, wt.HWND, wt.LPARAM)
    def cb(h, _):
        c = cls_of(h)
        if c.startswith("Chrome_") or c == "CefBrowserWindow":
            targets.append(int(h))
        return True
    _u32.EnumChildWindows(hwnd, cb, 0)
    if not targets:
        return "not-chromium"
    res = ctypes.c_size_t()
    for h in targets:
        for obj in (-4, -25):                            # OBJID_CLIENT, UiaRootObjectId
            _u32.SendMessageTimeoutW(h, 0x3D, 0, obj, 0x2, 500, ctypes.byref(res))
    return f"chromium-windows-queried={len(targets)}"


def _is_startup_dialog(hwnd: int) -> bool:
    from core_organs import popup_policy as pp
    return pp.looks_like_dialog(hwnd)


def _notice_window(h: int) -> bool:
    """A window that is never an application's main window: owned by another window, a tool window, or one that refuses activation (toasts, task panes, tooltips)."""
    try:
        ex = _u32.GetWindowLongW(h, -20) & 0xFFFFFFFF                        # GWL_EXSTYLE
        return bool(_u32.GetWindow(h, 4)) or bool(ex & 0x80) or bool(ex & 0x08000000)   # GW_OWNER, WS_EX_TOOLWINDOW, WS_EX_NOACTIVATE
    except Exception:
        return False


class _WP(ctypes.Structure):
    _fields_ = [("length", wt.UINT), ("flags", wt.UINT), ("showCmd", wt.UINT), ("ptMin", wt.POINT), ("ptMax", wt.POINT), ("rcNormal", wt.RECT)]


def _main_rank(h: int) -> Tuple[int, int, int]:
    r = wt.RECT()
    try:
        if _u32.IsIconic(h):                                                  # a minimized window's rect is the minimized stub: its restored size is what tells main from popup
            wp = _WP()
            wp.length = ctypes.sizeof(_WP)
            _u32.GetWindowPlacement(h, ctypes.byref(wp))
            r = wp.rcNormal
        else:
            _u32.GetWindowRect(h, ctypes.byref(r))
    except Exception:
        pass
    area = max(0, r.right - r.left) * max(0, r.bottom - r.top)
    return (0 if _notice_window(h) else 1, 1 if _u32.IsIconic(h) else 0, area)


def launch_hidden(name: str, timeout_s: float = 45.0, fast: bool = False, args: Optional[List[str]] = None) -> Dict[str, Any]:
    """Start `name` and keep its window minimized / unfocused from the moment it appears. `fast=True` shortens the protective settle waits
    (a window must be 0.6 s old and chosen for 0.6 s, startup is watched 3 s with 0.6 s of quiet instead of 1.0 / 1.2 / 5 s / 1.0 s): a splash
    screen that lives longer than that is still rejected by the size / title / proven-stable test, only the margin is smaller."""
    from core_organs import background_window as bw, headless_input as _hin
    _hin.ensure_input_desktop()
    info: Dict[str, Any] = {"launched": False, "hwnd": 0, "notes": []}
    app = resolve_app(name)
    if not app:
        # Not a Start-menu entry: any INSTALLED program still resolves by path / PATH / App Paths (an exe path is accepted
        # as is). A program whose manifest asks for elevation is never launched here: the UAC prompt is a human step.
        try:
            from core_organs import static_knowledge as sk
            from core_organs import pe_resources as pr
            exe = sk.exe_for(name)
            if exe and os.path.isfile(exe) and not sk.package_root(exe):
                level = (pr.read_resources(exe).get("manifest") or {}).get("execution_level", "")
                if level in ("requireAdministrator", "highestAvailable"):
                    info["notes"].append(f"not in the Start menu; {os.path.basename(exe)} requests elevation ({level}): a UAC prompt is a human step, not launched")
                    info["requires_elevation"] = True
                    return info
                app = (os.path.splitext(os.path.basename(exe))[0], exe)
                info["notes"].append("resolved by program path (not a Start-menu entry)")
        except Exception as exc:
            info["notes"].append(f"program-path resolution unavailable ({type(exc).__name__})")
    if not app:
        info["notes"].append("not in the Start menu")
        return info
    disp, appid = app
    info["resolved"] = disp
    before = _top_windows()
    fg_before = bw.last_user_window() or _u32.GetForegroundWindow()
    t0 = time.time()
    try:
        if re.search(r"\.exe$", appid, re.I) and os.path.exists(appid):
            si = subprocess.STARTUPINFO()
            si.dwFlags = 1
            si.wShowWindow = 7                                  # SW_SHOWMINNOACTIVE
            si.lpDesktop = "WinSta0\\Default"
            subprocess.Popen([appid] + list(args or []), startupinfo=si, cwd=os.path.dirname(appid))         # args: e.g. a scripting bridge the application loads at start-up
        elif re.match(r"^[A-Za-z]:\\", appid) or appid.lower().endswith(".exe"):
            subprocess.Popen(["cmd", "/c", "start", "/min", "", appid], creationflags=0x08000000)
        else:
            subprocess.Popen(["explorer.exe", f"shell:AppsFolder\\{appid}"], creationflags=0x08000000)
    except Exception as exc:
        info["notes"].append(f"launch failed: {type(exc).__name__}")
        return info
    hwnd, now = 0, {}
    first_seen: Dict[int, float] = {}
    chosen_since, chosen = 0.0, 0
    dialog_seen: List[str] = []
    answered: set = set()
    from core_organs import desktop_grounding as dg
    g = dg.DesktopGrounding()
    while time.time() - t0 < timeout_s:
        now = _top_windows()
        new = [h for h in now if h not in before]
        for h in new:
            first_seen.setdefault(h, time.time())
            if not _u32.IsIconic(h):                           # minimize EVERY new window the instant it shows
                _u32.ShowWindow(h, 7)
        # Candidates must have PROVEN stable: still alive, titled, real size, and older than 1.5 s.
        # Splash screens (Office, Visual Studio, Electron) appear for a moment and are destroyed; locking
        # onto one made every later UIA call throw COMError.
        # A single-instance app already running (e.g. OBS) pops an "already running" MESSAGE BOX when we
        # launch it. Scanning that dialog returned a nonsense "8 controls" map of a popup, so reject any
        # window whose title says it is an error/second-instance notice — we must not measure it as the app.
        def _ok(h: int) -> bool:
            if not (_u32.IsWindow(h) and now.get(h, (0, "", ""))[2]):
                return False
            title = now[h][2]
            if any(ord(ch) < 32 for ch in title) or _notice_window(h):         # a toast / notification / tool window of the app (measured: Office's 'Clipboard - Item not Collected')
                return False
            if _SECOND_INSTANCE_RE.search(title):
                if title not in dialog_seen:
                    dialog_seen.append(title)
                return False
            r = wt.RECT()
            _u32.GetWindowRect(h, ctypes.byref(r))
            big = (r.right - r.left) >= 200 and (r.bottom - r.top) >= 120
            iconic = bool(_u32.IsIconic(h))
            return (big or iconic) and time.time() - first_seen.get(h, time.time()) >= (0.6 if fast else 1.0) \
                and now[h][1] not in ("Windows.UI.Core.CoreWindow",)
        stable = [h for h in new if _ok(h) and h not in answered]
        if int((time.time() - t0) * 1) != info.get("_tick"):            # compact per-second trace for diagnostics
            info["_tick"] = int((time.time() - t0) * 1)
            info.setdefault("trace", []).append(
                f"{info['_tick']}s new={[(now[h][1][:14], now[h][2][:12], bool(_u32.IsIconic(h)), _ok(h)) for h in new][:4]}")
        if stable:
            cand_names = [name]
            base_name = os.path.splitext(os.path.basename(name))[0]
            if base_name and base_name != name:
                cand_names.append(base_name)
            pick = next((g.find_window(cn) for cn in cand_names if g.find_window(cn) in stable), None) or g.find_window(name)
            best = pick if pick in stable else max(stable, key=_main_rank)       # the app's main window: unowned, largest - never the window with the longest title
            if best != chosen:
                chosen, chosen_since = best, time.time()
            elif time.time() - chosen_since >= (0.6 if fast else 1.2):
                if len(answered) < 3 and _is_startup_dialog(chosen):            # a start-up QUESTION is not the app: answer it by role policy
                    from core_organs import popup_policy as pp
                    res = pp.resolve_dialog(chosen, mode="preflight")
                    answered.add(chosen)
                    info["notes"].append(f"start-up dialog '{now[chosen][2][:40]}' -> {res.action or 'unanswered'}"
                                         + (" (needs a human)" if res.need_human else ""))
                    if res.need_human:
                        info["startup_dialog_needs_human"] = now[chosen][2]
                        break
                    chosen = 0                                                  # now wait for the real window
                    continue
                hwnd = chosen
                break
        time.sleep(0.05)
    if hwnd:
        # a split-second window may already have been replaced by the real one (splash -> main)
        info["notes"].append(bw.stabilize_minimized(hwnd, fg_before, 3.0 if fast else 5.0, quiet_s=0.6 if fast else 1.0) or "stable")
        info["launched"] = True
        info["hwnd"] = hwnd
        bw.mark_ours(hwnd)                       # we created it: only then may the harness close/park it freely
        info["title"] = now.get(hwnd, (0, "", ""))[2]
    else:
        if dialog_seen:
            info["already_running_dialog"] = dialog_seen[0]
            info["notes"].append(f"app is already running (single instance); refused to scan its '{dialog_seen[0]}' dialog")
        else:
            info["notes"].append("no window appeared")
    info["launch_s"] = round(time.time() - t0, 2)
    info.pop("_tick", None)
    info["trace"] = (info.get("trace") or [])[-6:]
    return info


def wait_tree_ready(hwnd: int, timeout_s: float = 15.0, min_nodes: int = 3) -> int:
    """Block (bounded) until the window's UI tree has STOPPED GROWING. Apps resume and populate for a second or
    two after being un-minimized (UWP/WinUI/Office); acting at the first moment something exists means acting
    on an empty UI. Returns the settled node count."""
    from core_organs import fast_uia
    last, steady, end = -1, 0, time.time() + timeout_s
    while time.time() < end and steady < 2:
        snap = fast_uia.snapshot(hwnd, timeout_ms=6000)
        cnt = len(snap) if snap else 0
        steady = steady + 1 if (cnt == last and cnt >= min_nodes) else 0
        last = cnt
        time.sleep(0.35)
    return max(last, 0)


_DISCARD_RE = re.compile(r"^(don'?t save|do not save|discard( changes)?|no)$", re.I)


# the question a window asks before closing with unsaved work ("Do you want to save changes to ...", Office's "Save your
# changes to this file?")
_SAVE_PROMPT_RE = re.compile(r"\bsave\b.{0,30}\bchanges?\b|want to save|keep (?:your )?changes", re.I)


def _discard_unsaved(hwnd: int) -> bool:
    """A window WE launched is asking to save changes: answer with the non-saving button. Only ever called for
    instances this run created, so no user document is involved."""
    from core_organs import fast_uia
    from core_organs import organ_48_app_behavior_model as bm
    snaps = list(fast_uia.snapshot(hwnd, timeout_ms=4000) or [])
    for w in bm._popups(hwnd)[:4]:
        snaps += fast_uia.snapshot(w, timeout_ms=3000) or []
    asks = any(_SAVE_PROMPT_RE.search(n.name or "") for n in snaps)
    if not asks:
        return False
    for n in snaps:
        if _DISCARD_RE.match((n.name or "").strip()) and "invoke" in n.pats and n.enabled:
            return bm.invoke_node_safely(n)[0]
    return False


def close_window(hwnd: int, timeout_s: float = 6.0, discard_unsaved: bool = False) -> bool:
    """Close a window WE launched and VERIFY it is gone: WM_CLOSE, then SC_CLOSE, then a second WM_CLOSE.
    Never kills a process. Returns False honestly when the app refuses (e.g. a save prompt or a dialog)."""
    if not (hwnd and _u32.IsWindow(hwnd)):
        return True
    for msg, w in ((0x0010, 0), (0x0112, 0xF060), (0x0010, 0)):
        try:
            _u32.PostMessageW(hwnd, msg, w, 0)
        except Exception:
            pass
        end = time.time() + timeout_s / 3
        tried = False
        while time.time() < end:
            if not _u32.IsWindow(hwnd):
                return True
            if discard_unsaved and not tried and time.time() > end - timeout_s / 3 + 0.8:
                tried = True
                try:
                    _discard_unsaved(hwnd)
                except Exception:
                    pass
            time.sleep(0.1)
    return not _u32.IsWindow(hwnd)


# ------------------------------------------------------------------ start screens

# A single-instance app that is already running shows a modal notice when launched again (OBS: "OBS is
# already running"). Such a window is a message box, NOT the app — scanning it produced a bogus tiny map.
_SECOND_INSTANCE_RE = re.compile(r"already (running|open|launched)|another instance|instance already|"
                                 r"is (currently )?running|cannot (start|launch|open)" , re.I)

# Names (not apps) of the "give me an empty document" tile that start/backstage screens offer.
START_TILE_RE = re.compile(r"^(blank( (document|workbook|presentation|notebook|page|canvas|project|file))?|"
                           r"new blank( (document|workbook|presentation))?|empty (document|workbook|project))$", re.I)


def leave_start_screen(hwnd: int, timeout_s: float = 20.0) -> Dict[str, Any]:
    """Office-style apps open on a start/backstage screen with no ribbon at all. If one is showing, invoke
    its 'Blank ...' tile: an empty, UNSAVED document (closing it later prompts for nothing). Reversible and
    non-destructive; if there is no such tile the window is left exactly as it is."""
    from core_organs import fast_uia
    from core_organs import organ_48_app_behavior_model as bm
    snap = fast_uia.snapshot(hwnd, timeout_ms=8000) or []
    tile = next((n for n in snap if START_TILE_RE.match(n.name or "") and n.enabled
                 and (set(n.pats) & {"invoke", "select"})), None)
    if tile is None:
        return {"start_screen": False}
    ok, how = bm.invoke_node_safely(tile)
    t0 = time.time()
    while time.time() - t0 < timeout_s:
        time.sleep(0.5)
        s2 = fast_uia.snapshot(hwnd, timeout_ms=8000) or []
        if sum(1 for n in s2 if n.ctype == "TabItemControl") >= 3:       # a ribbon appeared
            return {"start_screen": True, "tile": tile.name, "how": how, "ribbon_after_s": round(time.time() - t0, 1)}
    return {"start_screen": True, "tile": tile.name, "how": how, "ribbon_after_s": None,
            "note": "invoked the blank tile but no tab strip appeared within the wait"}


# ------------------------------------------------------------------ desktop pipeline

def scan_desktop(name: str, model=None, *, launch: bool = True, deepen: Any = True,
                 e1_actions: int = 3, close_if_launched: bool = True, on_window=None,
                 allow_visible: bool = False, force: bool = False, fresh: bool = False,
                 fast: bool = False, e0_budget_s: Optional[float] = None,
                 ready_budget_s: float = 0.0, hwnd_hint: int = 0,
                 ribbon_budget_s: float = 0.0) -> Dict[str, Any]:
    """`fast=True` is the first-contact profile (P1-G): readiness polled at 150-200 ms instead of 400 ms, the start-screen wait capped at
    4 s, the menu crawl held to `e0_budget_s`, no E1 probing (the caller continues exploration later, cumulatively). Same pipeline, same
    knowledge written; only the waits and the exploration budget change.
    `ready_budget_s` > 0 bounds the readiness waits (first-children + tree-stop-growing) to that slice of the caller's scan
    budget, so a slow/huge app can no longer silently burn the historical 20s + 15s and blow any time contract. 0 (default,
    every legacy caller) keeps the old 20/15 caps exactly - the bound is opt-in, never a regression."""
    from core_organs import desktop_grounding as dg
    from core_organs import organ_48_app_behavior_model as bm
    from core_organs import organ_50_layout_map as lm
    from core_organs import background_window as bw
    model = model or bm.get_model()
    key = bm._app_key(name)
    rep: Dict[str, Any] = {"kind": "desktop", "target": name, "app_key": key, "phases": {}}
    t_all = time.time()
    g = dg.DesktopGrounding()
    bw.pin_user_window(_u32.GetForegroundWindow())     # whose window is the user's, for the whole scan
    # fresh=True: always start our OWN window and never reuse (or touch) one that already exists —
    # the safe default for unattended scans, since an existing window may hold the user's work.
    # hwnd_hint: scan THIS exact window (callers that already resolved the handle — hot UIA paths, tests);
    # an existing window is reused, never launched-closed.
    if hwnd_hint and _u32.IsWindow(hwnd_hint):
        fresh = False
        hwnd = hwnd_hint
    else:
        hwnd = 0 if fresh else (g.find_window(name) or 0)
    launched = False
    if not hwnd and launch:
        t = time.time()
        li = launch_hidden(name, fast=fast)
        rep["launch"] = {k: v for k, v in li.items() if k != "hwnd"}
        hwnd, launched = li.get("hwnd", 0), li.get("launched", False)
        rep["phases"]["launch_s"] = round(time.time() - t, 2)
    if hwnd and not (_u32.IsWindow(hwnd) and bm._win_class(hwnd)):     # a vanished/phantom handle: re-resolve once
        hwnd = g.find_window(name) or 0
    rep["hwnd"] = int(hwnd or 0)          # the EXACT window this scan walked/launched — callers must not re-resolve by name
    rep["pre_existing_window"] = bool(hwnd) and not launched
    if not hwnd:
        dlg = (rep.get("launch") or {}).get("already_running_dialog")
        rep["error"] = (f"already running (single instance): its '{dlg}' dialog was refused and the existing "
                        "window was not touched for safety" if dlg
                        else "no window (not running and could not be launched)")
        rep["elapsed_s"] = round(time.time() - t_all, 2)
        return rep
    if on_window:
        try:
            on_window(hwnd)                       # e.g. start a focus/exposure monitor before anything touches the app
        except Exception:
            pass
    rep["window_title"] = bm._win_title(hwnd)[:80]
    rep["window_class"] = bm._win_class(hwnd)
    pid = wt.DWORD()
    _u32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    fg0 = _u32.GetForegroundWindow()
    # POLITE MODE: a window the user can actually see is read passively only (one bulk snapshot);
    # expanding menus / probing would flicker UI in front of them and move their focus.
    polite = (not allow_visible) and bw.user_can_see(hwnd)
    rep["polite_mode"] = polite
    # WARM START: knowledge from an earlier scan of this exact app version is reused, not rebuilt
    exe = bm._exe_of_hwnd(hwnd)
    vh = bm.app_version_hash(exe)
    model.check_version(key, vh)
    existing = model.commands(key, limit=5000)
    e0_cached = (not force) and (any((c.get("origin") or "").startswith("e0:") and not c.get("stale") for c in existing)
                                 or model.step_stats(f"{key}:e0_done:{vh}")["successes"] > 0)
    warm_layout = None if force else lm.layout_cached(model, key, vh)
    layout_cached = warm_layout is not None
    rep["warm"] = {"e0_cached": e0_cached, "layout_cached": layout_cached, "known_commands_before": len(existing)}
    try:
        with bw.BackgroundSession(hwnd) as sess:
            rep["window_mode"] = sess.mode or "visible"
            rep["accessibility"] = wake_accessibility(hwnd)
            # readiness: a freshly started or Chromium app exposes its tree late (bounded growing wait)
            t = time.time()
            n, delay = 0, (0.15 if fast else 0.4)
            # bound the readiness waits from the caller's scan budget when given one; else the historical 20s + 15s
            _rb = float(ready_budget_s or 0.0)
            first_children_cap = (_rb * 0.6) if _rb > 0 else 20.0
            grow_stabilize_cap = (_rb * 0.4) if _rb > 0 else 15.0
            import uiautomation as auto
            while time.time() - t < first_children_cap:
                try:
                    n = len(auto.ControlFromHandle(hwnd).GetChildren())
                except Exception:
                    n = 0
                if n >= 2:
                    break
                time.sleep(delay)
                delay = min(delay * 1.5, 2.0)
            _poll = 0.2 if fast else 0.4
            # then: wait until the tree STOPS GROWING. UWP/WinUI/Office apps resume and populate for a second
            # or two after being un-minimized; mapping at the first moment something exists saw 3 controls
            from core_organs import fast_uia
            _RICH = 1200                          # dynamic real-time guard: a tree this large is obviously present and
            last, steady, grow_end = -1, 0, time.time() + grow_stabilize_cap   #   already populating fast - proving
            while time.time() < grow_end and steady < 2:                       #   "settled" with more FULL snapshots is
                snap = fast_uia.snapshot(hwnd, timeout_ms=6000)                 #   pure cost on a huge app, so stop once
                cnt = len(snap) if snap else 0                                  #   rich. (On a build without IUIAutomation6
                steady = steady + 1 if (cnt == last and cnt > 2) else 0         #   a single snapshot is not time-interruptible,
                last = cnt                                                      #   so limiting HOW MANY we take is the lever.)
                if last >= _RICH:
                    break
                if steady < 2:
                    time.sleep(_poll)
            rep["tree_nodes_when_ready"] = last
            # LAID OUT? A parked UWP/WinUI app may expose controls with EMPTY rectangles (it does not lay
            # out content that is entirely off-screen). Detect that and apply the 1-pixel sliver. This ONLY matters
            # for a sparse parked UI; a rich tree is already laid out, and re-snapshotting it is the dominant cost.
            if last >= _RICH:
                rep["laid_out_fraction"] = None
                rep["layout_fix"] = f"skipped the laid-out/sliver re-check: the tree is already rich ({last} nodes)"
            else:
                snap = fast_uia.snapshot(hwnd, timeout_ms=6000) or []
                named = [n for n in snap if n.name and (set(n.pats) & {"invoke", "toggle", "select", "expand"})]
                laid = sum(1 for n in named if (n.rect[2] > n.rect[0] and n.rect[3] > n.rect[1]))
                rep["laid_out_fraction"] = round(laid / len(named), 2) if named else None
                if named and len(named) >= 8 and laid / len(named) < 0.3 and sess.mode == "parked":
                    if bw.sliver(hwnd):
                        time.sleep(1.2)
                        snap = fast_uia.snapshot(hwnd, timeout_ms=6000) or []
                        named = [n for n in snap if n.name and (set(n.pats) & {"invoke", "toggle", "select", "expand"})]
                        laid = sum(1 for n in named if (n.rect[2] > n.rect[0] and n.rect[3] > n.rect[1]))
                        rep["layout_fix"] = f"sliver applied: laid-out fraction {rep['laid_out_fraction']} -> {round(laid / max(len(named), 1), 2)}"
            rep["phases"]["ready_s"] = round(time.time() - t, 2)
            if not polite:
                try:
                    rep["start_screen"] = leave_start_screen(hwnd, timeout_s=4.0 if fast else 20.0)
                except Exception as exc:
                    rep["start_screen"] = {"error": type(exc).__name__}
            t = time.time()
            if polite:
                rep["e0"] = {"skipped": "polite mode: window is in the user's view; passive read only"}
            elif e0_cached:
                rep["e0"] = {"skipped": f"cached ({len([c for c in existing if (c.get('origin') or '').startswith('e0:')])} menu commands known for this app version)"}
            else:
                e0 = bm.crawl_e0(model, name, hwnd, budget=(bm.DiscoveryBudget(base_s=e0_budget_s * 0.6, extend_s=1.5, max_s=e0_budget_s, patience=6)
                                                              if e0_budget_s else None))
                rep["e0"] = {"commands": e0["ingested"], "stopped": e0["stopped"],
                             "skipped": [s for m in e0["methods"] for s in m["skipped"]][:6]}
            rep["phases"]["e0_menus_s"] = round(time.time() - t, 2)
            t = time.time()
            do_deepen = deepen if (deepen and not polite and not layout_cached) else False
            if layout_cached and not force:
                # WARM START (same law as e0): the layout for this exact version is already mapped — reuse it,
                # do not rebuild. Re-walking a cached Explorer layout cost ~6 s of every scan (measured 2026-10-06)
                # and pushed first-contact past its budget while learning nothing new.
                n_ctrl = None
                try:
                    n_ctrl = model._conn.execute("SELECT COUNT(*) c FROM bm_layout WHERE app_key=?", (key,)).fetchone()["c"]
                except Exception:
                    pass
                lay = {"cached": True, "controls": n_ctrl, "regions": (warm_layout or {}).get("regions"),
                       "region_kinds": None, "deepen": False, "opaque_regions": None,
                       "skipped": "warm start: layout cached for this version"}
            else:
                lay = lm.map_layout(model, name, hwnd, deepen=do_deepen, version_hash=vh,
                                    ribbon_budget_s=ribbon_budget_s)
            rep["phases"]["layout_s"] = round(time.time() - t, 2)
            rep["layout"] = {k: lay.get(k) for k in ("controls", "regions", "region_kinds", "deepen", "deepen_mode",
                                                     "opaque_regions", "skipped", "elapsed_s")}
            rep["layout"]["cached"] = bool(lay.get("cached"))
            rep["sections"] = lay.get("sections", [])[:40]
            try:
                zero = model._conn.execute("SELECT COUNT(*) c FROM bm_layout WHERE app_key=? AND rx0=0 AND ry0=0 AND rx1=0 AND ry1=0", (key,)).fetchone()["c"]
                rep["positions_unknown"] = zero      # controls recorded WITHOUT geometry (e.g. UWP content that is not laid out while hidden)
            except Exception:
                pass
            t = time.time()
            n_e1 = 0 if fast else (e1_actions if not (e0_cached and layout_cached) else min(e1_actions, 1))   # warm: knowledge exists, probe less
            e1 = (bm.explore_e1(model, name, hwnd, max_actions=n_e1, budget_s=30.0)
                  if (n_e1 and not polite) else {"probes": []})
            rep["phases"]["e1_s"] = round(time.time() - t, 2)
            rep["e1"] = {"probes": len(e1["probes"]), "stopped": e1.get("stopped"),
                         "effects_observed": sum(1 for p in e1["probes"] if p.get("effect_observed")),
                         "unwound_all": all(p.get("unwound", True) for p in e1["probes"]),
                         "detail": [{"cmd": p.get("cmd", "")[:40], "s": p.get("elapsed_s"), "effect": p.get("effect_observed"),
                                     "effector": p.get("effector"), "new": len(p.get("new_controls", []))} for p in e1["probes"]],
                         "discovered_controls": sum(len(p.get("new_controls", [])) for p in e1["probes"])}
            guard = None
            try:
                guard = bw._parked.get(hwnd).guard if bw._parked.get(hwnd) else None
            except Exception:
                pass
            rep["focus_guard"] = {"focus_returns": getattr(guard, "refocused", 0), "popups_moved": getattr(guard, "moved", 0), "hook_hits": getattr(guard, "hook_hits", 0)}
        rep["ended_minimized"] = bool(_u32.IsIconic(hwnd))
    except Exception as exc:
        import traceback
        rep["error"] = f"{type(exc).__name__}: {str(exc)[:200]}"
        rep["error_trace"] = traceback.format_exc()[-900:]
    bw.unpin_user_window()
    try:
        rep["layout_commands"] = lm.layout_to_commands(model, key)    # ribbons/toolbars/keypads become commands
        rep["linked"] = lm.link_knowledge(model, key)       # position <-> meaning, both directions
    except Exception as exc:
        rep["linked"] = {"error": type(exc).__name__}
    rep["known_commands"] = len(model.commands(key, limit=5000))
    rep["regions_known"] = len(model.regions(key))
    if launched and close_if_launched:
        rep["closed"] = close_window(hwnd)
    rep["elapsed_s"] = round(time.time() - t_all, 2)
    return rep


# ------------------------------------------------------------------ the one entry point

def scan(target: str, model=None, **kw) -> Dict[str, Any]:
    kind = classify_target(target)
    if kind == "web":
        from core_organs import organ_51_web_layout as wl
        return wl.scan_url(target, model, **{k: v for k, v in kw.items() if k in ("deepen", "budget", "cookies_site", "privacy", "force")})
    return scan_desktop(target, model, **kw)
