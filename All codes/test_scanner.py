"""Organ 30 — App Scanner (Test Build)
Test version for OBS scanning validation.
"""

from __future__ import annotations

import base64
import ctypes
import hashlib
import io
import json
import logging
import os
import re
import socket
import subprocess
import threading
import time
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

import uiautomation as auto
import win32gui
import win32process

logger = logging.getLogger("hojaiga.organ30.app_scanner")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

GATEKEEPER_PORT = 11435
GATEKEEPER_SECRET = "339680"
OLLAMA_PORT = 11434


def _ensure_services() -> Tuple[bool, bool]:
    brain_ok, eye_ok = False, False
    try:
        with socket.create_connection(("127.0.0.1", OLLAMA_PORT), timeout=2):
            pass
    except (ConnectionRefusedError, OSError):
        try:
            subprocess.Popen(["ollama", "serve"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=0x08000000)
            time.sleep(3)
        except Exception:
            pass

    try:
        with socket.create_connection(("127.0.0.1", GATEKEEPER_PORT), timeout=2):
            pass
    except (ConnectionRefusedError, OSError):
        try:
            subprocess.Popen(["python", r"D:\new_automation\Brain_Gatekeeper.py"])
            time.sleep(4)
        except Exception:
            pass

    try:
        payload = json.dumps({"model": "llama3", "messages": [{"role": "user", "content": "ping"}], "stream": False}).encode()
        req = urllib.request.Request(
            f"http://127.0.0.1:{GATEKEEPER_PORT}/api/chat",
            data=payload,
            headers={"Content-Type": "application/json", "X-Hojaiga-Validation": GATEKEEPER_SECRET},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            if json.loads(resp.read()).get("message"):
                brain_ok = True
    except Exception:
        pass

    try:
        payload = json.dumps({"model": "moondream", "messages": [{"role": "user", "content": "ping"}], "stream": False}).encode()
        req = urllib.request.Request(
            f"http://127.0.0.1:{GATEKEEPER_PORT}/api/chat",
            data=payload,
            headers={"Content-Type": "application/json", "X-Hojaiga-Validation": GATEKEEPER_SECRET},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            if json.loads(resp.read()).get("message"):
                eye_ok = True
    except Exception:
        pass

    logger.info("[SERVICES] Brain=%s, Eye=%s", brain_ok, eye_ok)
    return brain_ok, eye_ok


@dataclass
class UIElement:
    id: str
    class_name: str
    text: str
    bounds: Dict[str, int]
    children: List["UIElement"] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "class_name": self.class_name,
            "text": self.text,
            "bounds": self.bounds,
            "children": [c.to_dict() for c in self.children],
        }


class AppScannerOrgan:
    _LLM_LOCK = threading.Lock()
    _user32 = ctypes.windll.user32

    _SQL_CONN = (
        "DRIVER={ODBC Driver 17 for SQL Server};"
        "SERVER=DHRUV_PATEL\\SQLEXPRESS;"
        "DATABASE=hojaiga_knowledge;"
        "UID=Hojaiga.com;"
        "PWD=DhPa@3396$;"
    )

    ACTIONABLE_TYPES = {
        "ButtonControl", "MenuItemControl", "CheckBoxControl", "ComboBoxControl",
        "RadioButtonControl", "TabItemControl", "ListItemControl", "HyperlinkControl",
        "Button", "MenuItem", "CheckBox", "ComboBox",
        "RadioButton", "TabItem", "ListItem", "Hyperlink",
    }

    UNSAFE_KEYWORDS = {"quit", "exit", "uninstall", "delete account", "format"}
    DISMISS_LABELS = {"ok", "cancel", "close", "yes", "no", "done", "apply", "accept", "dismiss"}

    def __init__(self, force: bool = False) -> None:
        self.force = force
        self._brain_ok, self._eye_ok = _ensure_services()
        self._scanned_sigs: Set[str] = set()
        self._init_db()

    def _init_db(self) -> None:
        try:
            from core_organs.database_manager import DatabaseManager
            self.db = DatabaseManager()
            self._use_manager = True
            logger.info("[DB] DatabaseManager hooked.")
        except Exception:
            import pyodbc
            self._conn = pyodbc.connect(self._SQL_CONN, timeout=10, autocommit=True)
            self._db_lock = threading.Lock()
            self._use_manager = False
            logger.info("[DB] Direct pyodbc connection.")

    @staticmethod
    def _control_sig(control_type: str, text: str, auto_id: str = "", win_title: str = "") -> str:
        key = [str(control_type), (text or "").strip().lower(), str(auto_id or ""), str(win_title).lower()]
        return hashlib.md5(json.dumps(key, sort_keys=True).encode()).hexdigest()

    def _is_scanned_in_db(self, app_id: str, sig: str) -> bool:
        def _query(conn):
            c = conn.cursor()
            c.execute("SELECT id FROM ui_scanned WHERE app_id=? AND sig=?", (app_id, sig))
            return c.fetchone() is not None
        result = self.db._safe_call(_query)
        return result if result is not None else False

    def _mark_scanned_in_db(self, app_id: str, sig: str, info: dict) -> None:
        now = time.time()
        def _insert(conn):
            c = conn.cursor()
            c.execute(
                "INSERT INTO ui_scanned (app_id, version, sig, info, last_scanned) VALUES (?,?,?,?,?)",
                (app_id, "live", sig, json.dumps(info), now),
            )
        self.db._safe_call(_insert)

    def _store_page_in_db(self, app_id: str, tree_hash: str, ui_tree: str) -> None:
        from datetime import datetime
        now = datetime.now()
        def _upsert(conn):
            c = conn.cursor()
            c.execute("SELECT id FROM ui_knowledge WHERE app_id=? AND page_key='root'", (app_id,))
            row = c.fetchone()
            if row:
                c.execute("UPDATE ui_knowledge SET tree_hash=?, ui_tree=?, last_scanned=? WHERE id=?",
                          (tree_hash, ui_tree, now, row[0]))
            else:
                c.execute("INSERT INTO ui_knowledge (app_id, version, page_key, tree_hash, ui_tree, interactive_elements, last_scanned) VALUES (?,?,?,?,?,?,?)",
                          (app_id, "live", "root", tree_hash, ui_tree, "[]", now))
        self.db._safe_call(_upsert)

    @staticmethod
    def _pid_of(hwnd: int) -> Optional[int]:
        if not hwnd:
            return None
        try:
            return win32process.GetWindowThreadProcessId(int(hwnd))[1]
        except Exception:
            return None

    def _sort_elements_spatial(self, elements: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        def _get_sort_key(el):
            rect = el.get("rect")
            if rect and rect.width() > 0:
                return (rect.top, rect.left)
            return (999999, 999999)
        return sorted(elements, key=_get_sort_key)

    def _extract_window_elements(self, ctrl_node) -> List[Dict[str, Any]]:
        elements = []
        def _walk(ctrl, depth=0):
            if depth > 12:
                return
            try:
                name = ctrl.Name or ""
                ctype = ctrl.ControlTypeName or ""
                aid = ctrl.AutomationId or ""
                rect = ctrl.BoundingRectangle

                if (name or ctype or aid) and ctype in self.ACTIONABLE_TYPES:
                    elements.append({
                        "control_obj": ctrl,
                        "name": name,
                        "control_type": ctype,
                        "automation_id": aid,
                        "rect": rect,
                    })

                for child in ctrl.GetChildren():
                    _walk(child, depth + 1)
            except Exception:
                pass

        _walk(ctrl_node)
        return elements

    def _virtual_click(self, ctrl_obj) -> bool:
        if hasattr(ctrl_obj, "GetInvokePattern"):
            pat = ctrl_obj.GetInvokePattern()
            if pat:
                try:
                    pat.Invoke()
                    return True
                except Exception:
                    pass

        if hasattr(ctrl_obj, "GetSelectionItemPattern"):
            pat = ctrl_obj.GetSelectionItemPattern()
            if pat:
                try:
                    pat.Select()
                    return True
                except Exception:
                    pass

        if hasattr(ctrl_obj, "GetTogglePattern"):
            pat = ctrl_obj.GetTogglePattern()
            if pat:
                try:
                    pat.Toggle()
                    return True
                except Exception:
                    pass

        hwnd = getattr(ctrl_obj, "NativeWindowHandle", 0) or 0
        if hwnd and self._user32:
            try:
                self._user32.SendMessageW(hwnd, 0x00F5, 0, 0)
                return True
            except Exception:
                pass

        rect = ctrl_obj.BoundingRectangle if hasattr(ctrl_obj, "BoundingRectangle") else None
        if rect and rect.width() > 0:
            cx = (rect.left + rect.right) // 2
            cy = (rect.top + rect.bottom) // 2
            parent_hwnd = hwnd
            curr = ctrl_obj
            while not parent_hwnd and curr:
                curr = curr.GetParentControl() if hasattr(curr, "GetParentControl") else None
                if curr and hasattr(curr, "NativeWindowHandle") and curr.NativeWindowHandle:
                    parent_hwnd = curr.NativeWindowHandle
                    break

            if parent_hwnd and self._user32:
                class POINT(ctypes.Structure):
                    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]
                pt = POINT(cx, cy)
                self._user32.ScreenToClient(parent_hwnd, ctypes.byref(pt))
                lparam = (pt.y << 16) | (pt.x & 0xFFFF)
                self._user32.PostMessageW(parent_hwnd, 0x0200, 0, lparam)
                self._user32.PostMessageW(parent_hwnd, 0x0201, 0x0001, lparam)
                self._user32.PostMessageW(parent_hwnd, 0x0202, 0, lparam)
                return True

        return False

    def _find_spawned_windows(self, target_pid: int, main_hwnd: int) -> List[Tuple[Any, str, int]]:
        result = []
        for c in auto.GetRootControl().GetChildren():
            try:
                h = c.NativeWindowHandle
                if h and h != main_hwnd and c.ProcessId == target_pid and c.IsWindowVisible():
                    name = c.Name or ""
                    if "profile:" in name.lower() and "scenes:" in name.lower():
                        continue
                    result.append((c, name, h))
            except Exception:
                continue
        return result

    def _classify_window(self, win_ctrl, title: str) -> str:
        tl = title.lower()
        if any(w in tl for w in ("error", "crash", "failed", "fatal", "exception", "critical")):
            return "ERROR_WINDOW"

        ctrls = self._extract_window_elements(win_ctrl)
        btns = {c["name"].strip().lower() for c in ctrls if "button" in c["control_type"].lower()}
        has_dismiss = bool(btns & self.DISMISS_LABELS)

        if has_dismiss and len(ctrls) <= 10:
            return "INFORMATIONAL_WINDOW"
        return "CHILD_WINDOW"

    def _resolve_popup_eye_brain(self, win_ctrl, title: str, app_id: str) -> bool:
        from PIL import ImageGrab
        logger.info("[POPUP] Resolving: '%s'", title)
        handle = getattr(win_ctrl, "NativeWindowHandle", 0)
        clicked = False

        tl = title.lower()
        if "add scene" in tl:
            try:
                for el in self._extract_window_elements(win_ctrl):
                    if "edit" in el["control_type"].lower():
                        if hasattr(el["control_obj"], "SetValue"):
                            el["control_obj"].SetValue("Scene 2")
            except Exception:
                pass
            for cand in ("ok", "cancel"):
                for b in self._extract_window_elements(win_ctrl):
                    if b["name"].strip().lower() == cand:
                        self._virtual_click(b["control_obj"])
                        clicked = True
                        break
                if clicked:
                    break

        elif any(k in tl for k in ("delete", "confirm", "remove", "closing dockable")):
            for cand in ("ok", "no", "cancel"):
                for b in self._extract_window_elements(win_ctrl):
                    if b["name"].strip().lower() == cand:
                        self._virtual_click(b["control_obj"])
                        clicked = True
                        break
                if clicked:
                    break

        if not clicked:
            rect = win_ctrl.BoundingRectangle
            img_b64 = ""
            try:
                if rect and rect.width() > 20 and rect.height() > 20:
                    shot = ImageGrab.grab((rect.left, rect.top, rect.right, rect.bottom))
                    shot.thumbnail((512, 512))
                    buf = io.BytesIO()
                    shot.save(buf, format="PNG")
                    img_b64 = base64.b64encode(buf.getvalue()).decode()
            except Exception:
                pass

            target_btn = "Cancel"
            if img_b64:
                try:
                    payload = json.dumps({
                        "model": "moondream",
                        "messages": [{"role": "user", "content": "What text is shown and which button dismisses this dialog?", "images": [img_b64]}],
                        "stream": False,
                    }).encode()
                    req = urllib.request.Request(
                        f"http://127.0.0.1:{GATEKEEPER_PORT}/api/chat",
                        data=payload,
                        headers={"Content-Type": "application/json", "X-Hojaiga-Validation": GATEKEEPER_SECRET},
                        method="POST",
                    )
                    with urllib.request.urlopen(req, timeout=30) as resp:
                        eye_text = json.loads(resp.read()).get("message", {}).get("content", "")

                    b_payload = json.dumps({
                        "model": "llama3",
                        "messages": [{"role": "user", "content": f"Popup text: {eye_text}. What button closes it safely (OK, Cancel, Close, No)? Respond ONLY with the button text."}],
                        "stream": False,
                    }).encode()
                    b_req = urllib.request.Request(
                        f"http://127.0.0.1:{GATEKEEPER_PORT}/api/chat",
                        data=b_payload,
                        headers={"Content-Type": "application/json", "X-Hojaiga-Validation": GATEKEEPER_SECRET},
                        method="POST",
                    )
                    with urllib.request.urlopen(b_req, timeout=25) as b_resp:
                        target_btn = json.loads(b_resp.read()).get("message", {}).get("content", "Cancel").strip()
                except Exception as e:
                    logger.debug("Eye/Brain error: %s", e)

            for b in self._extract_window_elements(win_ctrl):
                if b["name"].strip().lower() == target_btn.lower():
                    self._virtual_click(b["control_obj"])
                    clicked = True
                    break

        if not clicked:
            auto.SendKey(auto.Keys.VK_ESCAPE)

        time.sleep(0.4)
        closed = not win32gui.IsWindow(handle)

        sig = self._control_sig("Popup", title)
        self._mark_scanned_in_db(app_id, sig, {"title": title, "resolved": closed})
        self._scanned_sigs.add(sig)
        return closed

    def _scan_child_window_deep(self, win_ctrl, app_id: str, parent_node: UIElement, depth: int = 0) -> None:
        if depth >= 3:
            return

        title = win_ctrl.Name or f"Child_{win_ctrl.NativeWindowHandle}"
        logger.info("[CHILD] Deep scanning: '%s' (depth=%d)", title, depth)

        node = UIElement(id=str(win_ctrl.NativeWindowHandle), class_name="Window", text=title, bounds={})
        ctrls = self._extract_window_elements(win_ctrl)

        actionable = [c for c in ctrls if c["name"].strip().lower() not in self.DISMISS_LABELS]
        dismiss_btns = [c for c in ctrls if c["name"].strip().lower() in self.DISMISS_LABELS]

        for el in self._sort_elements_spatial(actionable):
            name = el["name"]
            ctype = el["control_type"]
            sig = self._control_sig(ctype, name, el["automation_id"], title)

            if sig in self._scanned_sigs and not self.force:
                continue

            self._virtual_click(el["control_obj"])
            time.sleep(0.3)

            for cw, ct, ch in self._find_spawned_windows(win_ctrl.ProcessId, win_ctrl.NativeWindowHandle):
                w_type = self._classify_window(cw, ct)
                if w_type == "CHILD_WINDOW":
                    self._scan_child_window_deep(cw, app_id, node, depth + 1)
                else:
                    self._resolve_popup_eye_brain(cw, ct, app_id)

            self._mark_scanned_in_db(app_id, sig, {"text": name, "type": ctype})
            self._scanned_sigs.add(sig)

        closed = False
        for b in dismiss_btns:
            if b["name"].strip().lower() in ("cancel", "close", "done", "ok"):
                self._virtual_click(b["control_obj"])
                time.sleep(0.3)
                closed = True
                break
        if not closed:
            auto.SendKey(auto.Keys.VK_ESCAPE)

        parent_node.children.append(node)

    def scan_app_active(self, app_id: str, target_hwnd: int) -> dict:
        target_pid = self._pid_of(target_hwnd)
        main_win = auto.ControlFromHandle(target_hwnd)
        if not main_win:
            return {"status": "error", "reason": "Invalid target HWND"}

        self._scanned_sigs.clear()
        main_title = main_win.Name or "MainWindow"
        root_element = UIElement(id=str(target_hwnd), class_name="MainWindow", text=main_title, bounds={})

        # PASS 1: Menu Bar
        logger.info("[PASS 1] Scanning Menu Bar and Dropdowns...")
        raw_elements = self._extract_window_elements(main_win)
        menu_headers = [e for e in raw_elements if "menuitem" in e["control_type"].lower()]
        menu_headers = self._sort_elements_spatial(menu_headers)

        for mh in menu_headers:
            m_name = mh["name"].strip()
            if not m_name or m_name.lower() in ("system", ""):
                continue

            logger.info("[MENU] Expanding: '%s'", m_name)

            before_items = set()
            for el in self._extract_window_elements(main_win):
                if "menuitem" in el["control_type"].lower():
                    before_items.add(el["name"].strip())

            self._virtual_click(mh["control_obj"])
            time.sleep(0.5)

            dropdown_items = []
            for el in self._extract_window_elements(main_win):
                if "menuitem" in el["control_type"].lower():
                    n = el["name"].strip()
                    if n and n != m_name and n not in before_items:
                        dropdown_items.append(el)

            if not dropdown_items:
                logger.info("[MENU] No items found via tree walk, trying keyboard shortcut for '%s'", m_name)
                shortcut = self._menu_shortcuts.get(m_name.lower())
                if shortcut:
                    win32gui.SetForegroundWindow(target_hwnd)
                    time.sleep(0.2)
                    auto.SendKeys(shortcut)
                    time.sleep(0.6)
                    after_items = set()
                    for el in self._extract_window_elements(main_win):
                        if "menuitem" in el["control_type"].lower():
                            n = el["name"].strip()
                            if n and n != m_name and n not in before_items:
                                dropdown_items.append(el)
                                after_items.add(n)
                    if not dropdown_items:
                        auto.SendKey(auto.Keys.VK_ESCAPE)
                        time.sleep(0.2)

            logger.info("[MENU] Found %d items under '%s'", len(dropdown_items), m_name)
            sorted_dropdown = self._sort_elements_spatial(dropdown_items)

            for sub_el in sorted_dropdown:
                s_name = sub_el["name"].strip()
                sub_sig = self._control_sig("MenuItem", s_name, sub_el["automation_id"], m_name)

                if sub_sig in self._scanned_sigs and not self.force:
                    continue

                self._virtual_click(mh["control_obj"])
                time.sleep(0.2)

                logger.info("[MENU ENGINE] Clicking: '%s' -> '%s'", m_name, s_name)
                self._virtual_click(sub_el["control_obj"])
                time.sleep(0.4)

                for cw, ct, ch in self._find_spawned_windows(target_pid, target_hwnd):
                    w_type = self._classify_window(cw, ct)
                    if w_type == "CHILD_WINDOW":
                        self._scan_child_window_deep(cw, app_id, root_element, depth=1)
                    else:
                        self._resolve_popup_eye_brain(cw, ct, app_id)

                self._mark_scanned_in_db(app_id, sub_sig, {"name": s_name, "parent_menu": m_name})
                self._scanned_sigs.add(sub_sig)

            auto.SendKey(auto.Keys.VK_ESCAPE)
            time.sleep(0.2)

        # PASS 2: Surface Controls
        logger.info("[PASS 2] Scanning Surface Controls...")
        surface_ctrls = [
            e for e in self._extract_window_elements(main_win)
            if "menuitem" not in e["control_type"].lower()
        ]
        surface_sorted = self._sort_elements_spatial(surface_ctrls)

        for el in surface_sorted:
            name = el["name"].strip()
            ctype = el["control_type"]
            sig = self._control_sig(ctype, name, el["automation_id"], main_title)

            if sig in self._scanned_sigs and not self.force:
                continue
            if name and any(k in name.lower() for k in self.UNSAFE_KEYWORDS):
                continue

            logger.info("[SURFACE] Clicking %s: '%s'", ctype, name)
            self._virtual_click(el["control_obj"])
            time.sleep(0.4)

            for cw, ct, ch in self._find_spawned_windows(target_pid, target_hwnd):
                w_type = self._classify_window(cw, ct)
                if w_type == "CHILD_WINDOW":
                    self._scan_child_window_deep(cw, app_id, root_element, depth=0)
                else:
                    self._resolve_popup_eye_brain(cw, ct, app_id)

            self._mark_scanned_in_db(app_id, sig, {"text": name, "type": ctype})
            self._scanned_sigs.add(sig)

        tree_hash = hashlib.sha256(json.dumps(root_element.to_dict(), sort_keys=True).encode()).hexdigest()
        self._store_page_in_db(app_id, tree_hash, json.dumps(root_element.to_dict(), sort_keys=True))
        logger.info("[COMPLETED] Unique elements: %d", len(self._scanned_sigs))

        return {"status": "completed", "tree_hash": tree_hash, "controls_scanned": len(self._scanned_sigs)}


if __name__ == "__main__":
    import win32gui

    hwnds = []
    def _enum(h, _):
        if win32gui.IsWindowVisible(h) and "Profile:" in win32gui.GetWindowText(h):
            hwnds.append(h)
        return True
    win32gui.EnumWindows(_enum, None)

    if hwnds:
        scanner = AppScannerOrgan(force=True)
        res = scanner.scan_app_active("OBS Studio", hwnds[0])
        print(json.dumps(res, indent=2))
    else:
        print("OBS not found. Launch OBS first.")
