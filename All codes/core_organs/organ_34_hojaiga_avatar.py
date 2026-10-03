"""Hojaiga Organ 34 — non-intrusive desktop edge avatar.

The avatar is intentionally a separate UI organ.  It can be imported by the
CrewAI engine without importing the teaching engine, while the Qt process binds
it to the active Hojaiga overlay at startup.
"""
from __future__ import annotations

import os
import random
import time
import weakref
from typing import Optional

from PyQt5.QtCore import Qt, QPointF, QRectF, QTimer, pyqtSignal
from PyQt5.QtGui import QColor, QPainter, QPainterPath, QPen, QPixmap, QRadialGradient
from PyQt5.QtWidgets import QWidget, QApplication

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
AVATAR_PNG = os.path.normpath(os.path.join(_THIS_DIR, "..", "assets", "hojaiga_avatar", "hojaiga_avatar_edge.png"))

_active_avatar: Optional["HojaigaEdgeAvatar"] = None
_last_crewai_activity = {"state": "idle", "detail": "", "at": 0.0}


def notify_crewai_activity(state: str, detail: str = "") -> None:
    """Safe event hook for Organ 01; never creates a GUI from a worker thread."""
    _last_crewai_activity.update({"state": str(state), "detail": str(detail)[:160], "at": time.time()})
    avatar = _active_avatar
    if avatar is not None:
        avatar.activity_changed.emit(str(state))


class HojaigaEdgeAvatar(QWidget):
    """Clickable, screen-edge peeking avatar bound to a Hojaiga overlay."""
    activity_changed = pyqtSignal(str)
    def __init__(self, overlay):
        super().__init__(None)
        self._overlay = weakref.ref(overlay)
        self.activity_changed.connect(self.set_activity)
        self.side = random.choice(("left", "right"))
        self.activity = "idle"
        self.peek_fraction = 0.42
        self.target_fraction = self.peek_fraction
        self._phase = 0.0
        self._transitioning = False
        self._last_relocate = time.monotonic()
        self._relocate_after = random.uniform(8.0, 15.0)
        self._pixmap = QPixmap(AVATAR_PNG)
        self.setFixedSize(182, 220)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        self.setToolTip("Hojaiga — click to open your teaching Void")
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(33)
        self._place_on_edge(initial=True)

    def set_activity(self, state: str) -> None:
        self.activity = str(state).lower()
        self.target_fraction = 0.62 if self.activity in {"thinking", "teaching", "running"} else 0.42
        self.update()

    def _screen_geometry(self):
        screen = QApplication.primaryScreen()
        return screen.availableGeometry() if screen else self.geometry()

    def _update_edge_x(self) -> None:
        """Animate only toward/away from a side edge; never enter screen centre."""
        rect = self._screen_geometry()
        visible = int(self.width() * self.peek_fraction)
        x = rect.left() - (self.width() - visible) if self.side == "left" else rect.right() - visible + 1
        self.move(x, self.y())

    def begin_void_transition(self) -> None:
        """Emerge from the edge, then hand focus to the infinite Void."""
        if self._transitioning:
            return
        self._transitioning = True
        self.activity = "thinking"
        self.target_fraction = 0.92
        self.show()
        self.raise_()
        QTimer.singleShot(420, self._finish_void_transition)

    def _finish_void_transition(self) -> None:
        overlay = self._overlay()
        if overlay is not None:
            overlay.activate_void_from_avatar()
        self.activity = "teaching"
        self.target_fraction = 0.34
        self._transitioning = False
        self._last_relocate = time.monotonic()

    def dock_after_void_minimize(self) -> None:
        """Keep the worker alive, but return the visible tutor to its edge."""
        self.activity = "idle"
        self.target_fraction = 0.42
        self.show()
        self.raise_()
        self._update_edge_x()
    def _place_on_edge(self, initial: bool = False) -> None:
        rect = self._screen_geometry()
        visible = int(self.width() * self.peek_fraction)
        x = rect.left() - (self.width() - visible) if self.side == "left" else rect.right() - visible + 1
        y = random.randint(rect.top() + 90, max(rect.top() + 90, rect.bottom() - self.height() - 90))
        self.move(x, y)
        if not initial:
            self.show()
            self.raise_()

    def _relocate(self) -> None:
        # First tuck away, then reappear from the opposite vertical edge.
        self.hide()
        self.side = "right" if self.side == "left" else "left"
        self.peek_fraction = 0.34
        self.target_fraction = 0.42
        QTimer.singleShot(random.randint(500, 1300), self._place_on_edge)
        self._last_relocate = time.monotonic()
        self._relocate_after = random.uniform(8.0, 15.0)

    def _tick(self) -> None:
        self._phase += 0.11
        if time.monotonic() - self._last_relocate > self._relocate_after and self.activity == "idle":
            self._relocate()
        self.peek_fraction += (self.target_fraction - self.peek_fraction) * 0.08
        self._update_edge_x()
        self.update()

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
            overlay = self._overlay()
            if overlay is not None:
                self.begin_void_transition()
            event.accept()
            return
        super().mousePressEvent(event)

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        body = QRectF(9, 9, self.width() - 18, self.height() - 18)
        pulse = 0.5 + 0.5 * __import__("math").sin(self._phase)
        glow = QRadialGradient(body.center(), body.width() * 0.58)
        glow.setColorAt(0.0, QColor(251, 146, 60, 72 + int(35 * pulse)))
        glow.setColorAt(0.65, QColor(34, 197, 94, 28))
        glow.setColorAt(1.0, QColor(0, 0, 0, 0))
        painter.setPen(Qt.NoPen)
        painter.setBrush(glow)
        painter.drawEllipse(body.adjusted(-8, -8, 8, 8))
        clip = QPainterPath()
        clip.addEllipse(body)
        painter.save()
        painter.setClipPath(clip)
        if not self._pixmap.isNull():
            painter.drawPixmap(body.toRect(), self._pixmap)
        else:
            painter.fillPath(clip, QColor(30, 41, 59, 240))
        painter.restore()
        border = QColor(251, 146, 60, 230) if self.activity in {"thinking", "running"} else QColor(74, 222, 128, 210)
        painter.setBrush(Qt.NoBrush)
        painter.setPen(QPen(border, 2.2))
        painter.drawEllipse(body)
        # A small logo-colored status bead remains visible even while peeking.
        dot = QPointF(body.right() - 18, body.bottom() - 20)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(249, 115, 22) if self.activity != "idle" else QColor(74, 222, 128))
        painter.drawEllipse(dot, 6, 6)


def spawn_edge_avatar(overlay) -> HojaigaEdgeAvatar:
    global _active_avatar
    if _active_avatar is None:
        _active_avatar = HojaigaEdgeAvatar(overlay)
    _active_avatar.show()
    _active_avatar.raise_()
    return _active_avatar