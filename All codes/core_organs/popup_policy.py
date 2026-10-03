"""
popup_policy.py -- inspect, classify and resolve blocking dialogs, headless.

Pipeline (one pass = one dialog):
    inspect   UIA read of the dialog's own words: title, message text, button captions/ids
    classify  generic lexicon -> category (overwrite_confirm, save_changes, file_picker,
              permission, cookie_consent, error, info, unknown) - no app names
    decide    non-destructive answer per category (see POLICY); destructive commits and
              elevation/credential prompts are NEVER auto-accepted -> need_human
    deliver   UIA Invoke on the chosen button (fallback: window message to the button's HWND);
              never the physical pointer/keyboard
    verify    the dialog window must actually be gone before the pass counts as handled

`clear_blockers` repeats passes (bounded) so stacked dialogs (a Confirm Save As on top of a
Save As picker) are unwound top-down.
"""

import logging
import re
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

from core_organs import headless_input as hin

logger = logging.getLogger("hojaiga.popup_policy")

try:
    import uiautomation as auto
except Exception:  # pragma: no cover
    auto = None

# Win32 standard dialog button ids -> role (stable across languages)
_ID_ROLE = {"1": "ok", "2": "cancel", "3": "abort", "4": "retry", "5": "ignore",
            "6": "yes", "7": "no", "8": "close", "9": "help", "10": "tryagain", "11": "continue"}

_PICKER_TITLES = ("save as", "save", "open", "export", "import", "browse", "select a file", "select file",
                  "choose file", "choose a file", "upload", "select folder", "browse for folder")
_OVERWRITE_CUES = ("already exists", "replace it", "overwrite", "confirm save as", "do you want to replace")
_SAVE_CHANGES_CUES = ("save changes", "do you want to save", "want to save", "unsaved changes",
                      "save your changes", "changes to")
_PERMISSION_CUES = ("user account control", "administrator", "elevat", "permission", "credential",
                    "password", "sign in", "authenticat", "allow this app to make changes")
_COOKIE_CUES = ("cookie", "consent", "gdpr", "privacy preferences", "we value your privacy")
_ERROR_CUES = ("error", "failed", "cannot", "can't", "could not", "unable", "not responding",
               "stopped working", "problem", "exception", "crash")
_INFO_CUES = ("information", "notice", "update", "welcome", "what's new", "tip", "complete",
              "success", "finished", "done")

# Preference order of button ROLES per category (first available wins). All non-destructive.
POLICY: Dict[str, Tuple[str, ...]] = {
    "overwrite_confirm": ("no", "cancel"),
    "save_changes": ("cancel", "no"),           # keep the document; never 'Don't save' / 'Save' blind
    "file_picker": ("cancel",),
    "error": ("ok", "close", "continue", "ignore", "cancel"),
    "info": ("ok", "close", "continue", "yes", "cancel"),
    "cookie_consent": ("reject", "decline", "no", "close", "cancel", "ok"),
    "unknown": ("cancel", "close", "no", "ok"),
}
_ROLE_WORDS = {
    "ok": ("ok", "okay", "got it", "done", "understood", "i understand", "dismiss"),
    "cancel": ("cancel", "abort"),
    "yes": ("yes",),
    "no": ("no", "don't save", "dont save", "do not save"),
    "close": ("close", "exit"),
    "continue": ("continue", "next", "proceed"),
    "ignore": ("ignore", "skip", "not now", "later", "remind me later", "no thanks"),
    "retry": ("retry", "try again"),
    "reject": ("reject all", "reject", "decline", "necessary only", "only necessary", "deny", "refuse"),
    "decline": ("decline", "deny", "refuse"),
}


@dataclass
class TaskContext:
    """What the running task owns. Set by the autonomy loop; read by every dialog handler
    (including organ_29's background sentinel) so they never cancel a picker the task needs."""
    paths: Tuple[str, ...] = ()
    allow_destructive: bool = False
    mode: str = "inflight"


TASK = TaskContext()


@dataclass
class DialogInfo:
    hwnd: int
    title: str = ""
    class_name: str = ""
    texts: List[str] = field(default_factory=list)
    buttons: List[Tuple[str, str, object]] = field(default_factory=list)  # (name, automation_id, ctrl)
    category: str = "unknown"

    @property
    def message(self) -> str:
        return " ".join(self.texts)

    def brief(self) -> str:
        return (f"'{self.title}' [{self.category}] msg='{self.message[:70]}' "
                f"buttons={[b[0] for b in self.buttons]}")


@dataclass
class Resolution:
    handled: bool
    need_human: bool
    action: str
    dialog: str
    note: str = ""


def _norm(s: str) -> str:
    return re.sub(r"[&‎‏]", "", (s or "")).strip().lower()


def _title_of(hwnd: int) -> str:
    buf = hin.ctypes.create_unicode_buffer(300)
    hin._u32.GetWindowTextW(hwnd, buf, 300)
    return buf.value


def inspect_dialog(hwnd: int, deep: bool = True) -> DialogInfo:
    """Read what the dialog SAYS (UIA), bounded. Pickers skip the deep walk (hundreds of cells)."""
    info = DialogInfo(hwnd=hwnd, title=_title_of(hwnd), class_name=hin._class_name(hwnd))
    if auto is None:
        return info
    try:
        root = auto.ControlFromHandle(hwnd)
        if root is None:
            return info
        is_picker = _norm(info.title) in _PICKER_TITLES
        if is_picker or not deep:
            # Only the confirm/cancel buttons matter for a picker: find them by stable ids.
            for aid in ("1", "2"):
                try:
                    b = root.ButtonControl(AutomationId=aid, searchDepth=8)
                    if b.Exists(0.4, 0.05):
                        info.buttons.append((b.Name or "", aid, b))
                except Exception:
                    pass
            return info
        nodes = 0
        stack = [(root, 0)]
        while stack and nodes < 300:
            c, d = stack.pop()
            nodes += 1
            try:
                t = c.ControlTypeName or ""
                nm = (c.Name or "").strip()
                if t == "TextControl" and nm and nm not in info.texts:
                    info.texts.append(nm)
                elif t == "ButtonControl":
                    info.buttons.append((nm, str(getattr(c, "AutomationId", "") or ""), c))
                if d < 7:
                    for ch in reversed(c.GetChildren()):
                        stack.append((ch, d + 1))
            except Exception:
                continue
    except Exception as exc:  # noqa: BLE001
        logger.debug("[popup] inspect failed: %s", exc)
    return info


def classify(info: DialogInfo) -> str:
    title = _norm(info.title)
    blob = _norm(info.title + " " + info.message)
    if any(c in blob for c in _PERMISSION_CUES):
        return "permission"
    if any(c in blob for c in _OVERWRITE_CUES):
        return "overwrite_confirm"
    if title in _PICKER_TITLES or any(title.startswith(p + " ") for p in ("save as", "open", "browse")):
        return "file_picker"
    if any(c in blob for c in _SAVE_CHANGES_CUES):
        return "save_changes"
    if any(c in blob for c in _COOKIE_CUES):
        return "cookie_consent"
    if any(c in blob for c in _ERROR_CUES):
        return "error"
    if any(c in blob for c in _INFO_CUES):
        return "info"
    return "unknown"


def _button_role(name: str, aid: str) -> str:
    n = _norm(name)
    for role, words in _ROLE_WORDS.items():
        if n in words:
            return role
    return _ID_ROLE.get(aid, "")


def choose_button(info: DialogInfo, roles: Sequence[str]):
    """First available button whose ROLE (caption or standard control id) matches the preference."""
    by_role: Dict[str, Tuple[str, str, object]] = {}
    for name, aid, ctrl in info.buttons:
        r = _button_role(name, aid)
        if r and r not in by_role:
            by_role[r] = (name, aid, ctrl)
        if aid in _ID_ROLE and _ID_ROLE[aid] not in by_role:
            by_role[_ID_ROLE[aid]] = (name, aid, ctrl)
    for role in roles:
        if role in by_role:
            return role, by_role[role]
    return None, None


def _deliver(button) -> Tuple[bool, str]:
    name, aid, ctrl = button
    try:
        ctrl.GetInvokePattern().Invoke()
        return True, "uia-invoke"
    except Exception:
        pass
    try:
        r = ctrl.BoundingRectangle
        h = int(getattr(ctrl, "NativeWindowHandle", 0) or 0)
        if h:
            ok, note = hin.post_click(hin._u32.GetAncestor(h, 2) or h, (r.left + r.right) // 2,
                                      (r.top + r.bottom) // 2)
            return ok, note
    except Exception:
        pass
    return False, "undeliverable"


def resolve_dialog(hwnd: int, *, mode: str = "inflight", task_paths: Sequence[str] = (),
                   allow_destructive: bool = False) -> Resolution:
    """Handle ONE dialog. mode='preflight' = stale cleanup before a run (pickers are cancelled);
    mode='inflight' = a picker the task itself needs (goal names a path) is left to the file-dialog rung."""
    info = inspect_dialog(hwnd)
    info.category = classify(info)
    cat = info.category
    brief = info.brief()
    paths = [p.lower() for p in task_paths if p]

    if cat == "permission":
        return Resolution(False, True, "need_human", brief, "elevation/credential prompt: never auto-accepted")

    if cat == "file_picker" and mode == "inflight" and paths:
        return Resolution(False, False, "owned-by-task", brief, "task names a path; file-dialog rung drives it")

    if cat == "overwrite_confirm":
        names = [p.replace("/", "\\").rsplit("\\", 1)[-1] for p in paths]
        ours = any(n and n in _norm(info.message) for n in names)
        if ours and allow_destructive:
            role, btn = choose_button(info, ("yes",))
            if btn:
                ok, how = _deliver(btn)
                return Resolution(ok, False, f"yes({how})", brief, "explicitly authorised overwrite of the task's own file")
        if mode == "inflight" and ours:
            return Resolution(False, True, "need_human", brief,
                              "task's own target already exists: overwrite needs explicit allow_destructive")
        # Not ours / not authorised: the non-destructive answer is 'No' (nothing is replaced).

    roles = POLICY.get(cat, POLICY["unknown"])
    role, btn = choose_button(info, roles)
    # A dialog that has just appeared may not have rendered its content yet (UIA then shows only the
    # title bar's Close). Re-read a few times, bounded, before concluding there is no safe button.
    for _ in range(9):          # bounded ~4.5 s: a busy machine renders dialog content late
        if btn is not None:
            break
        time.sleep(0.5)
        info = inspect_dialog(hwnd)
        info.category = classify(info)
        cat, brief = info.category, info.brief()
        if cat == "permission":
            return Resolution(False, True, "need_human", brief, "elevation/credential prompt: never auto-accepted")
        role, btn = choose_button(info, POLICY.get(cat, POLICY["unknown"]))
    if btn is None:
        return Resolution(False, True, "need_human", brief, "no safe button recognised - not guessing")
    ok, how = _deliver(btn)
    return Resolution(ok, False, f"{role}({how})", brief, "")


def blocking_dialogs(root_hwnd: int, exclude: Sequence[int] = ()) -> List[int]:
    """Visible dialog windows owned by the target's process (#32770 and friends), topmost first."""
    out = []
    skip = set(exclude)
    for h in hin.process_windows(root_hwnd, include_hidden=False):
        if h == root_hwnd or h in skip:
            continue
        if hin._class_name(h) == "#32770":
            out.append(h)
    return out


def clear_blockers(root_hwnd: int, *, mode: str = "inflight", task_paths: Sequence[str] = (),
                   allow_destructive: bool = False, max_rounds: int = 6,
                   exclude: Sequence[int] = ()) -> Dict[str, object]:
    """Unwind stacked dialogs top-down. Returns {handled:[...], need_human:bool, left:[...]}"""
    handled: List[str] = []
    need_human = False
    left: List[str] = []
    seen_stuck: Dict[int, int] = {}
    for _ in range(max_rounds):
        dialogs = blocking_dialogs(root_hwnd, exclude)
        if not dialogs:
            break
        progressed = False
        for hwnd in dialogs:
            if seen_stuck.get(hwnd, 0) >= 2:
                continue
            res = resolve_dialog(hwnd, mode=mode, task_paths=task_paths, allow_destructive=allow_destructive)
            if res.need_human:
                need_human = True
                handled.append(f"HUMAN:{res.dialog} ({res.note})")
                seen_stuck[hwnd] = 9
                continue
            if res.action == "owned-by-task":
                seen_stuck[hwnd] = 9
                continue
            gone = False
            end = time.time() + 1.6          # bounded wait for the dialog to actually close
            while time.time() < end:
                time.sleep(0.12)
                if not hin.is_alive(hwnd) or not hin._u32.IsWindowVisible(hwnd):
                    gone = True
                    break
            handled.append(f"{res.action}:{res.dialog}" + ("" if gone else " [still open]"))
            if gone:
                progressed = True
            else:
                seen_stuck[hwnd] = seen_stuck.get(hwnd, 0) + 1
        if not progressed:
            break
    left = [_title_of(h) for h in blocking_dialogs(root_hwnd, exclude) if seen_stuck.get(h, 0) < 9]
    return {"handled": handled, "need_human": need_human, "left": left}
