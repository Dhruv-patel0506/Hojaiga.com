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
