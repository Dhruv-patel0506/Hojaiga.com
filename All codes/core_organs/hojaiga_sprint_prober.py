"""
HOJAIGA SPRINT: Interaction Prober
Act on elements, measure what changed, learn what the app does.

Two kinds of action, cheapest first:
  * pattern action  - UIA Invoke / Toggle / Expand / Select (no mouse needed)
  * point action    - a real click at the element centre (for grids and canvas apps)
After every action we diff the WINDOW region (not the whole desktop, so the taskbar
clock cannot fake a change) and watch for new windows belonging to the same process
(that is how a dialog is discovered).
"""

import asyncio
import hashlib
import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import uiautomation as auto

MISSING = []
try:
    import numpy as np
    import mss
    from PIL import Image
except ImportError as exc:  # pragma: no cover - environment guard
    np = mss = Image = None
    MISSING.append(str(exc))

# This repo refuses physical input outright (headless_input.physical_input_blocked:
# "Always refuses: there is no opt-out") and provides posted-message input instead.
# Everything here that presses a key, types text or clicks therefore goes through it:
# a posted message is addressed to one hwnd, so it cannot land in whichever window
# happens to hold focus - which is how an unguarded SendKeys once scribbled its marker
# into a document the scan did not own.
try:
    import headless_input as hi
except ImportError as exc:  # pragma: no cover - environment guard
    hi = None
    MISSING.append(str(exc))

# Actions that can destroy user data, end the session, or hide the window we are
# mid-scan on (minimize/maximize/restore). Never probed unless allow_destructive=True.
DESTRUCTIVE = re.compile(
    r"\b(close|exit|quit|shutdown|delete|remove|format|clear all|discard|undo redo|"
    r"power|sign out|force|empty recycle|minimize|maximize|restore)\b"
)

# Keyboard shortcuts worth trying. Ctrl+S is deliberately NOT here: on a document
# with a path it saves silently, and probing must never write to a user's file.
# Save/Open are learned from the menu text instead (see probe_menus).
SAFE_SHORTCUTS = [
    ("ctrl+n", "new"),
    ("ctrl+f", "find"),
]

MENU_TYPES = {"MenuItemControl", "MenuControl", "MenuBarControl"}
# Window-frame chrome and account widgets: pressing them logs the user in somewhere,
# moves the window, or opens the system menu. Not app knowledge, so not probed.
SKIP_CHROME = {"system", "user avatar", "what's new", "minimize", "maximize", "restore"}
MENU_WORD_HINTS = ("file", "edit", "view", "help", "format", "tools", "window",
                   "more options", "navigation")
# The only buttons safe to press while clearing a dialog our own probe opened.
# Compared with all punctuation stripped. "Save"/"OK"/"Yes" are deliberately absent:
# pressing one of those would write a file the user never asked for.
CANCEL_LABELS = {"cancel", "no", "dontsave", "donotsave", "discard",
                 "discardchanges", "closewithoutsaving", "neverstore",
                 "noremember", "notnow", "notoday"}


def _norm(text):
    return re.sub(r"[^a-z0-9 ]", " ", (text or "").lower()).strip()


class HOJAIGAProber:
    def __init__(self, allow_destructive=False, use_clicks=True):
        self.allow_destructive = allow_destructive
        self.use_clicks = use_clicks
        self._proc_pid = None
        self._sct = None  # lazily opened, reused for every frame
        self._baseline_windows = {}  # hwnd -> title of the app's windows before we touched anything
        self._seen_commands = set()  # menu items already recorded, so two menus do not double-count

    # ---- measurement -----------------------------------------------------
    def _hash(self, img):
        if img is None or np is None:
            return ""
        arr = np.asarray(img.resize((96, 96)), dtype="uint8")
        return hashlib.md5(arr.tobytes()).hexdigest()

    def _diff(self, a, b):
        """(mean_change, fraction_of_pixels_changed) both 0..1"""
        if a is None or b is None or np is None:
            return 0.0, 0.0
        wa = min(a.size[0], b.size[0])
        ha = min(a.size[1], b.size[1])
        x = np.abs(np.asarray(a.resize((wa, ha)), dtype=np.int16)
                   - np.asarray(b.resize((wa, ha)), dtype=np.int16))
        changed = (x.max(axis=2) > 24)
        return float(x.mean()) / 255.0, float(changed.mean())

    # ---- window bookkeeping ----------------------------------------------
    def _sibling_windows(self):
        """hwnd -> title for every window this app owns. Keyed by hwnd, not by
        (hwnd, title): a tab renaming itself is not a new dialog."""
        hwnds = {}
        for ctrl in auto.GetRootControl().GetChildren():
            try:
                if self._proc_pid and ctrl.ProcessId == self._proc_pid:
                    rect = ctrl.BoundingRectangle
                    if rect.width() > 40 and rect.height() > 40:
                        hwnds[ctrl.NativeWindowHandle] = ctrl.Name or ""
            except Exception:
                continue
        return hwnds

    def _titles(self):
        """Titles this app is showing. A document's own text can leak into its title
        bar ("*draft - Notepad"), which is how a probe once read back an empty field,
        declared its cleanup verified, and left its marker in the user's tab."""
        try:
            return set(self._sibling_windows().values())
        except Exception:
            return set()

    def _focus(self, window):
        """Activate the window under test and PROVE it reached the foreground.

        Delegates to perception.ensure_foreground: a screenshot of a window that is not
        truly on top reads the app that is, so both the pixel diff and the OCR fallback
        depend on this actually landing. Returns the verified foreground state.
        """
        try:
            from hojaiga_sprint_perception import ensure_foreground
            return ensure_foreground(window)
        except Exception:
            return False

    def _input_hwnd(self, window, ctrl=None):
        """Which hwnd to address posted input to.

        Posted characters belong to the focused control, not to the frame - which is
        why headless_input exposes focused_control(). Prefer the control's own window,
        then whatever Win32 reports as focused inside the frame, then the frame.
        Minimised or gone windows are skipped: Windows does not render them and
        post_click refuses their coordinates outright.
        """
        top = window.NativeWindowHandle
        candidates = [getattr(ctrl, "NativeWindowHandle", 0) if ctrl is not None else 0]
        if hi is not None:
            candidates.append(hi.focused_control(top))
        candidates.append(top)
        for cand in candidates:
            if cand and hi is not None and hi.is_alive(cand) and not hi.is_minimized(cand):
                return cand
        return top

    def _restore_field(self, ctrl, original, hwnd):
        """Put a text field back to exactly the characters it held before we typed.

        Precise backspaces alone are not enough: autocomplete can insert extra
        characters, so the count we delete is wrong. When the field was empty before
        us, select-all + delete is still provably safe - the only content there is
        content we added. Otherwise we stop and report the residue rather than risk
        touching text that belongs to the user.
        """
        for _ in range(3):
            try:
                now = ctrl.GetValuePattern().Value or ""
            except Exception:
                return False
            if now == original:
                return True
            if original.strip() == "":
                # Everything in here is text we added, so clearing the whole field is
                # an exact restore. Posted, never physical.
                hi.post_key_combo(hwnd, "ctrl+a")
                time.sleep(0.15)
                hi.post_key_combo(hwnd, "del")
                time.sleep(0.2)
                continue
            return False
        return False

    def _revert(self, window, escape=1, dialog_hwnd=0):
        """Undo what our probe opened. Escape is only pressed when something moved,
        and the dialog sweep only runs for a dialog we actually saw: walking the
        desktop costs ~135 ms and 90% of probes open nothing."""
        if escape <= 0:
            return
        self._focus(window)
        if hi is not None:
            # Posted to the dialog when there is one (an Escape on the frame leaves a
            # modal open), otherwise to the window under test.
            target = dialog_hwnd or window.NativeWindowHandle
            for _ in range(escape):
                delivered, _note = hi.post_key_combo(target, "esc")
                time.sleep(0.12)
                if not delivered:
                    break
        if dialog_hwnd:
            self._dismiss(dialog_hwnd)

    def _new_window(self, exclude_label=""):
        """A window this app just opened. Asked after every action, not only when the
        pixels moved: a modal can sit outside the rectangle we are watching, so the
        image diff alone cannot see it."""
        try:
            for hwnd, name in self._sibling_windows().items():
                if hwnd not in self._baseline_windows and name \
                        and _norm(name) != _norm(exclude_label):
                    return hwnd, name
        except Exception:
            pass
        return 0, ""

    def _dismiss(self, hwnd):
        """Close a dialog our own probe opened - by its cancel/discard button only.
        Never the main window, never OK or Save (that writes the file the dialog was
        about to create). Labels are compared with ALL punctuation stripped, because
        "Don't save" becomes "don t save" when an apostrophe turns into a space, and
        a silently unmatched button means the prompt stays open."""
        try:
            dlg = auto.ControlFromHandle(hwnd)
            if dlg is None:
                return
            stack = [(dlg, 0)]
            while stack:
                node, depth = stack.pop()
                try:
                    label = re.sub(r"[^a-z0-9]", "", (node.Name or "").lower())
                    if label in CANCEL_LABELS:
                        pattern = node.GetPattern(auto.PatternId.InvokePattern)
                        if pattern is not None:
                            pattern.Invoke()
                            return
                except Exception:
                    pass
                if depth < 6:
                    try:
                        for child in node.GetChildren():
                            stack.append((child, depth + 1))
                    except Exception:
                        pass
        except Exception:
            pass

    # ---- acting ----------------------------------------------------------
    def _actuate(self, element, window):
        """Perform the action. Returns the method actually used, or None."""
        ctrl = element.get("_ctrl")
        action = element.get("action")
        if ctrl is not None:
            try:
                if action == "invoke":
                    ctrl.GetPattern(auto.PatternId.InvokePattern).Invoke()
                    return "uia-invoke"
                if action == "toggle":
                    ctrl.GetPattern(auto.PatternId.TogglePattern).Toggle()
                    return "uia-toggle"
                if action == "expand":
                    pattern = ctrl.GetPattern(auto.PatternId.ExpandCollapsePattern)
                    pattern.Expand()
                    return "uia-expand"
                if action == "select":
                    ctrl.GetPattern(auto.PatternId.SelectionItemPattern).Select()
                    return "uia-select"
                # action == "type": fall through to the click below, which focuses the field
            except Exception:
                pass
        # Position click: reached for a "type" control that failed its pattern, AND for
        # an OCR target that has no UIA control at all (_ctrl is None). Posted to the
        # child window under that point, so no cursor moves and it cannot land elsewhere.
        if self.use_clicks and hi is not None:
            x = element["x"] + element["width"] // 2
            y = element["y"] + element["height"] // 2
            rect = window.BoundingRectangle
            if not (rect.left <= x <= rect.right and rect.top <= y <= rect.bottom):
                return None  # never click outside the app we are teaching
            delivered, _note = hi.post_click(window.NativeWindowHandle, int(x), int(y))
            return "post-click" if delivered else None
        return None

    # ---- OCR fallback: naming controls an app never publishes to UIA -------
    def _ocr_targets(self, perception_data, window_rect, cap=25):
        """Turn OCR text regions into click targets for a UIA-blind app.

        Region coordinates arrive relative to the window screenshot, so the window
        origin is added to reach the screen point post_click expects. Only the app's
        own on-screen words become targets, filtered by the same destructive/chrome
        rules as UIA controls - a nameless patch of pixels is not worth clicking, and
        a label that says 'delete' is not clicked on someone else's document.
        """
        regions = perception_data.get("ocr_results") or []
        if not regions or not window_rect or len(window_rect) < 4:
            return []
        # OCR boxes are measured from the CLAMPED capture origin, not window_rect:
        # a maximised window's rect starts at -9, but the grab (and so the text)
        # starts at the monitor edge (0). Offsetting by the wrong origin would aim
        # every click 9px high-left and off the real control.
        ox, oy = perception_data.get("capture_origin") or (window_rect[0], window_rect[1])
        left, top, width, height = window_rect[0], window_rect[1], window_rect[2], window_rect[3]
        right, bottom = left + width, top + height
        out, seen = [], set()
        # Biggest glyphs first: a toolbar label is a better target than anti-aliased
        # noise, and the cap then keeps the meaningful end of the list.
        for r in sorted(regions, key=lambda z: -(z["width"] * z["height"])):
            text = (r.get("text") or "").strip()
            low = _norm(text)
            if len(low) < 2 or low in seen:
                continue
            if (DESTRUCTIVE.search(low) and not self.allow_destructive) or low in SKIP_CHROME:
                continue
            x, y = ox + r["x"], oy + r["y"]
            w, h = r["width"], r["height"]
            if w < 8 or h < 8:
                continue  # speckle, not a control
            cx, cy = x + w // 2, y + h // 2
            if not (left <= cx <= right and top <= cy <= bottom):
                continue
            seen.add(low)
            out.append({
                "label": text[:40], "control_type": "OCRText",
                "x": x, "y": y, "width": w, "height": h,
                "action": "invoke", "enabled": True, "offscreen": False,
                "_ctrl": None, "source": "ocr",
            })
            if len(out) >= cap:
                break
        return out

    # ---- menu reading: the safe way to learn an app's vocabulary -----------
    def _collect_menu_labels(self, window):
        """Every menu-ish label currently visible under the window."""
        labels = set()

        def walk(ctrl, depth):
            if depth > 14 or len(labels) > 400:
                return
            try:
                if ctrl.ControlTypeName in ("MenuItemControl", "ButtonControl", "TextControl"):
                    name = (ctrl.Name or "").strip()
                    if name:
                        labels.add(_norm(name))
            except Exception:
                return
            try:
                for child in ctrl.GetChildren():
                    walk(child, depth + 1)
            except Exception:
                pass

        walk(window, 0)
        # A classic Win32 menu opens in its own popup window, outside our subtree.
        try:
            hwnd, _name = self._new_window()
            if hwnd:
                walk(auto.ControlFromHandle(hwnd), 0)
        except Exception:
            pass
        return labels

    def _menu_roots(self, window, limit=10):
        """Top-level menus / nav buttons worth opening, in reading order."""
        found = []

        def walk(ctrl, depth):
            if depth > 6 or len(found) >= limit:
                return
            try:
                label = (ctrl.Name or "").strip()
                ctype = ctrl.ControlTypeName
                rect = ctrl.BoundingRectangle
            except Exception:
                return
            if label and rect.width() > 1 and rect.height() > 1:
                low = _norm(label)
                words = low.split()
                interesting = low in MENU_WORD_HINTS or (bool(words) and words[0] in MENU_WORD_HINTS)
                if interesting and (ctype in ("MenuItemControl", "ButtonControl", "TabItemControl",
                                              "SplitButtonControl")):
                    try:
                        openable = (ctrl.GetPattern(auto.PatternId.ExpandCollapsePattern) is not None
                                    or ctrl.GetPattern(auto.PatternId.InvokePattern) is not None)
                    except Exception:
                        openable = False
                    if openable:
                        found.append({"ctrl": ctrl, "label": label, "control_type": ctype})
            try:
                for child in ctrl.GetChildren():
                    walk(child, depth + 1)
            except Exception:
                pass

        walk(window, 0)
        return found

    def probe_menus(self, window, budget_seconds=8.0):
        """Open each menu, READ the commands it offers, close it. Nothing is clicked:
        a menu's text is the app's command vocabulary and UIA hands it over without
        touching the user's document. This is where 'save', 'print' and 'find' come
        from - no button has to be pressed, no file has to be written."""
        found = []
        deadline = time.time() + budget_seconds
        for menu in self._menu_roots(window):
            if time.time() > deadline:
                break
            label = menu["label"]
            if DESTRUCTIVE.search(_norm(label)) and not self.allow_destructive:
                continue
            self._focus(window)
            before = self._collect_menu_labels(window)
            element = {"label": label, "action": "expand", "x": 0, "y": 0,
                       "width": 0, "height": 0, "control_type": menu["control_type"],
                       "_ctrl": menu["ctrl"], "enabled": True, "offscreen": False}
            method = self._actuate(element, window)
            if not method:
                continue
            time.sleep(0.3)
            after = self._collect_menu_labels(window)
            new_items = sorted(after - before)
            for item in new_items[:40]:
                if item and item != _norm(label) and item not in self._seen_commands:
                    self._seen_commands.add(item)
                    found.append({
                        "element_label": f"{label}: {item.title()}",
                        "element_x": 0, "element_y": 0,
                        "effect_type": "offers_command",
                        "change_magnitude": 0.0,
                        "method": "read-menu",
                        "source": "uia",
                        "control_type": "MenuItem",
                        "detail": f"offered under {label}",
                        "dialog": "",
                    })
            if new_items:
                print(f"  [M] {label:<14} offers {len(new_items)} commands: "
                      f"{', '.join(i[:14] for i in new_items[:8])}")
            self._revert(window, escape=1)
            try:
                pattern = menu["ctrl"].GetPattern(auto.PatternId.ExpandCollapsePattern)
                if pattern is not None and pattern.ExpandCollapseState == 1:
                    pattern.Collapse()
                    time.sleep(0.15)
            except Exception:
                pass
            self._baseline_windows = self._sibling_windows()
        return found

    def _classify(self, mean_change, frac_changed, element, dialog=""):
        """What kind of thing just happened.

        Shape first, label words second: a control named 'Open Navigation' that
        repaints a strip of the window is a MENU, whatever its name suggests.
        """
        low = _norm(element.get("label", ""))
        action = element.get("action")
        if dialog:
            return "opens_dialog"
        if frac_changed < 0.002 and mean_change < 0.004:
            return "no_visible_change"
        if action == "toggle":
            return "toggles_state"
        if action == "expand" or any(k in low for k in ("menu", "navigation", "more options", "hamburger")):
            return "opens_menu"
        if any(k in low for k in ("save", "apply", "confirm")):
            return "save_or_confirm"
        if any(k in low for k in ("cancel", "back", "dismiss")):
            return "close_or_cancel"
        if any(k in low for k in ("copy", "paste", "cut")):
            return "clipboard_action"
        if any(k in low for k in ("new", "create", "insert", "add")):
            return "creates_or_opens"
        if frac_changed > 0.30:
            return "replaces_view"
        if frac_changed > 0.05:
            return "ui_changed"
        return "local_change"

    # ---- text capability --------------------------------------------------
    def _probe_text_input(self, window, targets):
        """Can the app accept typed text?

        Only ever probes a control that is ALREADY EMPTY, and removes exactly the
        characters it typed. Never select-all, never SetValue on a field holding the
        user's own data - scanning a document that is not ours must not edit it.
        """
        edits = [e for e in targets
                 if e.get("action") == "type" and not e["offscreen"]
                 and e.get("_ctrl") is not None]
        edits.sort(key=lambda e: -e["width"] * e["height"])
        marker = "hojaiga_probe_42"
        for element in edits[:3]:
            ctrl = element["_ctrl"]
            try:
                try:
                    original = ctrl.GetValuePattern().Value or ""
                except Exception:
                    original = ""
                if original.strip():
                    continue  # someone's content; not ours to touch
            except Exception:
                continue

            self._focus(window)
            before = self._snapshot(window)
            titles_before = self._titles()
            if not self._actuate(element, window):
                continue
            time.sleep(0.3)
            # Characters go to the field's own hwnd, so no other window can receive
            # them. If the app ignores posted input, nothing is typed and the
            # capability is reported as unproven rather than guessed at.
            target = self._input_hwnd(window, ctrl)
            delivered, note = (hi.post_text(target, marker) if hi is not None
                               else (False, "headless_input unavailable"))
            if not delivered:
                print(f"  [T] - text not deliverable to this app ({note[:60]})")
                return None
            time.sleep(0.5)
            after = self._snapshot(window)
            mean, frac = self._diff(before, after)
            try:
                value_now = ctrl.GetValuePattern().Value or ""
                # The app exposes its text: proof means our marker is in it. A pixel
                # change elsewhere is not evidence of typing - a flyout opening would
                # move pixels and would have been recorded as a false capability.
                accepted = marker in value_now
            except Exception:
                accepted = frac > 0.0  # no text API: fall back on what visibly changed

            # Remove what we typed, then PROVE the field is back to the state we found
            # it in. Counting backspaces is not sufficient on its own: autocomplete can
            # add characters we never sent, so an exact-count delete can leave the
            # marker sitting in the field. _restore_field finishes the job and says so
            # when it cannot.
            for _ in range(len(marker)):
                hi.post_key_combo(target, "backspace")
            time.sleep(0.3)
            residue = not self._restore_field(ctrl, original, target)
            # The field is not the whole story: an editor can report an empty value
            # while the document it belongs to still holds our text, and that shows up
            # in the title bar. Both channels are checked, neither is trusted alone.
            leaked = any(marker in t for t in self._titles() - titles_before)
            if leaked:
                print("  [T] ! marker surfaced in a window title - the document is "
                      "not ours to edit, treating it as residue")
                residue = True

            if accepted:
                return {
                    "element_label": element["label"] or "text area",
                    "element_x": element["x"], "element_y": element["y"],
                    "effect_type": "accepts_text_input",
                    "change_magnitude": round(frac, 4),
                    "method": "type",
                    "source": "uia",
                    "control_type": element["control_type"],
                    "detail": f"typed {marker!r} into an empty {element['control_type'].lower()} and it appeared"
                              + (" [WARNING: probe text could not be removed]" if residue else ""),
                    "dialog": "",
                }
            self._revert(window)
            if residue:
                # Our text is still in this field: probing another one risks leaving a
                # second mess behind and clicking into the user's content.
                print("  [T] ! residue left in "
                      f"{element['label']!r} - stopping the text probe")
                break
        return None

    # ---- scratch document: proving text input without touching a user's file --
    def _tab_count(self, window):
        """How many tabs this app is showing. Used to prove a tab is OURS."""
        count = [0]

        def walk(ctrl, depth):
            if depth > 20 or count[0] > 200:
                return
            try:
                if ctrl.ControlTypeName == "TabItemControl":
                    count[0] += 1
                for child in ctrl.GetChildren():
                    walk(child, depth + 1)
            except Exception:
                return

        walk(window, 0)
        return count[0]

    def _find_text(self, marker, max_nodes=1500):
        """Does any control of THIS app now show this text? Read-only sweep of our own
        windows, keyed on ValuePattern - no clicks, so the focused document keeps the
        typing target. Scoped to our process: walking the whole desktop tree would be
        slow and could read another app's fields."""
        for hwnd in self._sibling_windows():
            try:
                root = auto.ControlFromHandle(hwnd)
            except Exception:
                continue
            if root is None:
                continue
            stack = [(root, 0)]
            seen = 0
            while stack and seen < max_nodes:
                node, depth = stack.pop()
                seen += 1
                try:
                    value = node.GetValuePattern().Value
                    if value and marker in value:
                        return (node.Name or "text area")[:60]
                except Exception:
                    pass
                if depth < 20:
                    try:
                        for child in node.GetChildren():
                            stack.append((child, depth + 1))
                    except Exception:
                        pass
        return ""

    # Which key creates a new document differs per app: in the 2026 Notepad Ctrl+T is
    # a new TAB and Ctrl+N is a new WINDOW; in Word both are windows; in a browser
    # Ctrl+T is a tab. Try them in order and keep only the one we can PROVE produced
    # a fresh document, so cleanup never targets something the user already had.
    SCRATCH_KEYS = ("ctrl+t", "ctrl+n")

    def _open_scratch_document(self, window):
        """(kind, handle, key) describing the document we just created, or None.
        kind == "tab" -> handle is the new tab count; "window" -> handle is its hwnd."""
        hwnd = self._input_hwnd(window)
        for key in self.SCRATCH_KEYS:
            tabs_before = self._tab_count(window)
            windows_before = set(self._sibling_windows())
            self._focus(window)
            delivered, _note = hi.post_key_combo(hwnd, key)
            if not delivered:
                continue
            time.sleep(1.0)
            tabs_after = self._tab_count(window)
            new_windows = set(self._sibling_windows()) - windows_before
            if tabs_after > tabs_before:
                return "tab", tabs_after, key
            if len(new_windows) == 1:
                return "window", list(new_windows)[0], key
            # Provably nothing new: back out and try the other key.
            self._revert(window, escape=1)
        return None

    def _probe_text_on_scratch_document(self, window):
        """Learn "this app accepts typed text" the only safe way when every text area
        on screen already holds the user's content: create a document ourselves, type
        into that, delete exactly our characters, close the document we made.

        Typing goes to the focused control and is verified by reading the tree, never
        by clicking a field - clicking a field could select one of the user's tabs.
        """
        marker = "hojaiga_probe_42"
        opened = self._open_scratch_document(window)
        if not opened:
            # Nothing provably new: do not type, and do not press Ctrl+W - that would
            # close whatever tab the user was already on.
            print("  [T] - no provably-empty scratch document; text input left unproven")
            return None
        kind, ours, create_key = opened
        self._baseline_windows = self._sibling_windows()

        def close_ours():
            try:
                if kind == "tab":
                    # Ctrl+W closes whichever tab is ACTIVE. Ours is active, because we
                    # just created it and posted input does not move focus. Addressed
                    # to this window only, so it can never hit another app.
                    hi.post_key_combo(self._input_hwnd(window), "ctrl+w")
                    time.sleep(0.7)
                else:
                    import ctypes
                    ctypes.windll.user32.PostMessageW(ours, 0x0010, 0, 0)  # WM_CLOSE
                    time.sleep(0.5)
            except Exception:
                pass
            # An edited document can still be flagged as changed even after we emptied
            # it: answer the prompt "don't save", never "save".
            hwnd, _name = self._new_window()
            if hwnd:
                self._dismiss(hwnd)
                self._baseline_windows = self._sibling_windows()

        print(f"  [T] scratch {kind} created by {create_key}")
        titles_before = self._titles()
        top = ours if kind == "window" else window.NativeWindowHandle
        if not hi.is_alive(top) or hi.is_minimized(top):
            print("  [T] - scratch document is not reachable, refusing to type")
            close_ours()
            return None
        delivered, note = hi.post_text(hi.focused_control(top), marker)
        if not delivered:
            print(f"  [T] - text not deliverable to the scratch document ({note[:50]})")
            close_ours()
            return None
        time.sleep(0.6)
        landed = self._find_text(marker)
        # This document was empty the moment we created it, so every character in it
        # is ours: select-all + delete is a provably exact cleanup. Backspacing our
        # own length is not - autocomplete adds characters we never sent.
        clear = hi.focused_control(top)
        hi.post_key_combo(clear, "ctrl+a")
        time.sleep(0.15)
        hi.post_key_combo(clear, "del")
        time.sleep(0.2)
        close_ours()
        # Same double-check as the field probe: if our marker shows up in a title that
        # did not have it before, some document still holds it - including, possibly,
        # one of the user's.
        still_there = [t for t in self._titles() - titles_before if marker in t]
        if still_there:
            print(f"  [T] ! marker still visible in {still_there[0][:60]!r}")

        if not landed:
            return None
        return {
            "element_label": landed,
            "element_x": 0, "element_y": 0,
            "effect_type": "accepts_text_input",
            "change_magnitude": 0.0,
            "method": "type",
            "source": "uia",
            "control_type": "Document",
            "detail": f"typed into a fresh {kind} we created, then closed it"
                      + (" [WARNING: marker still visible in a window title]"
                         if still_there else ""),
            "dialog": "",
        }

    def _monitor(self):
        if self._sct is None:
            self._sct = mss.MSS()
        return self._sct

    def _snapshot(self, window):
        """One frame of just this window. The MSS handle is reused: opening it for
        every grab costs more than the grab itself."""
        if mss is None or np is None:
            return None
        rect = window.BoundingRectangle
        sct = self._monitor()
        virtual = sct.monitors[0]
        left = max(rect.left, virtual["left"])
        top = max(rect.top, virtual["top"])
        right = min(rect.right, virtual["left"] + virtual["width"])
        bottom = min(rect.bottom, virtual["top"] + virtual["height"])
        if right - left < 4 or bottom - top < 4:
            return None
        shot = sct.grab({"left": left, "top": top,
                         "width": right - left, "height": bottom - top})
        return Image.frombytes("RGB", shot.size, shot.rgb)

    def _settle(self, window, max_wait=1.0):
        """Grab frames until the picture stops moving. A highlight that lands in
        100 ms is measured in 100 ms; a dialog that needs 800 ms gets its 800 ms."""
        previous = self._snapshot(window)
        start = time.time()
        while time.time() - start < max_wait:
            time.sleep(0.1)
            current = self._snapshot(window)
            if current is None or self._hash(previous) == self._hash(current):
                return current
            previous = current
        return previous

    # ---- main loop ---------------------------------------------------------
    async def probe_app(self, window, perception_data, app_name, budget_seconds=10,
                        probe_shortcuts=False, max_elements=60, read_menus=True,
                        scratch_text=False):
        start_time = time.time()
        discovered = []
        self._proc_pid = window.ProcessId
        self._focus(window)
        self._baseline_windows = self._sibling_windows()

        # Menus are read before anything is clicked: they name the app's commands
        # (save, print, find) without a single destructive action.
        if read_menus:
            menu_budget = min(max(4.0, budget_seconds * 0.3), 12.0)
            print(f"[PROBE] Reading menus ({menu_budget:.0f}s)...")
            discovered += self.probe_menus(window, menu_budget)

        # Then shortcuts: high value, and they must not be starved by the element budget.
        if probe_shortcuts:
            discovered += await self._probe_keyboard(window, start_time, budget_seconds)

        elements = perception_data["uia_elements"]
        window_rect = perception_data.get("window_rect") or ()

        # Live walk of the tree for actionable controls. Actions are read from the
        # LIVE control, not paired back to the perception snapshot by position: two
        # nested elements share a rect all the time and the pairing would silently
        # hand us the container instead of the button.
        from hojaiga_sprint_perception import _detect_action
        targets = []

        def walk(ctrl, depth):
            if len(targets) >= max_elements or depth > 24:
                return
            try:
                rect = ctrl.BoundingRectangle
                ctype = ctrl.ControlTypeName
                label = ((ctrl.Name or "").strip() or (ctrl.AutomationId or "").strip()
                         or ctype.replace("Control", ""))[:80]
                action = _detect_action(ctrl) if ctrl.IsEnabled else None
            except Exception:
                return
            if action and rect.width() > 1 and rect.height() > 1:
                if ctype == "TabItemControl" and not self.allow_destructive:
                    action = None  # a tab is the user's content, not a command to learn
                if _norm(label) in SKIP_CHROME:
                    action = None  # frame chrome: it moves the window, it is not a feature
            if action and window_rect:
                inside = (rect.left >= window_rect[0] - 4 and rect.top >= window_rect[1] - 4
                          and rect.right <= window_rect[0] + window_rect[2] + 4
                          and rect.bottom <= window_rect[1] + window_rect[3] + 4)
                if not inside:
                    action = None
            if action:
                targets.append({
                    "label": label, "control_type": ctype.replace("Control", ""),
                    "x": rect.left, "y": rect.top,
                    "width": rect.width(), "height": rect.height(),
                    "action": action, "enabled": True, "offscreen": False, "_ctrl": ctrl,
                })
            try:
                for child in ctrl.GetChildren():
                    walk(child, depth + 1)
                    if len(targets) >= max_elements:
                        return
            except Exception:
                pass

        walk(window, 0)  # UIA is single-apartment: everything runs on the calling thread
        await asyncio.sleep(0)

        candidates = [e for e in targets
                      if not (DESTRUCTIVE.search(_norm(e["label"])) and not self.allow_destructive)]
        print(f"[PROBE] {len(candidates)} actionable elements queued "
              f"({len(targets) - len(candidates)} skipped as destructive)")

        # A UIA-blind app (Blender, a game engine, a canvas Electron build) publishes
        # nothing the tree can name. When there is barely anything to probe, fall back
        # to what the screen actually says: OCR regions become click targets, probed
        # exactly like a real control and tagged source=ocr so the store stays honest.
        if len(candidates) < 5:
            ocr_targets = self._ocr_targets(perception_data, window_rect)
            if ocr_targets:
                print(f"[PROBE] UIA sparse ({len(candidates)} actionable) - adding "
                      f"{len(ocr_targets)} OCR targets from "
                      f"{len(perception_data.get('ocr_results') or [])} regions")
                candidates = candidates + ocr_targets

        for i, element in enumerate(candidates):
            if time.time() - start_time > budget_seconds:
                print(f"[PROBE] Budget exhausted after {len(discovered)} discoveries")
                break
            label = element["label"]
            try:
                result = self._probe_one(element, window, app_name)
            except Exception as exc:
                print(f"  [{i + 1}] ! {label[:34]:34} ({type(exc).__name__})")
                continue
            if result and result["effect_type"] != "no_visible_change":
                discovered.append(result)
                print(f"  [{i + 1}] + {label[:34]:34} -> {result['effect_type']} "
                      f"({result['method']}, {result['change_magnitude']:.3f})")
            else:
                print(f"  [{i + 1}] - {label[:34]:34} no visible change")

        # With --text-tab our own document is tried first: typing into one of the
        # user's tabs marks it modified even after every character is deleted, so a
        # disposable document we created and closed is the more considerate choice.
        text_capability = None
        if scratch_text:
            text_capability = self._probe_text_on_scratch_document(window)
        if not text_capability:
            text_capability = self._probe_text_input(window, targets)
        if text_capability:
            discovered.append(text_capability)
            print(f"  [+] text input                          -> accepts_text_input")

        self._revert(window)
        await asyncio.sleep(0)
        elapsed = time.time() - start_time
        return {
            "app_name": app_name,
            "interactions": [d for d in discovered if d.get("effect_type") != "no_visible_change"],
            "total_discovered": len([d for d in discovered if d.get("effect_type") != "no_visible_change"]),
            "time_taken": elapsed,
        }

    def _probe_one(self, element, window, app_name):
        self._focus(window)
        before = self._snapshot(window)
        method = self._actuate(element, window)
        if not method:
            return None
        after = self._settle(window)
        mean, frac = self._diff(before, after)

        dialog_hwnd, dialog = self._new_window(element["label"])

        effect = self._classify(mean, frac, element, dialog)
        result = {
            "element_label": element["label"],
            "element_x": element["x"], "element_y": element["y"],
            "effect_type": effect,
            "change_magnitude": round(frac, 4),
            "method": method,
            "source": element.get("source", "uia"),
            "control_type": element["control_type"],
            "detail": dialog or "",
            "dialog": dialog or "",
        }
        if dialog or frac > 0.02 or element["action"] == "expand":
            self._revert(window, escape=1, dialog_hwnd=dialog_hwnd)
            if dialog:
                self._baseline_windows = self._sibling_windows()
            if element["action"] == "expand":
                # Escape does not always dismiss a flyout (UWP menus often ignore it).
                # Re-invoking the same control collapses it, so the next probe sees
                # the app as it was, not the menu we opened.
                try:
                    ctrl = element.get("_ctrl")
                    pattern = ctrl.GetPattern(auto.PatternId.ExpandCollapsePattern)
                    if pattern is not None and pattern.ExpandCollapseState == 1:  # Expanded
                        pattern.Collapse()
                        time.sleep(0.15)
                except Exception:
                    pass
        return result

    async def _probe_keyboard(self, window, start_time, budget_seconds):
        found = []
        if hi is None:
            return found
        for keys, intent in SAFE_SHORTCUTS:
            if time.time() - start_time > budget_seconds:
                break
            self._focus(window)
            before = self._snapshot(window)
            delivered, _note = hi.post_key_combo(self._input_hwnd(window), keys)
            if not delivered:
                continue
            after = self._settle(window, max_wait=0.9)
            mean, frac = self._diff(before, after)
            dialog_hwnd, dialog = self._new_window()
            if dialog or frac > 0.02:
                found.append({
                    "element_label": f"{keys.upper()} ({intent})",
                    "element_x": 0, "element_y": 0,
                    "effect_type": "opens_dialog" if dialog else "keyboard_action",
                    "change_magnitude": round(frac, 4),
                    "method": "shortcut",
                    "source": "keyboard",
                    "control_type": "Accelerator",
                    "detail": dialog or f"{keys} produced a visible change",
                    "dialog": dialog or "",
                })
                print(f"  [K] + {keys.upper():18} -> {found[-1]['effect_type']} {dialog[:30]}")
                self._revert(window, escape=1, dialog_hwnd=dialog_hwnd)
                if dialog:
                    self._baseline_windows = self._sibling_windows()
        return found
