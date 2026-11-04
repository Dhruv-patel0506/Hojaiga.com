"""
organ_34_teaching_void.py
Hojaiga Autonomous OS — Infinite Teaching Void Space & Whiteboard Overlay.

Provides a limitless, fully transparent dotted-grid canvas across the entire screen
and infinite virtual 2D coordinate space for teaching, explaining, diagramming, and
demonstrating concepts. Retains every stroke, note, and diagram in world coordinates,
supporting smooth pan/scroll in all directions, bookmarking, and instant trace-back.
"""

import logging
import math
import queue
import threading
import time
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("hojaiga.organ34.teaching_void")

try:
    import tkinter as tk
    from tkinter import font as tkfont
    _HAS_TK = True
except ImportError:
    _HAS_TK = False

try:
    import ctypes
    from ctypes import wintypes
    import win32gui
    import win32con
    _HAS_WIN32 = True
except ImportError:
    _HAS_WIN32 = False


# Theme Color Presets for Teaching Void
THEMES = {
    "cyber_dots": {
        "dot": "#2d4259",       # Subtle soft cyan-slate dots
        "accent": "#00f0ff",    # Neon electric cyan
        "secondary": "#ff007f", # Hot pink / magenta
        "card_bg": "#0d1624",   # Semi-translucent dark card bg
        "text": "#e0f2fe",      # Clean soft white
        "header": "#38bdf8",    # Sky blue header
        "arrow": "#38bdf8",     # Cyan arrow
        "highlight": "#fbbf24", # Vibrant amber
        "success": "#34d399",   # Neon emerald green
    },
    "chalk_dots": {
        "dot": "#3a3a3a",
        "accent": "#fef08a",    # Chalk yellow
        "secondary": "#f472b6", # Chalk pink
        "card_bg": "#18181b",
        "text": "#f4f4f5",
        "header": "#67e8f9",
        "arrow": "#fde047",
        "highlight": "#fb923c",
        "success": "#4ade80",
    },
    "matrix_dots": {
        "dot": "#14381e",
        "accent": "#22c55e",    # Terminal green
        "secondary": "#a855f7", # Violet
        "card_bg": "#05150a",
        "text": "#dcfce7",
        "header": "#4ade80",
        "arrow": "#86efac",
        "highlight": "#facc15",
        "success": "#22c55e",
    }
}


class TeachingVoid:
    """
    Singleton Infinite Teaching Void Space Overlay.
    Runs a transparent fullscreen click-through window in a dedicated background daemon thread.
    """

    _instance = None
    _lock = threading.Lock()

    def __new__(cls, *args, **kwargs):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._init()
            return cls._instance

    def _init(self):
        self._cmd_queue: queue.Queue = queue.Queue()
        self._thread: Optional[threading.Thread] = None
        self._root: Optional[tk.Tk] = None
        self._canvas: Optional[tk.Canvas] = None
        self._hwnd: int = 0
        self._is_open = False
        self._theme_name = "cyber_dots"
        self._theme = THEMES["cyber_dots"]

        # Infinite World Space & Camera
        self._cam_x = 0.0
        self._cam_y = 0.0
        self._target_cam_x = 0.0
        self._target_cam_y = 0.0
        self._cam_animating = False
        self._zoom = 1.0
        self._grid_spacing = 32

        # Screen dimensions
        self._screen_w = 1920
        self._screen_h = 1080

        # Knowledge / Diagram Storage in World Coordinates
        self._elements: List[Dict[str, Any]] = []
        self._bookmarks: Dict[str, Tuple[float, float]] = {}  # name -> (wx, wy)
        self._elem_id_counter = 0

        # Click-through state
        self._click_through = True

        # Spawning dot illumination wave animation
        self._is_spawning = False
        self._spawn_anim_radius = 0.0


    # ── External Thread-Safe Public API ──────────────────────────────

    def open(self, theme: str = "cyber_dots") -> str:
        """Open or show the infinite transparent dotted teaching void space."""
        if theme in THEMES:
            self._theme_name = theme
            self._theme = THEMES[theme]

        if not self._is_open or not self._thread or not self._thread.is_alive():
            self._start_thread()

        self._send_cmd("show")
        return f"Teaching Void Space activated (theme='{self._theme_name}'). Infinite canvas ready."

    def close(self) -> str:
        """Hide the teaching void overlay."""
        if self._is_open:
            self._send_cmd("hide")
            return "Teaching Void Space closed."
        return "Teaching Void Space was not active."

    def draw_shape(self, shape: str, x: float, y: float, width: float = 160.0,
                   height: float = 120.0, color: str = "", fill: bool = True,
                   label: str = "", bookmark: str = "") -> str:
        """
        Draw a parametric shape or diagram container in world coordinates.
        Supported shapes: 'rect', 'card', 'box', 'circle', 'oval', 'diamond', 'star', 'heart', 'cylinder', 'cloud'.
        """
        self.open(self._theme_name)
        self._elem_id_counter += 1
        elem_id = f"shape_{self._elem_id_counter}"
        c = color or self._theme["accent"]

        elem = {
            "id": elem_id,
            "type": "shape",
            "shape": shape.lower().strip(),
            "wx": float(x),
            "wy": float(y),
            "w": float(width),
            "h": float(height),
            "color": c,
            "fill": fill,
            "label": label,
            "bookmark": bookmark,
            "created_at": time.time(),
        }
        self._elements.append(elem)
        if bookmark:
            self._bookmarks[bookmark.lower().strip()] = (float(x), float(y))

        self._send_cmd("add_element", elem)
        return f"Drew '{shape}' at world coords ({x:.0f}, {y:.0f}) size={width:.0f}x{height:.0f} label='{label}' (bookmark='{bookmark}')"

    def write_text(self, text: str, x: float, y: float, font_size: int = 14,
                   color: str = "", header: str = "", bookmark: str = "") -> str:
        """
        Write explanatory notes, equations, bullet points, or code cards in world coordinates.
        """
        self.open(self._theme_name)
        self._elem_id_counter += 1
        elem_id = f"text_{self._elem_id_counter}"
        c = color or self._theme["text"]

        elem = {
            "id": elem_id,
            "type": "text",
            "text": text,
            "header": header,
            "wx": float(x),
            "wy": float(y),
            "font_size": font_size,
            "color": c,
            "bookmark": bookmark,
            "created_at": time.time(),
        }
        self._elements.append(elem)
        if bookmark:
            self._bookmarks[bookmark.lower().strip()] = (float(x), float(y))

        self._send_cmd("add_element", elem)
        return f"Wrote explanation note at world coords ({x:.0f}, {y:.0f}) header='{header}' (bookmark='{bookmark}')"

    def draw_arrow(self, from_x: float, from_y: float, to_x: float, to_y: float,
                   label: str = "", color: str = "", style: str = "straight") -> str:
        """
        Draw a directed concept arrow connecting two points in the void.
        """
        self.open(self._theme_name)
        self._elem_id_counter += 1
        elem_id = f"arrow_{self._elem_id_counter}"
        c = color or self._theme["arrow"]

        elem = {
            "id": elem_id,
            "type": "arrow",
            "from_x": float(from_x),
            "from_y": float(from_y),
            "to_x": float(to_x),
            "to_y": float(to_y),
            "label": label,
            "color": c,
            "style": style,
            "created_at": time.time(),
        }
        self._elements.append(elem)
        self._send_cmd("add_element", elem)
        return f"Drew arrow from ({from_x:.0f}, {from_y:.0f}) to ({to_x:.0f}, {to_y:.0f}) label='{label}'"

    def draw_stroke(self, points: List[Tuple[float, float]], color: str = "",
                    width: int = 3) -> str:
        """
        Draw freehand polyline strokes across the void or over screen elements.
        points: list of (x, y) world coordinates.
        """
        if not points or len(points) < 2:
            return "Need at least 2 points for a stroke."
        self.open(self._theme_name)
        self._elem_id_counter += 1
        elem_id = f"stroke_{self._elem_id_counter}"
        c = color or self._theme["accent"]

        elem = {
            "id": elem_id,
            "type": "stroke",
            "points": points,
            "color": c,
            "width": width,
            "created_at": time.time(),
        }
        self._elements.append(elem)
        self._send_cmd("add_element", elem)
        return f"Drew freehand stroke with {len(points)} points."

    def navigate(self, target: str, distance: float = 400.0) -> str:
        """
        Pan camera or trace back to a previously saved concept.
        target: 'up', 'down', 'left', 'right', 'home', or bookmark name (e.g. 'intro', 'step1').
        """
        self.open(self._theme_name)
        t = target.lower().strip()

        if t == "home":
            self._target_cam_x = 0.0
            self._target_cam_y = 0.0
            self._send_cmd("animate_camera", (0.0, 0.0))
            return "Navigated camera back to Void Home (0, 0)."

        if t in ("up", "down", "left", "right"):
            dx, dy = 0.0, 0.0
            if t == "up":
                dy = -distance
            elif t == "down":
                dy = distance
            elif t == "left":
                dx = -distance
            elif t == "right":
                dx = distance
            new_x = self._cam_x + dx
            new_y = self._cam_y + dy
            self._target_cam_x = new_x
            self._target_cam_y = new_y
            self._send_cmd("animate_camera", (new_x, new_y))
            return f"Scrolled Teaching Void {t} by {distance:.0f}px. Camera now at ({new_x:.0f}, {new_y:.0f})."

        if t in ("zoom_in", "zoomin", "zoom in", "in"):
            self._zoom = min(3.0, self._zoom * 1.25)
            self._grid_spacing = max(16, int(32 * self._zoom))
            self._send_cmd("redraw")
            return f"Zoomed in (zoom={self._zoom:.2f}x, spacing={self._grid_spacing}px)."

        if t in ("zoom_out", "zoomout", "zoom out", "out"):
            self._zoom = max(0.4, self._zoom * 0.8)
            self._grid_spacing = max(16, int(32 * self._zoom))
            self._send_cmd("redraw")
            return f"Zoomed out (zoom={self._zoom:.2f}x, spacing={self._grid_spacing}px)."


        # Check bookmarks for trace-back
        if t in self._bookmarks:
            wx, wy = self._bookmarks[t]
            # Center the camera on the bookmarked concept
            target_cx = wx - (self._screen_w / 2.0)
            target_cy = wy - (self._screen_h / 2.0)
            self._target_cam_x = target_cx
            self._target_cam_y = target_cy
            self._send_cmd("animate_camera", (target_cx, target_cy))
            return f"Traced back to bookmark '{target}' at world ({wx:.0f}, {wy:.0f})."

        return f"Unknown navigation target '{target}'. Available bookmarks: {list(self._bookmarks.keys())} or use up/down/left/right/home."

    def clear(self, mode: str = "all") -> str:
        """
        Clear drawings from the teaching void.
        mode: 'all' (wipes entire infinite space), 'viewport' (clears only visible area), 'home' (resets camera).
        """
        m = mode.lower().strip()
        if m == "all":
            self._elements.clear()
            self._bookmarks.clear()
            self._send_cmd("clear_all")
            return "Cleared all drawings from the infinite void space."
        elif m == "viewport":
            vw_left = self._cam_x
            vw_top = self._cam_y
            vw_right = self._cam_x + self._screen_w
            vw_bottom = self._cam_y + self._screen_h
            self._elements = [e for e in self._elements if not (vw_left <= e.get("wx", 0) <= vw_right and vw_top <= e.get("wy", 0) <= vw_bottom)]
            self._send_cmd("redraw")
            return "Cleared visible viewport drawings."
        elif m == "home":
            self.navigate("home")
            return "Reset camera to home."
        return f"Unknown clear mode '{mode}'."

    def get_status(self) -> Dict[str, Any]:
        """Return current status and statistics of the Teaching Void."""
        return {
            "active": self._is_open,
            "theme": self._theme_name,
            "camera": {"x": self._cam_x, "y": self._cam_y},
            "total_elements": len(self._elements),
            "bookmarks": list(self._bookmarks.keys()),
        }

    def save_notes(self, folder: str = "teaching_notes", title: str = "Teaching Session") -> Dict[str, str]:
        """
        Save whatever was taught on screen into a folder as formatted notes, diagrams, and screenshot.
        Outputs:
        1. Markdown notes document (.md)
        2. Visual screenshot capture (.png)
        3. Raw structured elements data (.json)
        """
        import os
        import json
        from datetime import datetime

        if not os.path.isabs(folder):
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            target_dir = os.path.join(base_dir, folder)
        else:
            target_dir = folder

        os.makedirs(target_dir, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        slug_title = "".join(c if c.isalnum() else "_" for c in title).strip("_").lower()
        base_name = f"{slug_title}_{timestamp}"

        notes_file = os.path.join(target_dir, f"{base_name}.md")
        json_file = os.path.join(target_dir, f"{base_name}.json")
        img_file = os.path.join(target_dir, f"{base_name}.png")

        # 1. Capture screenshot of screen/void using Win32 CAPTUREBLT (captures layered transparent void)
        has_screenshot = False
        try:
            import ctypes
            from ctypes import wintypes
            from PIL import Image

            user32 = ctypes.windll.user32
            gdi32 = ctypes.windll.gdi32

            hdesk = user32.OpenInputDesktop(0, False, 0x01FF)
            if hdesk:
                user32.SetThreadDesktop(hdesk)

            w = user32.GetSystemMetrics(0)
            h = user32.GetSystemMetrics(1)
            hdc_screen = user32.GetDC(0)
            hdc_mem = gdi32.CreateCompatibleDC(hdc_screen)
            hbm = gdi32.CreateCompatibleBitmap(hdc_screen, w, h)
            gdi32.SelectObject(hdc_mem, hbm)

            # CAPTUREBLT (0x40000000) | SRCCOPY (0x00CC0020) = 0x40CC0020 captures layered transparent windows
            gdi32.BitBlt(hdc_mem, 0, 0, w, h, hdc_screen, 0, 0, 0x40CC0020)

            class BITMAPINFOHEADER(ctypes.Structure):
                _fields_ = [
                    ('biSize', wintypes.DWORD),
                    ('biWidth', wintypes.LONG),
                    ('biHeight', wintypes.LONG),
                    ('biPlanes', wintypes.WORD),
                    ('biBitCount', wintypes.WORD),
                    ('biCompression', wintypes.DWORD),
                    ('biSizeImage', wintypes.DWORD),
                    ('biXPelsPerMeter', wintypes.LONG),
                    ('biYPelsPerMeter', wintypes.LONG),
                    ('biClrUsed', wintypes.DWORD),
                    ('biClrImportant', wintypes.DWORD)
                ]

            bmi = BITMAPINFOHEADER()
            bmi.biSize = ctypes.sizeof(BITMAPINFOHEADER)
            bmi.biWidth = w
            bmi.biHeight = -h
            bmi.biPlanes = 1
            bmi.biBitCount = 32
            bmi.biCompression = 0

            buf = ctypes.create_string_buffer(w * h * 4)
            gdi32.GetDIBits(hdc_mem, hbm, 0, h, buf, ctypes.byref(bmi), 0)

            img = Image.frombuffer('RGBA', (w, h), buf, 'raw', 'BGRA', 0, 1)
            img.convert('RGB').save(img_file, "PNG")
            has_screenshot = True

            gdi32.DeleteObject(hbm)
            gdi32.DeleteDC(hdc_mem)
            user32.ReleaseDC(0, hdc_screen)
        except Exception as cap_err:
            logger.debug(f"[VOID] BitBlt screenshot capture note: {cap_err}")
            try:
                from PIL import ImageGrab
                screenshot = ImageGrab.grab()
                screenshot.save(img_file, "PNG")
                has_screenshot = True
            except Exception:
                has_screenshot = False

        # 2. Build Rich Markdown Notes
        md_lines = [
            f"# 📚 {title}",
            f"",
            f"- **Date & Time**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            f"- **Theme**: `{self._theme_name}`",
            f"- **Total Teaching Elements**: {len(self._elements)}",
            f"- **Camera World Position**: `({self._cam_x:.0f}, {self._cam_y:.0f})`",
            f"",
        ]

        if has_screenshot:
            rel_img = os.path.basename(img_file)
            md_lines.extend([
                f"## 🖼️ Session Canvas Snapshot",
                f"![Teaching Canvas Snapshot]({rel_img})",
                f"",
            ])

        # Bookmarks Summary
        if self._bookmarks:
            md_lines.extend([
                f"## 🔖 Bookmarks & Concept Traceback",
                f"| Bookmark | World Coordinates |",
                f"| :--- | :--- |",
            ])
            for b_name, (bx, by) in self._bookmarks.items():
                md_lines.append(f"| **{b_name}** | `({bx:.0f}, {by:.0f})` |")
            md_lines.append("")

        # Explanations & Notes
        texts = [e for e in self._elements if e.get("type") == "text"]
        if texts:
            md_lines.append("## 📝 Explanations & Written Notes")
            for t in texts:
                header = t.get("header")
                if header:
                    md_lines.append(f"### {header}")
                content = t.get("text", "")
                md_lines.append(content)
                if t.get("bookmark"):
                    md_lines.append(f"> *Bookmark: `{t.get('bookmark')}`*")
                md_lines.append("")

        # Diagrams & Structures
        shapes = [e for e in self._elements if e.get("type") == "shape"]
        if shapes:
            md_lines.append("## 📐 Diagrams & Concepts")
            md_lines.append("| Shape | Label | World Position | Dimensions | Bookmark |")
            md_lines.append("| :--- | :--- | :--- | :--- | :--- |")
            for s in shapes:
                s_shape = s.get("shape", "rect")
                s_label = s.get("label", "-") or "-"
                s_pos = f"({s.get('wx', 0):.0f}, {s.get('wy', 0):.0f})"
                s_dim = f"{s.get('w', 0):.0f} x {s.get('h', 0):.0f}"
                s_bm = s.get("bookmark", "-") or "-"
                md_lines.append(f"| **{s_shape.capitalize()}** | {s_label} | `{s_pos}` | `{s_dim}` | `{s_bm}` |")
            md_lines.append("")

        # Concept Flow / Arrows
        arrows = [e for e in self._elements if e.get("type") == "arrow"]
        if arrows:
            md_lines.append("## 🔄 Concept Flow & Relationships")
            for a in arrows:
                label_txt = f" --({a.get('label')})--> " if a.get("label") else " ----> "
                fx, fy = a.get("from_x", 0), a.get("from_y", 0)
                tx, ty = a.get("to_x", 0), a.get("to_y", 0)
                md_lines.append(f"- `({fx:.0f}, {fy:.0f})`{label_txt}`({tx:.0f}, {ty:.0f})`")
            md_lines.append("")

        with open(notes_file, "w", encoding="utf-8") as f:
            f.write("\n".join(md_lines))

        # 3. Export Raw JSON for full fidelity replay/trace
        export_data = {
            "title": title,
            "timestamp": datetime.now().isoformat(),
            "theme": self._theme_name,
            "camera": {"x": self._cam_x, "y": self._cam_y},
            "bookmarks": self._bookmarks,
            "elements": self._elements,
            "screenshot": img_file if has_screenshot else None,
        }
        with open(json_file, "w", encoding="utf-8") as f:
            json.dump(export_data, f, indent=2)

        return {
            "status": "success",
            "folder": target_dir,
            "notes_path": notes_file,
            "screenshot_path": img_file if has_screenshot else "",
            "json_path": json_file,
            "elements_count": str(len(self._elements)),
        }


    # ── Background Thread & Tkinter Rendering Loop ───────────────────

    def _send_cmd(self, action: str, data: Any = None):
        self._cmd_queue.put((action, data))

    def _start_thread(self):
        self._is_open = True
        ready_evt = threading.Event()
        self._thread = threading.Thread(target=self._run_tk_loop, args=(ready_evt,), daemon=True, name="TeachingVoidThread")
        self._thread.start()
        ready_evt.wait(timeout=3.0)

    def _run_tk_loop(self, ready_evt: threading.Event):
        if not _HAS_TK:
            ready_evt.set()
            return

        root = tk.Tk()
        self._root = root
        root.title("Hojaiga_Teaching_Void")
        root.attributes("-fullscreen", True)
        root.attributes("-topmost", True)

        # Transparent Key: #000001
        TRANSPARENT_COLOR = "#000001"
        root.attributes("-transparentcolor", TRANSPARENT_COLOR)
        root.config(bg=TRANSPARENT_COLOR)

        screen_w = root.winfo_screenwidth()
        screen_h = root.winfo_screenheight()
        self._screen_w = screen_w
        self._screen_h = screen_h

        canvas = tk.Canvas(root, width=screen_w, height=screen_h, bg=TRANSPARENT_COLOR,
                           highlightthickness=0, bd=0)
        canvas.pack(fill="both", expand=True)
        self._canvas = canvas

        # Mouse Pan Binding: right-click drag or middle-click drag to pan void
        drag_state = {"last_x": 0, "last_y": 0}

        def _on_mouse_down(event):
            drag_state["last_x"] = event.x
            drag_state["last_y"] = event.y

        def _on_mouse_drag(event):
            dx = event.x - drag_state["last_x"]
            dy = event.y - drag_state["last_y"]
            drag_state["last_x"] = event.x
            drag_state["last_y"] = event.y
            self._cam_x -= dx
            self._cam_y -= dy
            self._redraw()

        canvas.bind("<Button-2>", _on_mouse_down)
        canvas.bind("<B2-Motion>", _on_mouse_drag)
        canvas.bind("<Button-3>", _on_mouse_down)
        canvas.bind("<B3-Motion>", _on_mouse_drag)

        # Apply Windows WS_EX_TRANSPARENT click-through overlay
        root.update()
        try:
            hwnd = root.winfo_id()
            self._hwnd = hwnd
            if _HAS_WIN32:
                style = win32gui.GetWindowLong(hwnd, win32con.GWL_EXSTYLE)
                win32gui.SetWindowLong(hwnd, win32con.GWL_EXSTYLE,
                                       style | win32con.WS_EX_LAYERED | win32con.WS_EX_TRANSPARENT)
        except Exception:
            pass

        ready_evt.set()

        # Initial Draw
        self._redraw()

        # Periodic Queue & Animation Handler
        def _poll_queue():
            try:
                while not self._cmd_queue.empty():
                    action, data = self._cmd_queue.get_nowait()
                    if action == "show":
                        root.deiconify()
                        self._is_open = True
                        self._is_spawning = True
                        self._spawn_anim_radius = 10.0
                        self._redraw()
                    elif action == "hide":
                        root.withdraw()
                        self._is_open = False
                    elif action == "add_element":
                        self._render_element(data)
                    elif action == "clear_all":
                        canvas.delete("all")
                        self._draw_grid()
                    elif action == "redraw":
                        self._redraw()
                    elif action == "animate_camera":
                        self._target_cam_x, self._target_cam_y = data
                        self._cam_animating = True
            except Exception:
                pass

            # Spawning dot illumination wave across the screen
            if self._is_spawning:
                self._spawn_anim_radius += 75.0
                max_reach = math.hypot(self._screen_w, self._screen_h) * 0.75
                if self._spawn_anim_radius > max_reach:
                    self._is_spawning = False
                self._redraw()

            # Camera Animation (smooth easing toward target)
            if self._cam_animating:
                dx = self._target_cam_x - self._cam_x
                dy = self._target_cam_y - self._cam_y
                dist = math.hypot(dx, dy)
                if dist < 2.0:
                    self._cam_x = self._target_cam_x
                    self._cam_y = self._target_cam_y
                    self._cam_animating = False
                    self._redraw()
                else:
                    self._cam_x += dx * 0.25
                    self._cam_y += dy * 0.25
                    self._redraw()

            root.after(16, _poll_queue)

        root.after(16, _poll_queue)
        root.mainloop()

    # ── Internal Rendering Routines ──────────────────────────────────

    def _redraw(self):
        if not self._canvas:
            return
        self._canvas.delete("all")
        self._draw_grid()
        for elem in self._elements:
            self._render_element(elem)

    def _draw_grid(self):
        """Draw aesthetic translucent dots that naturally shift with camera movement."""
        if not self._canvas:
            return
        spacing = self._grid_spacing
        dot_color = self._theme["dot"]

        # Calculate grid origin based on camera offset
        offset_x = int(-self._cam_x % spacing)
        offset_y = int(-self._cam_y % spacing)

        mid_x = self._screen_w / 2.0
        mid_y = self._screen_h / 2.0

        # Draw dots in matrix with 20-25% luminescence & spawning illumination wave
        for x in range(offset_x - spacing, self._screen_w + spacing, spacing):
            for y in range(offset_y - spacing, self._screen_h + spacing, spacing):
                cur_dot = dot_color
                r = 1
                if self._is_spawning:
                    d = math.hypot(x - mid_x, y - mid_y)
                    if abs(d - self._spawn_anim_radius) < 60:
                        cur_dot = self._theme["accent"]
                        r = 2
                self._canvas.create_oval(x - r, y - r, x + r, y + r,
                                         fill=cur_dot, outline=cur_dot, tags="grid")

        # Top-left subtle HUD label
        hud_text = f"TEACHING VOID SPACE • ({self._cam_x:.0f}, {self._cam_y:.0f}) • zoom={self._zoom:.2f}x • {len(self._elements)} concepts"
        self._canvas.create_text(24, 24, text=hud_text, anchor="nw",
                                 fill=self._theme["dot"], font=("Consolas", 9, "bold"), tags="hud")


    def _render_element(self, elem: Dict[str, Any]):
        """Render a world-coordinate element onto screen canvas with camera transformation."""
        if not self._canvas:
            return
        etype = elem.get("type")
        cx = self._cam_x
        cy = self._cam_y

        if etype == "shape":
            shape = elem.get("shape", "rect")
            wx = elem.get("wx", 0.0)
            wy = elem.get("wy", 0.0)
            w = elem.get("w", 160.0)
            h = elem.get("h", 100.0)
            color = elem.get("color", self._theme["accent"])
            label = elem.get("label", "")

            # Screen coordinates
            sx1 = wx - cx
            sy1 = wy - cy
            sx2 = sx1 + w
            sy2 = sy1 + h

            # Culling: check if visible on screen
            if sx2 < -50 or sx1 > self._screen_w + 50 or sy2 < -50 or sy1 > self._screen_h + 50:
                return

            fill_color = self._theme["card_bg"] if elem.get("fill", True) else ""

            if shape in ("circle", "oval"):
                self._canvas.create_oval(sx1, sy1, sx2, sy2, outline=color, width=2,
                                         fill=fill_color)
            elif shape == "diamond":
                mid_x = (sx1 + sx2) / 2
                mid_y = (sy1 + sy2) / 2
                pts = [mid_x, sy1, sx2, mid_y, mid_x, sy2, sx1, mid_y]
                self._canvas.create_polygon(pts, outline=color, width=2, fill=fill_color)
            elif shape == "star":
                mx = (sx1 + sx2) / 2
                my = (sy1 + sy2) / 2
                r_out = min(w, h) / 2
                r_in = r_out * 0.42
                star_pts = []
                for i in range(10):
                    angle = (i * math.pi / 5) - (math.pi / 2)
                    r = r_out if i % 2 == 0 else r_in
                    star_pts.extend([mx + r * math.cos(angle), my + r * math.sin(angle)])
                self._canvas.create_polygon(star_pts, outline=color, width=2, fill=fill_color)
            elif shape == "heart":
                mx = (sx1 + sx2) / 2
                my = (sy1 + sy2) / 2
                scale = min(w, h) / 34
                heart_pts = []
                for step in range(32):
                    t = step * (2 * math.pi / 32)
                    hx = 16 * (math.sin(t) ** 3)
                    hy = -(13 * math.cos(t) - 5 * math.cos(2 * t) - 2 * math.cos(3 * t) - math.cos(4 * t))
                    heart_pts.extend([mx + hx * scale, my + hy * scale])
                self._canvas.create_polygon(heart_pts, outline=color, width=2, fill=fill_color)
            elif shape == "card":
                # High-tech card with accent title bar
                self._canvas.create_rectangle(sx1, sy1, sx2, sy2, outline=color, width=2,
                                              fill=fill_color)
                self._canvas.create_rectangle(sx1, sy1, sx2, sy1 + 24, outline=color, width=1,
                                              fill=color)
                if label:
                    self._canvas.create_text(sx1 + 8, sy1 + 12, text=label, anchor="w",
                                             fill="#000000", font=("Segoe UI", 10, "bold"))
            elif (shape in ("triangle", "pentagon", "hexagon", "heptagon", "septagon", "octagon", "nonagon", "enneagon", "decagon", "dodecagon")
                  or any(shape.startswith(p) for p in ("polygon:", "ngon:", "poly:"))
                  or "-gon" in shape):
                polygon_sides = {
                    "triangle": 3, "pentagon": 5, "hexagon": 6, "heptagon": 7, "septagon": 7,
                    "octagon": 8, "nonagon": 9, "enneagon": 9, "decagon": 10, "dodecagon": 12
                }
                n = polygon_sides.get(shape, 9)
                if ":" in shape:
                    try: n = int(shape.split(":")[1])
                    except Exception: n = 9
                elif "-gon" in shape:
                    try: n = int(shape.split("-gon")[0])
                    except Exception: n = 9
                mx = (sx1 + sx2) / 2
                my = (sy1 + sy2) / 2
                rx = w / 2.0
                ry = h / 2.0
                poly_pts = []
                for i in range(n):
                    ang = (2.0 * math.pi * i / float(n)) - (math.pi / 2.0)
                    poly_pts.extend([mx + rx * math.cos(ang), my + ry * math.sin(ang)])
                self._canvas.create_polygon(poly_pts, outline=color, width=3, fill=fill_color)
            else:
                self._canvas.create_rectangle(sx1, sy1, sx2, sy2, outline=color, width=2,
                                              fill=fill_color)

            if label and shape != "card":
                self._canvas.create_text((sx1 + sx2) / 2, (sy1 + sy2) / 2, text=label,
                                         fill=color, font=("Segoe UI", 11, "bold"))

        elif etype == "text":
            wx = elem.get("wx", 0.0)
            wy = elem.get("wy", 0.0)
            text = elem.get("text", "")
            header = elem.get("header", "")
            font_sz = elem.get("font_size", 13)
            color = elem.get("color", self._theme["text"])

            sx = wx - cx
            sy = wy - cy

            if header:
                self._canvas.create_text(sx, sy, text=f"■ {header}", anchor="nw",
                                         fill=self._theme["header"],
                                         font=("Segoe UI", font_sz + 2, "bold"))
                sy += font_sz + 8

            self._canvas.create_text(sx, sy, text=text, anchor="nw",
                                     fill=color, font=("Consolas", font_sz))

        elif etype == "arrow":
            fx = elem.get("from_x", 0.0) - cx
            fy = elem.get("from_y", 0.0) - cy
            tx = elem.get("to_x", 0.0) - cx
            ty = elem.get("to_y", 0.0) - cy
            color = elem.get("color", self._theme["arrow"])
            label = elem.get("label", "")

            self._canvas.create_line(fx, fy, tx, ty, fill=color, width=2,
                                     arrow=tk.LAST, arrowshape=(12, 15, 5))

            if label:
                mx = (fx + tx) / 2
                my = (fy + ty) / 2 - 10
                self._canvas.create_text(mx, my, text=label, fill=color,
                                         font=("Segoe UI", 9, "bold"))

        elif etype == "stroke":
            pts = elem.get("points", [])
            color = elem.get("color", self._theme["accent"])
            width = elem.get("width", 3)
            flat_pts = []
            for px, py in pts:
                flat_pts.extend([px - cx, py - cy])
            if len(flat_pts) >= 4:
                self._canvas.create_line(flat_pts, fill=color, width=width,
                                         capstyle=tk.ROUND, joinstyle=tk.ROUND, smooth=True)


# Global Singleton accessor
def get_teaching_void() -> TeachingVoid:
    return TeachingVoid()



# ═════════════════════════════════════════════════════════════════════════════
# ANIMATED LESSON RENDERER
# -----------------------------------------------------------------------------
# Text / textbook / storybook / notes / image / video  →  a self-contained,
# animated, narrated HTML lesson, page by page.
#
#   * the brain's understanding layer (hojaiga_ml_engine) reads each page:
#     key concepts (RAKE), relations (part-of, flows-to, causes ...), numbers
#   * each page becomes a scene chosen from what the text *does*:
#     process (things moving between parts), structure (a whole and its parts),
#     comparison, cycle, timeline, math (exact calculation steps), story
#     (setting, characters, word effects), or concept map
#   * every scene can switch to a living 3D view (drag to rotate, wheel/pinch
#     to zoom, labels stay readable) and to a 4-view hologram layout for a
#     Pepper's-ghost pyramid on a Raspberry Pi display
#   * narration uses the viewer's speech synthesizer; words light up as spoken
#   * images are traced stroke by stroke (Sobel edges → polylines), videos are
#     sampled into key frames and traced the same way
#
# The visual vocabulary (settings, characters, word effects, subject colours)
# lives in <BRAIN_HOME>/render_lexicon.json — editable and extendable without
# code; the defaults below only seed that file.
# ═════════════════════════════════════════════════════════════════════════════

import base64 as _r_base64
import json as _r_json
import os as _r_os
import re as _r_re
from pathlib import Path as _RPath

_R_DEFAULT_LEXICON = {
    "settings": {
        "night": ["night", "dark", "moon", "midnight", "evening"],
        "stars": ["star", "stars", "galaxy", "constellation"],
        "storm": ["storm", "stormy", "thunder", "lightning", "rain", "rainy"],
        "forest": ["forest", "woods", "tree", "trees", "jungle"],
        "village": ["village", "house", "home", "town", "cottage"],
        "hill": ["hill", "mountain", "valley", "cliff"],
        "sea": ["sea", "ocean", "beach", "wave", "waves", "river", "lake"],
        "space": ["space", "planet", "orbit", "rocket", "earth", "sun"],
        "snow": ["snow", "winter", "ice", "frozen"],
        "day": ["morning", "sunny", "day", "sunrise"],
    },
    "creatures": ["fox", "dog", "cat", "bird", "rabbit", "bear", "lion", "wolf", "mouse", "horse", "owl",
                  "dragon", "fish", "deer", "tiger", "monkey", "elephant", "frog", "duck"],
    "people": ["girl", "boy", "mother", "father", "king", "queen", "prince", "princess", "teacher", "child",
               "man", "woman", "grandma", "grandpa", "friend", "doctor", "farmer"],
    "effects": {
        "shake": ["crash", "crashed", "boom", "bang", "thunder", "shook", "exploded", "slammed", "roared"],
        "wave": ["howled", "whooshed", "swirled", "wind", "flowed", "waved"],
        "glow": ["glowing", "glowed", "bright", "shining", "shone", "sparkled", "light", "magic"],
        "whisper": ["whispered", "quietly", "softly", "silent", "hushed"],
        "dash": ["ran", "raced", "rushed", "flew", "jumped", "hurried", "dashed", "moves", "travels"],
        "bounce": ["laughed", "joy", "happy", "danced", "dancing", "giggled", "cheered"],
        "grow": ["tall", "huge", "giant", "enormous", "big", "grew", "expanded"],
        "shrink": ["tiny", "small", "little", "shrank"],
        "shiver": ["shivering", "cold", "afraid", "scared", "trembled"],
    },
    "subjects": {"biology": "#d6336c", "chemistry": "#ae3ec9", "physics": "#4263eb", "math": "#1098ad",
                 "history": "#e8590c", "geography": "#2b8a3e", "social studies": "#f08c00",
                 "language": "#7048e8", "story": "#f59f00", "default": "#4c6ef5"},
}

_R_FLOW = [
    _r_re.compile(r"from\s+(?:the\s+)?([a-z][a-z \-]{1,40}?)\s+(?:to|into|toward|towards)\s+(?:the\s+)?([a-z][a-z \-]{1,40}?)(?:[,.;]|$|\s+(?:where|while|and|which|during|if)\b)", _r_re.I),
    _r_re.compile(r"through\s+(?:the\s+)?([a-z][a-z \-]{1,40}?)\s+(?:to|into)\s+(?:the\s+)?([a-z][a-z \-]{1,40}?)(?:[,.;]|$|\s)", _r_re.I),
    _r_re.compile(r"(?:the\s+)?([a-z][a-z \-]{1,40}?)\s+(?:connects?|leads?|opens?)\s+(?:to|into)\s+(?:the\s+)?([a-z][a-z \-]{1,40}?)(?:[,.;]|$|\s)", _r_re.I),
    _r_re.compile(r"(?:the\s+)?([a-z][a-z \-]{1,40}?)\s+(?:joins?|fuses? with|meets?|enters?|attaches to|implants? in)\s+(?:an?\s+|the\s+)?([a-z][a-z \-]{1,40}?)(?:[,.;]|$|\s+(?:in|at|to|and|of)\b)", _r_re.I),
    _r_re.compile(r"(?:the\s+)?([a-z][a-z \-]{1,30}?)\s+(?:\w+\s+and\s+)?(?:moves?|travels?|goes|migrates?|is carried|are carried)\s+(?:to|into|toward)\s+(?:the\s+)?([a-z][a-z \-]{1,40}?)(?:[,.;]|$|\s)", _r_re.I),
    _r_re.compile(r"(?:the\s+)?([a-z][a-z \-]{1,40}?)\s+(?:is|are)\s+called\s+(?:an?\s+|the\s+)?([a-z][a-z \-]{1,40}?)(?:[,.;]|$|\s)", _r_re.I),
    _r_re.compile(r"(?:the\s+)?([a-z][a-z \-]{1,40}?)\s+(?:becomes?|turns? into|changes? into|develops? into)\s+(?:a\s+|an\s+|the\s+)?([a-z][a-z \-]{1,40}?)(?:[,.;]|$|\s)", _r_re.I),
]
_R_PART = [
    _r_re.compile(r"(?:the\s+)?([a-z][a-z \-]{1,40}?)\s+(?:is|are)\s+(?:a\s+)?part\s+of\s+(?:the\s+)?([a-z][a-z \-]{1,50}?)(?:[,.;]|$)", _r_re.I),
    _r_re.compile(r"(?:the\s+)?([a-z][a-z \-]{1,40}?)\s+(?:consists? of|contains?|includes?|is made of|has)\s+(.+?)(?:[.;]|$)", _r_re.I),
]
_R_STOPLEAD = _r_re.compile(r"^(?:the|a|an|this|that|these|those|its|their|his|her)\s+", _r_re.I)


def _r_clean(phrase: str) -> str:
    phrase = phrase.strip().lower()
    if _r_re.match(r"(?:during|after|before|when|while|in|on|at|if|once)\b", phrase):
        m = list(_r_re.finditer(r"\b(?:a|an|the)\s+", phrase))   # "during ovulation an egg" → "egg"
        if m:
            phrase = phrase[m[-1].end():]
    cut = list(_r_re.finditer(r"\b(?:when|where|that|which|who|if|because|after|before)\s+", phrase))
    if cut and cut[-1].end() < len(phrase):          # keep the clause that holds the actor
        phrase = phrase[cut[-1].end():]
    phrase = _r_re.sub(r"(?:\s+\w+)?\s+and$", "", phrase)   # "zygote divides and" → "zygote"
    phrase = _R_STOPLEAD.sub("", phrase)
    phrase = _r_re.sub(r"\s+", " ", phrase)
    return " ".join(phrase.split()[:4])


class AnimatedLessonRenderer:
    def __init__(self, brain_home=None):
        home = _RPath(brain_home or _r_os.environ.get("HOJAIGA_BRAIN_HOME", _r_os.path.join("storage", "brain")))
        home.mkdir(parents=True, exist_ok=True)
        self.lexicon_path = home / "render_lexicon.json"
        if not self.lexicon_path.exists():
            self.lexicon_path.write_text(_r_json.dumps(_R_DEFAULT_LEXICON, indent=1), encoding="utf-8")
        self.lex = _r_json.loads(self.lexicon_path.read_text(encoding="utf-8"))
        for k, v in _R_DEFAULT_LEXICON.items():   # new default keys appear without overwriting edits
            self.lex.setdefault(k, v)

    # ── reading ─────────────────────────────────────────────────────────────
    @staticmethod
    def _engine():
        from core_organs import hojaiga_ml_engine as eng
        return eng

    def _read(self, path: str) -> tuple[str, list[str]]:
        """Returns (text, media_paths)."""
        eng = self._engine()
        p = _RPath(path)
        if not p.exists():
            return path, []          # raw text given on the command line
        ext = p.suffix.lower()
        if ext in eng.IMAGE_EXT or ext in eng.VIDEO_EXT:
            return eng.DatasetReader._sidecar_text(p), [str(p)]
        items = eng.DatasetReader().read(p)
        return "\n\n".join(it.text for it in items if it.text), [it.image or it.video for it in items
                                                                 if it.image or it.video]

    def _pages(self, text: str, mode: str) -> list[dict]:
        text = text.replace("\r", "")
        marked = _r_re.split(r"(?im)^\s*(?:page|chapter|scene|slide)\s+(\d+)\s*[:.\-]?\s*$", text)
        if len(marked) > 2:
            pages = [{"title": f"Page {marked[i]}", "text": marked[i + 1].strip()}
                     for i in range(1, len(marked) - 1, 2) if marked[i + 1].strip()]
            return pages
        heads = _r_re.split(r"(?m)^#{1,6}\s+(.+)$", text)
        if len(heads) > 2:
            pages = []
            intro = heads[0].strip()
            if intro:
                pages.append({"title": "", "text": intro})
            for i in range(1, len(heads) - 1, 2):
                body = heads[i + 1].strip()
                paras = [q for q in _r_re.split(r"\n\s*\n", body) if q.strip()] or [""]
                for j, para in enumerate(paras):
                    pages.append({"title": heads[i].strip() + (f" ({j + 1})" if len(paras) > 1 else ""),
                                  "text": para.strip()})
            return [p for p in pages if p["text"]]
        paras = [q.strip() for q in _r_re.split(r"\n\s*\n", text) if q.strip()]
        return [{"title": "", "text": q} for q in paras]

    # ── understanding a page ──────────────────────────────────────────────────
    def _setting(self, words: set) -> list[str]:
        return [name for name, cues in self.lex["settings"].items() if words & set(cues)]

    def _cast(self, full_text: str) -> dict:
        """Characters of the whole book: lexicon creatures/people plus proper names
        (capitalised mid-sentence, or recurring and never written in lower case).
        Quoted speech is ignored so words inside dialogue are not mistaken for names."""
        text = _r_re.sub(r"(?im)^\s*(?:page|chapter|scene|slide)\s+\d+.*$", "\n", full_text)
        text = _r_re.sub(r"[\"“][^\"”]*[\"”]", " ", text)
        lower_words = set(_r_re.findall(r"\b[a-z][a-z]+\b", text))
        cap_counts: dict[str, int] = {}
        mid: set = set()
        cast: dict[str, dict] = {}
        for s in self._engine().b_sentences(text):
            toks = _r_re.findall(r"[A-Za-z][A-Za-z]+", s)
            for i, w in enumerate(toks):
                lw = w.lower()
                if lw in self.lex["creatures"]:
                    cast.setdefault(lw, {"name": lw, "kind": "creature"})
                elif lw in self.lex["people"]:
                    cast.setdefault(lw, {"name": lw, "kind": "person"})
                elif w[0].isupper() and lw not in self._engine()._B_STOP and lw not in ("page", "chapter", "scene"):
                    cap_counts[w] = cap_counts.get(w, 0) + 1
                    if i > 0:
                        mid.add(w)
        for w, n in cap_counts.items():
            if w.lower() in lower_words:
                continue
            if w in mid or n >= 2:
                cast.setdefault(w.lower(), {"name": w, "kind": "person"})
        return cast

    def _characters(self, text: str, sents: list[str]) -> list[dict]:
        words = {w.lower() for w in _r_re.findall(r"[A-Za-z]+", text)}
        return [c for k, c in getattr(self, "_book_cast", {}).items() if k in words][:4]

    def _effects(self, sents: list[str]) -> dict:
        eff = {}
        for s in sents:
            for w in _r_re.findall(r"[A-Za-z']+", s):
                for name, cues in self.lex["effects"].items():
                    if w.lower() in cues:
                        eff[w.lower()] = name
        return eff

    def _flows(self, sents: list[str]) -> list[tuple[str, str, str]]:
        edges = []
        for s in sents:
            carrier = _r_clean(_r_re.split(r"\s+(?:moves?|travels?|passes?|flows?|goes|go|is carried|are carried)\b",
                                          s, maxsplit=1)[0]) if _r_re.search(
                r"\b(?:moves?|travels?|passes?|flows?|goes|go|carried)\b", s, _r_re.I) else ""
            for rx in _R_FLOW:
                for m in rx.finditer(s):
                    a, b = _r_clean(m.group(1)), _r_clean(m.group(2))
                    if a and b and a != b and len(a) > 2 and len(b) > 2:
                        edges.append((a, b, _r_clean(carrier)[:24]))
        out, seen = [], set()
        for a, b, c in edges:
            if (a, b) not in seen:
                seen.add((a, b))
                out.append((a, b, c))
        return out

    def _parts(self, sents: list[str]) -> list[tuple[str, str]]:
        pairs = []
        for s in sents:
            m = _R_PART[0].search(s)
            if m:
                pairs.append((_r_clean(m.group(2)), _r_clean(m.group(1))))
                continue
            m = _R_PART[1].search(s)
            if m:
                whole = _r_clean(m.group(1))
                for part in _r_re.split(r",\s*|\s+and\s+", m.group(2)):
                    part = _r_clean(part)
                    if part and part != whole and len(part.split()) <= 4:
                        pairs.append((whole, part))
        return pairs

    @staticmethod
    def _chain(edges: list[tuple[str, str, str]]) -> list[list[str]]:
        """Join edges into ordered paths (longest first)."""
        nxt = {}
        indeg = {}
        for a, b, _ in edges:
            nxt.setdefault(a, []).append(b)
            indeg[b] = indeg.get(b, 0) + 1
            indeg.setdefault(a, indeg.get(a, 0))
        carriers = {c for _, _, c in edges if c}
        if len(carriers) == 1 and all(c for _, _, c in edges):   # one thing travelling: one journey
            journey = []
            for a, b, _ in edges:
                for x in (a, b):
                    if x not in journey:
                        journey.append(x)
            return [journey]
        starts = [n for n, d in indeg.items() if d == 0] or [edges[0][0]]
        paths = []
        for s in starts:
            path, cur = [s], s
            while cur in nxt and nxt[cur]:
                cur = nxt[cur][0]
                if cur in path:
                    break
                path.append(cur)
            paths.append(path)
        return sorted(paths, key=len, reverse=True)

    def _scene(self, page: dict, mode: str, grade: str) -> dict:
        eng = self._engine()
        text = page["text"]
        sents = eng.b_sentences(text)
        words = {w.lower() for w in _r_re.findall(r"[A-Za-z]+", text)}
        scene = {"title": page["title"], "sentences": sents, "effects": self._effects(sents)}
        keyphrases = [k for k, _ in eng.rake_keyphrases(text, top=8)]
        flows = self._flows(sents)
        parts = self._parts(sents)
        has_quote = bool(_r_re.search(r"[\"“”]", text))
        past = len(_r_re.findall(r"\b\w+ed\b", text)) / max(1, len(text.split()))
        chars = self._characters(text, sents)
        storyish = mode == "story" or (mode == "auto" and (has_quote or past > 0.06) and chars and not flows)
        math_expr = None
        for m in _r_re.finditer(r"[\d.]+(?:\s*[+\-*/^×÷]\s*[\d.()]+)+", text):
            val = eng.safe_calculate(m.group(0))
            if val is not None:
                math_expr = {"expr": m.group(0).strip(), "value": f"{val:.10g}"}
                break
        if storyish:
            scene.update(type="story", setting=self._setting(words) or ["day"], characters=chars)
        elif math_expr:
            scene.update(type="math", equation=math_expr, terms=keyphrases[:5])
        elif flows:
            chains = self._chain(flows)
            scene.update(type="process", path=chains[0], branches=chains[1:3],
                         carriers=[c for _, _, c in flows if c][:3],
                         edges=[{"from": a, "to": b, "carrier": c} for a, b, c in flows])
        elif parts:
            whole = max({w for w, _ in parts}, key=lambda w: sum(1 for x, _ in parts if x == w))
            scene.update(type="structure", whole=whole,
                         parts=list(dict.fromkeys(p for w, p in parts if w == whole))[:8],
                         others=[{"whole": w, "part": p} for w, p in parts if w != whole][:6])
        elif _r_re.search(r"\b(whereas|unlike|compared|versus|vs\.?|while)\b", text, _r_re.I) and len(keyphrases) >= 2:
            scene.update(type="comparison", left=keyphrases[0], right=keyphrases[1], terms=keyphrases[2:6])
        elif _r_re.search(r"\b(cycle|repeats?|again and again|returns? to)\b", text, _r_re.I):
            scene.update(type="cycle", steps=keyphrases[:6])
        elif len(_r_re.findall(r"\b(1[0-9]{3}|20[0-9]{2})\b", text)) >= 2:
            events = []
            for s in sents:
                y = _r_re.search(r"\b(1[0-9]{3}|20[0-9]{2})\b", s)
                if y:
                    events.append({"year": y.group(1), "text": s[:90]})
            scene.update(type="timeline", events=events[:7])
        else:
            scene.update(type="concept", center=(keyphrases or [page["title"] or "idea"])[0], terms=keyphrases[1:8])
        if grade and grade.isdigit() and int(grade) <= 4:
            scene["sentences"] = [s if len(s.split()) <= 18 else " ".join(s.split()[:18]) + "…" for s in sents]
        scene["keyphrases"] = keyphrases
        return scene

    # ── images & video: trace into strokes ────────────────────────────────────
    @staticmethod
    def trace_image(path: str, size: int = 360, max_strokes: int = 900) -> dict:
        import numpy as np
        from PIL import Image
        img = Image.open(path).convert("RGB")
        w, h = img.size
        scale = size / max(w, h)
        img = img.resize((max(1, int(w * scale)), max(1, int(h * scale))))
        g = np.asarray(img.convert("L"), dtype="float32")
        gx = np.zeros_like(g)
        gy = np.zeros_like(g)
        gx[1:-1, 1:-1] = (g[:-2, 2:] + 2 * g[1:-1, 2:] + g[2:, 2:]) - (g[:-2, :-2] + 2 * g[1:-1, :-2] + g[2:, :-2])
        gy[1:-1, 1:-1] = (g[2:, :-2] + 2 * g[2:, 1:-1] + g[2:, 2:]) - (g[:-2, :-2] + 2 * g[:-2, 1:-1] + g[:-2, 2:])
        mag = np.hypot(gx, gy)
        thr = np.percentile(mag, 88)
        edge = mag > thr
        visited = np.zeros_like(edge)
        strokes = []
        H, W = edge.shape
        nbrs = [(-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1)]
        ys, xs = np.nonzero(edge)
        order = np.lexsort((xs, ys))
        for idx in order:
            y, x = int(ys[idx]), int(xs[idx])
            if visited[y, x]:
                continue
            pts = [(x, y)]
            visited[y, x] = True
            cy, cx = y, x
            while len(pts) < 400:
                for dy, dx in nbrs:
                    ny, nx_ = cy + dy, cx + dx
                    if 0 <= ny < H and 0 <= nx_ < W and edge[ny, nx_] and not visited[ny, nx_]:
                        visited[ny, nx_] = True
                        pts.append((nx_, ny))
                        cy, cx = ny, nx_
                        break
                else:
                    break
            if len(pts) >= 6:
                strokes.append(pts[::2])
            if len(strokes) >= max_strokes:
                break
        strokes.sort(key=len, reverse=True)
        buf = __import__("io").BytesIO()
        img.save(buf, format="JPEG", quality=82)
        return {"width": img.size[0], "height": img.size[1], "strokes": strokes[:max_strokes],
                "image": "data:image/jpeg;base64," + _r_base64.b64encode(buf.getvalue()).decode()}

    def _media_scenes(self, media: list[str]) -> list[dict]:
        eng = self._engine()
        scenes = []
        for m in media:
            if not m:
                continue
            ext = _RPath(m).suffix.lower()
            try:
                if ext in eng.IMAGE_EXT:
                    scenes.append({"type": "trace", "title": _RPath(m).name, "sentences": [], "effects": {},
                                   "trace": self.trace_image(m)})
                elif ext in eng.VIDEO_EXT:
                    import tempfile
                    from PIL import Image
                    frames = eng.load_video_frames(m, frames=6, size=256)
                    for i, fr in enumerate(frames):
                        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tf:
                            Image.fromarray((fr.transpose(1, 2, 0) * 255).astype("uint8")).save(tf.name)
                            tr = self.trace_image(tf.name, size=320, max_strokes=500)
                        _r_os.unlink(tf.name)
                        scenes.append({"type": "trace", "title": f"{_RPath(m).name} · frame {i + 1}",
                                       "sentences": [], "effects": {}, "trace": tr})
            except Exception as exc:
                scenes.append({"type": "concept", "title": _RPath(m).name, "center": "media",
                               "terms": [], "sentences": [f"Could not read this media: {exc}"], "effects": {}})
        return scenes

    # ── output ──────────────────────────────────────────────────────────────
    def plan(self, text: str, media: list[str] = None, subject: str = "", grade: str = "", mode: str = "auto",
             title: str = "") -> dict:
        pages = self._pages(text, mode) if text.strip() else []
        self._book_cast = self._cast(text) if text.strip() else {}
        scenes = [self._scene(p, mode, grade) for p in pages]
        scenes += self._media_scenes(media or [])
        subj = (subject or ("story" if scenes and all(s["type"] == "story" for s in scenes) else "")).lower()
        color = self.lex["subjects"].get(subj, self.lex["subjects"]["default"])
        return {"title": title or (pages[0]["title"] if pages and pages[0]["title"] else "Lesson"),
                "subject": subj, "grade": grade, "accent": color, "scenes": scenes,
                "lexicon": {"effects": self.lex["effects"]}}

    def render(self, text: str, out: str, media=None, subject: str = "", grade: str = "", mode: str = "auto",
               hologram: bool = False, title: str = "") -> dict:
        plan = self.plan(text, media, subject, grade, mode, title)
        plan["hologram"] = hologram
        html = _LESSON_TEMPLATE.replace("__TITLE__", _r_re.sub(r"[<>&]", "", plan["title"])[:80]) \
                               .replace("__PLAN__", _r_json.dumps(plan).replace("</", "<\\/"))
        _RPath(out).write_text(html, encoding="utf-8")
        return {"out": str(out), "scenes": [s["type"] for s in plan["scenes"]], "subject": plan["subject"],
                "bytes": len(html)}

    def render_file(self, path: str, out: str, **kw) -> dict:
        text, media = self._read(path)
        first = _r_re.search(r"(?m)^#\s+(.+)$", text)
        stem = _RPath(path).stem.replace("_", " ").replace("-", " ").title() if _RPath(path).exists() else ""
        return self.render(text, out, media=media, title=(first.group(1) if first else stem), **kw)


_LESSON_TEMPLATE = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>__TITLE__</title>
<style>
:root{--bg:#0b1020;--panel:#121a30;--fg:#eef2fb;--mut:#9aa6c4;--line:#27324f;--accent:#4c6ef5}
@media (prefers-color-scheme: light){:root:not([data-theme="dark"]){--bg:#f4f6fb;--panel:#ffffff;--fg:#121829;--mut:#55607a;--line:#d7dce8}}
*{box-sizing:border-box}html,body{margin:0;background:var(--bg);color:var(--fg);font:16px/1.5 system-ui,-apple-system,"Segoe UI",sans-serif}
header{display:flex;flex-wrap:wrap;gap:8px 16px;align-items:center;justify-content:space-between;padding:12px 16px;border-bottom:1px solid var(--line)}
h1{font-size:18px;margin:0}.chip{font-size:12px;padding:2px 10px;border-radius:99px;background:var(--accent);color:#fff;text-transform:capitalize}
main{max-width:1100px;margin:0 auto;padding:12px 16px 24px}
.stage{position:relative;width:100%;aspect-ratio:16/9;background:var(--panel);border:1px solid var(--line);border-radius:14px;overflow:hidden}
.stage svg,.stage canvas{position:absolute;inset:0;width:100%;height:100%}
.stage canvas{display:none;touch-action:none;cursor:grab;background:#000}
.stage.mode3d canvas{display:block}.stage.mode3d svg{display:none}
.scene-title{position:absolute;left:12px;top:10px;font-weight:700;font-size:14px;color:var(--fg);z-index:2;background:color-mix(in srgb,var(--panel) 85%,transparent);padding:2px 10px;border-radius:8px}.scene-title:empty{display:none}
.hint{position:absolute;right:12px;bottom:8px;font-size:12px;color:#9aa6c4;z-index:2;display:none}.stage.mode3d .hint{display:block}
.caption{min-height:84px;margin:14px 2px 10px;font-size:19px;line-height:1.6}
.caption .s{opacity:.38;transition:opacity .3s}.caption .s.on{opacity:1}.caption .w.say{background:color-mix(in srgb,var(--accent) 35%,transparent);border-radius:4px}
.controls{display:flex;flex-wrap:wrap;gap:8px;align-items:center}
button{font:inherit;font-size:14px;padding:8px 14px;border-radius:10px;border:1px solid var(--line);background:var(--panel);color:var(--fg);cursor:pointer}
button.on{background:var(--accent);color:#fff;border-color:var(--accent)}.pageno{color:var(--mut);font-size:14px;margin-left:auto}
.lbl{font:600 15px system-ui,sans-serif;fill:var(--fg);paint-order:stroke;stroke:var(--panel);stroke-width:4px}
.small{font:13px system-ui,sans-serif;fill:var(--mut)}
.pop{opacity:0;transform-box:fill-box;transform-origin:center;animation:pop .7s cubic-bezier(.2,1.4,.4,1) forwards}
@keyframes pop{from{opacity:0;transform:scale(.3)}to{opacity:1;transform:scale(1)}}
.draw{stroke-dasharray:var(--len,1200);stroke-dashoffset:var(--len,1200);animation:draw 1.4s ease forwards}
@keyframes draw{to{stroke-dashoffset:0}}
.lit{filter:drop-shadow(0 0 10px var(--accent))}.lit .lbl{fill:var(--accent)}
.breathe{animation:breathe 3.5s ease-in-out infinite;transform-box:fill-box;transform-origin:center}
@keyframes breathe{50%{transform:scale(1.04)}}
.bob{animation:bob 2.4s ease-in-out infinite;transform-box:fill-box}@keyframes bob{50%{transform:translateY(-8px)}}
.sway{animation:sway 4s ease-in-out infinite;transform-box:fill-box;transform-origin:bottom center}@keyframes sway{50%{transform:rotate(2.5deg)}}
.twinkle{animation:tw 2s ease-in-out infinite}@keyframes tw{50%{opacity:.2}}
.rain{animation:rain .7s linear infinite}@keyframes rain{to{transform:translate(-30px,120px)}}
.flash{animation:flash 5s infinite}@keyframes flash{0%,91%,100%{opacity:0}92%,95%{opacity:.85}}
.wave{animation:wavex 3s ease-in-out infinite}@keyframes wavex{50%{transform:translateX(-30px)}}
.spin{animation:spin 18s linear infinite;transform-origin:480px 270px}@keyframes spin{to{transform:rotate(360deg)}}
.fx-shake{display:inline-block;animation:shake .35s 3}@keyframes shake{25%{transform:translateX(-3px) rotate(-2deg)}75%{transform:translateX(3px) rotate(2deg)}}
.fx-wave{display:inline-block;animation:wv 1.2s ease-in-out 2}@keyframes wv{25%{transform:translateY(-4px)}75%{transform:translateY(4px)}}
.fx-glow{text-shadow:0 0 10px #ffd43b,0 0 18px #ffd43b}
.fx-whisper{font-style:italic;opacity:.75;font-size:.92em}
.fx-dash{display:inline-block;animation:dash .8s ease 1}@keyframes dash{from{transform:translateX(-30px);opacity:0}}
.fx-bounce{display:inline-block;animation:bnc .6s ease 3}@keyframes bnc{50%{transform:translateY(-7px)}}
.fx-grow{display:inline-block;font-size:1.25em;font-weight:700}.fx-shrink{font-size:.8em}
.fx-shiver{display:inline-block;animation:shake .12s 10}
</style></head>
<body>
<header><h1 id="title"></h1><span class="chip" id="subject"></span></header>
<main>
  <div class="stage" id="stage"><div class="scene-title" id="stitle"></div>
    <svg id="svg" viewBox="0 0 960 540" preserveAspectRatio="xMidYMid meet" aria-label="animated scene"></svg>
    <canvas id="cv"></canvas><div class="hint">drag to rotate · scroll/pinch to zoom · zoom in to read details</div></div>
  <div class="caption" id="caption" aria-live="polite"></div>
  <div class="controls">
    <button id="prev">◀ Prev</button><button id="play" class="on">❚❚ Pause</button><button id="next">Next ▶</button>
    <button id="b3d">3D</button><button id="bholo">Hologram</button><button id="bvoice" class="on">Voice</button>
    <span class="pageno" id="pageno"></span>
  </div>
</main>
<script>
const PLAN = __PLAN__;
const $ = id => document.getElementById(id);
document.documentElement.style.setProperty('--accent', PLAN.accent || '#4c6ef5');
$('title').textContent = PLAN.title; $('subject').textContent = PLAN.subject || 'lesson';
if (!PLAN.subject) $('subject').style.display = 'none';
const svg = $('svg'), cv = $('cv'), stage = $('stage');
let page = 0, playing = true, voice = true, mode3d = false, holo = !!PLAN.hologram, sentIdx = 0, timer = null;
const esc = s => String(s).replace(/[&<>"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
function hash(s){let h=2166136261;for(const c of String(s)){h^=c.charCodeAt(0);h=Math.imul(h,16777619)}return h>>>0}
function hue(s){return hash(s)%360}
function col(s,l=58){return `hsl(${hue(s)} 70% ${l}%)`}
function blob(cx,cy,r,seed){const n=9,pts=[];for(let i=0;i<n;i++){const a=i/n*Math.PI*2,k=0.82+((hash(seed+i)%100)/100)*0.36;pts.push([cx+Math.cos(a)*r*k,cy+Math.sin(a)*r*k*0.8])}
 let d=`M${(pts[0][0]+pts[n-1][0])/2},${(pts[0][1]+pts[n-1][1])/2}`;for(let i=0;i<n;i++){const p=pts[i],q=pts[(i+1)%n];d+=` Q${p[0]},${p[1]} ${(p[0]+q[0])/2},${(p[1]+q[1])/2}`}return d+'Z'}
function wrap(t,max=16){const w=String(t).split(' '),lines=[];let cur='';for(const x of w){if((cur+' '+x).trim().length>max&&cur){lines.push(cur);cur=x}else cur=(cur+' '+x).trim()}if(cur)lines.push(cur);return lines.slice(0,3)}
function label(x,y,t,cls='lbl',max=16){return wrap(t,max).map((l,i,a)=>`<text x="${x}" y="${y+(i-(a.length-1)/2)*18}" text-anchor="middle" dominant-baseline="middle" class="${cls}">${esc(l)}</text>`).join('')}
function node(id,x,y,r,text,delay){return `<g class="pop nd" data-k="${esc(text)}" style="animation-delay:${delay}s"><path d="${blob(x,y,r,text)}" fill="${col(text)}" fill-opacity=".85" stroke="${col(text,35)}" stroke-width="2" class="breathe"/>${label(x,y,text)}</g>`}
function curve(x1,y1,x2,y2,bend=40){const mx=(x1+x2)/2,my=(y1+y2)/2-bend;return `M${x1},${y1} Q${mx},${my} ${x2},${y2}`}
const defs = `<defs><marker id="ar" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto"><path d="M0,0 L10,5 L0,10z" fill="var(--mut)"/></marker>
<radialGradient id="glow"><stop offset="0" stop-color="#fff" stop-opacity=".9"/><stop offset="1" stop-color="#fff" stop-opacity="0"/></radialGradient></defs>`;

// ── scene painters ──────────────────────────────────────────────────────────
const P = {};
P.process = s => {
  const path = s.path, n = path.length, out = [defs], pos = [];
  path.forEach((p,i)=>{const x=110+i*(740/Math.max(1,n-1)),y=270+Math.sin(i*1.3)*90;pos.push([x,y])});
  for(let i=0;i<n-1;i++){const [x1,y1]=pos[i],[x2,y2]=pos[i+1],d=curve(x1+48,y1,x2-52,y2,50);
    out.push(`<path id="e${i}" d="${d}" fill="none" stroke="var(--mut)" stroke-width="3" class="draw" style="--len:600;animation-delay:${.5+i*.6}s" marker-end="url(#ar)"/>`);
    for(let k=0;k<3;k++) out.push(`<circle r="7" fill="${PLAN.accent}" opacity=".95"><animateMotion dur="2.4s" begin="${1.2+i*.6+k*.8}s" repeatCount="indefinite" rotate="auto"><mpath href="#e${i}"/></animateMotion></circle>`);}
  path.forEach((p,i)=>out.push(node('n'+i,pos[i][0],pos[i][1],58,p,i*.6)));
  (s.branches||[]).forEach((b,j)=>{const y=470-j*40; out.push(`<text x="40" y="${y}" class="small pop" style="animation-delay:${1+n*.6}s">also: ${esc(b.join(' → '))}</text>`)});
  if((s.carriers||[]).length) out.push(`<g class="pop" style="animation-delay:1s"><circle cx="40" cy="40" r="7" fill="${PLAN.accent}"/><text x="56" y="45" class="small">= ${esc(s.carriers[0])}</text></g>`);
  return out.join('');
};
P.structure = s => {
  const out=[defs], parts=s.parts||[], n=parts.length; out.push(node('w',480,270,110,s.whole,0));
  parts.forEach((p,i)=>{const a=-Math.PI/2+i/n*Math.PI*2,x=480+Math.cos(a)*300,y=270+Math.sin(a)*190;
    out.push(`<path d="M${480+Math.cos(a)*100},${270+Math.sin(a)*80} L${x-Math.cos(a)*55},${y-Math.sin(a)*45}" stroke="var(--mut)" stroke-width="2.5" class="draw" style="--len:400;animation-delay:${.4+i*.5}s"/>`);
    out.push(node('p'+i,x,y,52,p,.6+i*.5));});
  (s.others||[]).forEach((o,i)=>out.push(`<text x="20" y="${500-i*20}" class="small pop" style="animation-delay:${2+i*.3}s">${esc(o.part)} ⊂ ${esc(o.whole)}</text>`));
  return out.join('');
};
P.concept = s => {
  const out=[defs], t=s.terms||[]; out.push(node('c',480,270,95,s.center,0)); out.push('<g class="spin">');
  t.forEach((x,i)=>{const a=i/t.length*Math.PI*2,px=480+Math.cos(a)*290,py=270+Math.sin(a)*185;
    out.push(`<line x1="480" y1="270" x2="${px}" y2="${py}" stroke="var(--line)" stroke-width="2"/>`);out.push(node('t'+i,px,py,48,x,.4+i*.35))});
  out.push('</g>'); return out.join('');
};
P.cycle = s => {
  const out=[defs], st=s.steps||[], n=st.length||1;
  out.push(`<circle id="ring" cx="480" cy="270" r="190" fill="none" stroke="var(--line)" stroke-width="3" stroke-dasharray="8 8"/>`);
  out.push(`<circle r="10" fill="${PLAN.accent}"><animateMotion dur="6s" repeatCount="indefinite" path="M480,80 a190,190 0 1,1 -1,0"/></circle>`);
  st.forEach((x,i)=>{const a=-Math.PI/2+i/n*Math.PI*2;out.push(node('c'+i,480+Math.cos(a)*190,270+Math.sin(a)*190,50,x,i*.5))});
  return out.join('');
};
P.comparison = s => {
  const out=[defs]; out.push(node('l',250,220,100,s.left,0)); out.push(node('r',710,220,100,s.right,.4));
  out.push(`<line x1="480" y1="60" x2="480" y2="480" stroke="var(--line)" stroke-width="3" class="draw" style="--len:420"/>`);
  (s.terms||[]).forEach((t,i)=>out.push(`<g class="pop" style="animation-delay:${1+i*.4}s">${label(i%2?710:250,380+Math.floor(i/2)*36,t,'small',30)}</g>`));
  return out.join('');
};
P.timeline = s => {
  const out=[defs], ev=s.events||[], n=ev.length||1;
  out.push(`<line x1="60" y1="300" x2="900" y2="300" stroke="var(--mut)" stroke-width="4" class="draw" style="--len:840"/>`);
  ev.forEach((e,i)=>{const x=90+i*(780/Math.max(1,n-1)),up=i%2===0;
    out.push(`<g class="pop" style="animation-delay:${.6+i*.6}s"><circle cx="${x}" cy="300" r="12" fill="${col(e.year)}"/><text x="${x}" y="${up?260:350}" text-anchor="middle" class="lbl">${esc(e.year)}</text>${label(x,up?200:410,e.text,'small',22)}</g>`)});
  return out.join('');
};
P.math = s => {
  const out=[defs], toks=s.equation.expr.split(/\s*([+\-*/^×÷()])\s*/).filter(Boolean);
  let x=480-toks.length*34;
  toks.forEach((t,i)=>{out.push(`<text x="${x}" y="230" font-size="54" font-weight="700" fill="var(--fg)" class="pop" style="animation-delay:${i*.45}s" text-anchor="middle">${esc(t)}</text>`);x+=68});
  out.push(`<text x="480" y="340" text-anchor="middle" font-size="64" font-weight="800" fill="${PLAN.accent}" class="pop" style="animation-delay:${toks.length*.45+.3}s">= ${esc(s.equation.value)}</text>`);
  (s.terms||[]).forEach((t,i)=>out.push(`<text x="480" y="${420+i*24}" text-anchor="middle" class="small pop" style="animation-delay:${2+i*.3}s">${esc(t)}</text>`));
  return out.join('');
};
function person(x,y,c,name,delay){return `<g class="pop" style="animation-delay:${delay}s"><g class="bob"><circle cx="${x}" cy="${y-110}" r="26" fill="#f1c7a3"/><circle cx="${x-9}" cy="${y-114}" r="3" fill="#222"/><circle cx="${x+9}" cy="${y-114}" r="3" fill="#222"/><path d="M${x-9},${y-101} q9,7 18,0" stroke="#222" stroke-width="2" fill="none"/><path d="M${x-30},${y} L${x-22},${y-80} Q${x},${y-92} ${x+22},${y-80} L${x+30},${y} Z" fill="${c}"/><path d="M${x-22},${y-74} l-22,40 M${x+22},${y-74} l22,40" stroke="${c}" stroke-width="9" stroke-linecap="round"/></g><text x="${x}" y="${y+22}" text-anchor="middle" class="lbl">${esc(name)}</text></g>`}
function creature(x,y,c,name,delay,glow){return `<g class="pop" style="animation-delay:${delay}s">${glow?`<circle cx="${x}" cy="${y-40}" r="90" fill="url(#glow)" class="twinkle"/>`:''}<g class="bob"><ellipse cx="${x}" cy="${y-38}" rx="48" ry="26" fill="${c}"/><circle cx="${x+48}" cy="${y-62}" r="22" fill="${c}"/><path d="M${x+36},${y-80} l6,-22 l10,18 M${x+52},${y-82} l10,-20 l6,20" fill="${c}" stroke="${c}" stroke-width="6" stroke-linejoin="round"/><circle cx="${x+56}" cy="${y-64}" r="3" fill="#222"/><path d="M${x-46},${y-44} q-40,-30 -30,-60" stroke="${c}" stroke-width="14" fill="none" stroke-linecap="round"/><path d="M${x-30},${y-16} v18 M${x-10},${y-16} v18 M${x+14},${y-16} v18 M${x+32},${y-16} v18" stroke="${c}" stroke-width="7" stroke-linecap="round"/></g><text x="${x}" y="${y+22}" text-anchor="middle" class="lbl">${esc(name)}</text></g>`}
P.story = s => {
  const set=new Set(s.setting||[]), dark=set.has('night')||set.has('storm')||set.has('stars')||set.has('space');
  const out=[defs, `<defs><linearGradient id="sky" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="${dark?'#0b1340':set.has('storm')?'#3b4252':'#8ec5ff'}"/><stop offset="1" stop-color="${dark?'#3a2d6b':'#e0f2ff'}"/></linearGradient></defs>`,
   `<rect width="960" height="540" fill="url(#sky)"/>`];
  if(dark||set.has('stars')) for(let i=0;i<70;i++){const x=hash('x'+i)%960,y=hash('y'+i)%300;out.push(`<circle cx="${x}" cy="${y}" r="${1+hash('r'+i)%3}" fill="#fff" class="twinkle" style="animation-delay:${(i%10)/5}s"/>`)}
  if(dark&&!set.has('storm')) out.push(`<circle cx="820" cy="90" r="40" fill="#f8f3d0"/><circle cx="805" cy="80" r="40" fill="url(#sky)"/>`);
  if(!dark) out.push(`<circle cx="840" cy="90" r="46" fill="#ffd43b" class="breathe"/>`);
  if(set.has('hill')) out.push(`<path d="M0,420 Q300,200 620,400 T960,380 V540 H0Z" fill="${dark?'#243b2f':'#69db7c'}"/>`);
  out.push(`<rect y="430" width="960" height="110" fill="${set.has('sea')?'#1c7ed6':set.has('snow')?'#f1f3f5':dark?'#1d3326':'#51cf66'}"/>`);
  if(set.has('sea')) for(let i=0;i<4;i++) out.push(`<path class="wave" d="M-40,${450+i*22} q40,-14 80,0 t80,0 t80,0 t80,0 t80,0 t80,0 t80,0 t80,0 t80,0 t80,0 t80,0 t80,0 t80,0" stroke="#a5d8ff" stroke-width="3" fill="none" style="animation-delay:${i*.4}s"/>`);
  if(set.has('forest')) for(let i=0;i<9;i++){const x=20+i*115+(hash('t'+i)%40),h=140+hash('h'+i)%80;out.push(`<g class="sway" style="animation-delay:${i*.3}s"><rect x="${x-8}" y="${440-h*.35}" width="16" height="${h*.35}" fill="#6b4f3a"/><path d="M${x},${440-h} L${x+48},${440-h*.3} L${x-48},${440-h*.3}Z" fill="${dark?'#1f4d36':'#2f9e44'}"/></g>`)}
  if(set.has('village')) for(let i=0;i<3;i++){const x=600+i*110;out.push(`<g><rect x="${x}" y="370" width="80" height="62" fill="#e9d8a6"/><path d="M${x-8},372 L${x+40},330 L${x+88},372Z" fill="#c0392b"/><rect x="${x+28}" y="392" width="22" height="40" fill="#6b4f3a"/>${dark?`<rect x="${x+8}" y="384" width="14" height="14" fill="#ffd43b" class="twinkle"/>`:''}</g>`)}
  if(set.has('storm')||set.has('rain')){out.push(`<rect width="960" height="540" fill="#fff" class="flash"/>`);out.push('<g>');for(let i=0;i<90;i++){const x=hash('rx'+i)%1000,y=hash('ry'+i)%500-80;out.push(`<line x1="${x}" y1="${y}" x2="${x-8}" y2="${y+22}" stroke="#a5d8ff" stroke-width="2" class="rain" style="animation-delay:${(i%14)/20}s"/>`)}out.push('</g>')}
  const ch=s.characters||[];
  ch.forEach((c,i)=>{const x=220+i*230,y=470, glow=Object.entries(s.effects||{}).some(([w,e])=>e==='glow');
    out.push(c.kind==='creature'?creature(x,y,col(c.name,55),c.name,.3+i*.4,glow):person(x,y,col(c.name,48),c.name,.3+i*.4))});
  const q=(s.sentences||[]).join(' ').match(/["“]([^"”]{3,120})["”]/);
  if(q){out.push(`<g class="pop" style="animation-delay:2.2s"><rect x="300" y="60" width="420" height="${30+wrap(q[1],40).length*20}" rx="18" fill="#fff" stroke="#222"/>${label(510,80+wrap(q[1],40).length*10,q[1],'small',40).replaceAll('class="small"','class="small" style="fill:#222"')}</g>`)}
  return out.join('');
};
P.trace = s => {
  const t=s.trace, out=[defs], sc=Math.min(900/t.width,480/t.height), ox=(960-t.width*sc)/2, oy=(540-t.height*sc)/2+10;
  out.push(`<image href="${t.image}" x="${ox}" y="${oy}" width="${t.width*sc}" height="${t.height*sc}" opacity="0"><animate attributeName="opacity" from="0" to="1" begin="${Math.min(9,t.strokes.length*.012)+.5}s" dur="2s" fill="freeze"/></image>`);
  out.push(`<g fill="none" stroke="${PLAN.accent}" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" transform="translate(${ox},${oy}) scale(${sc})">`);
  t.strokes.forEach((st,i)=>{const d='M'+st.map(p=>p.join(',')).join(' L');out.push(`<path d="${d}" class="draw" style="--len:${st.length*3};animation-delay:${i*.012}s;animation-duration:.6s"/>`)});
  out.push('</g>'); return out.join('');
};

// ── 3D / hologram engine (no libraries) ─────────────────────────────────────
function graph3d(s){
  let names=[], edges=[];
  if(s.type==='process'){names=[...s.path];for(let i=0;i<names.length-1;i++)edges.push([i,i+1]);(s.branches||[]).forEach(b=>b.forEach((x,j)=>{if(!names.includes(x))names.push(x);if(j)edges.push([names.indexOf(b[j-1]),names.indexOf(x)])}))}
  else if(s.type==='structure'){names=[s.whole,...(s.parts||[])];for(let i=1;i<names.length;i++)edges.push([0,i])}
  else if(s.type==='story'){names=(s.characters||[]).map(c=>c.name).concat(s.setting||[]);for(let i=1;i<names.length;i++)edges.push([0,i])}
  else if(s.type==='timeline'){names=(s.events||[]).map(e=>e.year);for(let i=0;i<names.length-1;i++)edges.push([i,i+1])}
  else if(s.type==='comparison'){names=[s.left,s.right,...(s.terms||[])];edges.push([0,1]);for(let i=2;i<names.length;i++)edges.push([i%2,i])}
  else {names=[s.center||s.title||'idea',...(s.terms||s.steps||s.keyphrases||[])];for(let i=1;i<names.length;i++)edges.push([0,i])}
  names=names.filter(Boolean).slice(0,16);edges=edges.filter(([a,b])=>a>=0&&b>=0&&a<names.length&&b<names.length);
  const n=names.length, pts=names.map((nm,i)=>{
    if(s.type==='process'||s.type==='timeline'){const a=i*0.9;return [Math.cos(a)*1.4,(i-(n-1)/2)*0.55,Math.sin(a)*1.4]}
    if(i===0&&s.type!=='comparison')return [0,0,0];
    const k=i+.5, ph=Math.acos(1-2*k/n), th=Math.PI*(1+Math.sqrt(5))*k;return [Math.cos(th)*Math.sin(ph)*1.8,Math.cos(ph)*1.5,Math.sin(th)*Math.sin(ph)*1.8]});
  const detail=names.map(nm=>((s.sentences||[]).find(t=>t.toLowerCase().includes(String(nm).toLowerCase()))||''));
  return {names,edges,pts,detail};
}
let G=null, yaw=0.6, pitch=0.25, zoom=1, drag=null, t3=0;
function draw3d(){
  if(!mode3d)return; const dpr=window.devicePixelRatio||1, W=cv.clientWidth, H=cv.clientHeight;
  if(cv.width!==W*dpr){cv.width=W*dpr;cv.height=H*dpr}
  const c=cv.getContext('2d'); c.setTransform(dpr,0,0,dpr,0,0); c.fillStyle='#000'; c.fillRect(0,0,W,H);
  if(!drag) yaw+=0.004; t3+=0.016;
  const views = holo ? [[0,0],[Math.PI/2,1],[Math.PI,2],[3*Math.PI/2,3]] : [[0,-1]];
  for(const [off,slot] of views){
    c.save();
    let cx=W/2, cy=H/2, scale=Math.min(W,H)*0.22*zoom;
    if(holo){scale=Math.min(W,H)*0.075*zoom; c.translate(W/2,H/2); c.rotate(slot*Math.PI/2); c.translate(0,-Math.min(W,H)*0.3); cx=0; cy=0;}
    const cyw=Math.cos(yaw+off), syw=Math.sin(yaw+off), cp=Math.cos(pitch), sp=Math.sin(pitch);
    const proj=G.pts.map(([x,y,z])=>{const X=x*cyw-z*syw, Z0=x*syw+z*cyw, Y=y*cp-Z0*sp, Z=y*sp+Z0*cp, f=3.2/(3.2+Z);return [cx+X*scale*f, cy+Y*scale*f, f, Z]});
    c.lineWidth=2;
    G.edges.forEach(([a,b],i)=>{const p=proj[a],q=proj[b];c.strokeStyle='rgba(150,170,220,.55)';c.beginPath();c.moveTo(p[0],p[1]);c.lineTo(q[0],q[1]);c.stroke();
      const u=(t3*0.35+i*0.17)%1;c.fillStyle=PLAN.accent;c.beginPath();c.arc(p[0]+(q[0]-p[0])*u,p[1]+(q[1]-p[1])*u,4*p[2],0,7);c.fill()});
    const order=proj.map((p,i)=>i).sort((a,b)=>proj[b][3]-proj[a][3]);
    for(const i of order){const [x,y,f]=proj[i], r=(i===0?26:18)*f*Math.sqrt(zoom), h=hue(G.names[i]);
      const g=c.createRadialGradient(x-r*.35,y-r*.35,r*.1,x,y,r);g.addColorStop(0,`hsl(${h} 90% 80%)`);g.addColorStop(1,`hsl(${h} 70% 38%)`);
      c.fillStyle=g;c.beginPath();c.arc(x,y,r,0,7);c.fill();
      c.fillStyle='#fff';c.font=`600 ${Math.max(11,13*f*Math.min(zoom,1.6))}px system-ui`;c.textAlign='center';c.fillText(G.names[i],x,y-r-6);
      if(zoom>1.6&&G.detail[i]){c.fillStyle='rgba(220,230,255,.85)';c.font=`${Math.max(9,10*f*zoom/1.6)}px system-ui`;
        wrap(G.detail[i],46).forEach((l,k)=>c.fillText(l,x,y+r+14+k*13))}}
    c.restore();
  }
  requestAnimationFrame(draw3d);
}
cv.addEventListener('pointerdown',e=>{drag=[e.clientX,e.clientY];cv.setPointerCapture(e.pointerId)});
cv.addEventListener('pointermove',e=>{if(!drag)return;yaw+=(e.clientX-drag[0])*0.01;pitch=Math.max(-1.3,Math.min(1.3,pitch+(e.clientY-drag[1])*0.01));drag=[e.clientX,e.clientY]});
cv.addEventListener('pointerup',()=>drag=null);
cv.addEventListener('wheel',e=>{e.preventDefault();zoom=Math.max(.4,Math.min(4,zoom*(e.deltaY<0?1.12:0.89)))},{passive:false});
let pinch=null;cv.addEventListener('touchmove',e=>{if(e.touches.length===2){const d=Math.hypot(e.touches[0].clientX-e.touches[1].clientX,e.touches[0].clientY-e.touches[1].clientY);if(pinch)zoom=Math.max(.4,Math.min(4,zoom*d/pinch));pinch=d}},{passive:true});
cv.addEventListener('touchend',()=>pinch=null);

// ── narration & paging ──────────────────────────────────────────────────────
const FX = {}; for(const [name,words] of Object.entries((PLAN.lexicon||{}).effects||{})) words.forEach(w=>FX[w]=name);
function captionHTML(s){return (s.sentences||[]).map((t,i)=>`<span class="s" data-i="${i}">`+t.split(/(\s+)/).map(w=>{const k=w.toLowerCase().replace(/[^a-z']/g,'');const fx=(s.effects||{})[k]||FX[k];return /\s+/.test(w)?w:`<span class="w${fx?' fx-'+fx:''}">${esc(w)}</span>`}).join('')+'</span>').join(' ')}
function highlight(i){
  document.querySelectorAll('.caption .s').forEach(el=>el.classList.toggle('on',+el.dataset.i===i));
  const sent=((PLAN.scenes[page].sentences||[])[i]||'').toLowerCase();
  document.querySelectorAll('#svg .nd').forEach(g=>g.classList.toggle('lit',sent.includes(g.dataset.k.toLowerCase().split(' ')[0])));
}
function speak(i){
  clearTimeout(timer); const sents=PLAN.scenes[page].sentences||[];
  if(i>=sents.length){ if(playing) timer=setTimeout(()=>go(page+1,true), 2500); return; }
  sentIdx=i; highlight(i);
  const next=()=>{ if(playing) speak(i+1) };
  if(voice && 'speechSynthesis' in window){
    speechSynthesis.cancel(); const u=new SpeechSynthesisUtterance(sents[i]); u.rate=PLAN.grade&&+PLAN.grade<=4?0.85:0.95;
    const words=[...document.querySelectorAll(`.caption .s[data-i="${i}"] .w`)];
    u.onboundary=e=>{let pos=0;for(const w of words){w.classList.toggle('say',e.charIndex>=pos&&e.charIndex<pos+w.textContent.length+1);pos+=w.textContent.length+1}};
    u.onend=()=>{words.forEach(w=>w.classList.remove('say'));next()}; u.onerror=()=>{timer=setTimeout(next, 280*sents[i].split(' ').length)};
    speechSynthesis.speak(u);
  } else timer=setTimeout(next, 300*sents[i].split(' ').length+600);
}
function go(p, auto){
  if(p<0||p>=PLAN.scenes.length){ if(auto){playing=false;syncButtons()} return; }
  page=p; const s=PLAN.scenes[p];
  $('stitle').textContent=s.title||''; $('pageno').textContent=`${p+1} / ${PLAN.scenes.length} · ${s.type}`;
  svg.innerHTML=(P[s.type]||P.concept)(s); $('caption').innerHTML=captionHTML(s);
  G=graph3d(s); if(playing) speak(0); else highlight(0);
}
function syncButtons(){$('play').textContent=playing?'❚❚ Pause':'▶ Play';$('play').classList.toggle('on',playing);$('b3d').classList.toggle('on',mode3d);$('bholo').classList.toggle('on',holo);$('bvoice').classList.toggle('on',voice)}
$('prev').onclick=()=>go(page-1); $('next').onclick=()=>go(page+1);
$('play').onclick=()=>{playing=!playing; if(!playing){clearTimeout(timer); if('speechSynthesis' in window) speechSynthesis.cancel()} else speak(sentIdx); syncButtons()};
$('b3d').onclick=()=>{mode3d=!mode3d; stage.classList.toggle('mode3d',mode3d); if(mode3d) requestAnimationFrame(draw3d); syncButtons()};
$('bholo').onclick=()=>{holo=!holo; if(holo&&!mode3d){mode3d=true;stage.classList.add('mode3d');requestAnimationFrame(draw3d)} syncButtons()};
$('bvoice').onclick=()=>{voice=!voice; if(!voice&&'speechSynthesis' in window) speechSynthesis.cancel(); syncButtons()};
document.addEventListener('keydown',e=>{if(e.key==='ArrowRight')go(page+1);if(e.key==='ArrowLeft')go(page-1);if(e.key===' '){e.preventDefault();$('play').click()}});
if(holo){mode3d=true;stage.classList.add('mode3d');requestAnimationFrame(draw3d)}
syncButtons(); go(0);
</script></body></html>"""
