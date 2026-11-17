import ast
import io

P = "D:/new_automation/All codes/core_organs/professor/overlay.py"
s = io.open(P, "r", encoding="utf-8").read()


def rep(old, new):
    global s
    assert old in s, old[:90]
    s = s.replace(old, new, 1)


rep("""        self.thinking = False
        self.landed_at: Optional[float] = None
        self.hold_until = 0.0

    def fly_to(self, x: float, y: float) -> None:""", """        self.thinking = False
        self.landed_at: Optional[float] = None
        self.hold_until = 0.0
        self.route: Optional[Tuple[Any, float]] = None             # a stitched multi-target trajectory being played: (pointing.Trajectory, start time)

    def fly_route(self, traj: Any) -> None:
        self.route = (traj, time.perf_counter())
        self.flight = None
        self.landed_at = None
        self.thinking = False

    def fly_to(self, x: float, y: float) -> None:""")
rep("""    def flying(self) -> bool:
        return self.flight is not None""", """    def flying(self) -> bool:
        return self.flight is not None or self.route is not None""")
rep("""        scale_idx = 1.0
        if self.flight is not None:
            p0, p1, t0, dur = self.flight""", """        scale_idx = 1.0
        if self.route is not None:
            traj, rt0 = self.route
            rt = now - rt0
            if rt >= traj.duration:
                self.pos = traj.points[-1]
                self.route = None
                self.landed_at = now
            else:
                self.pos = traj.at(rt)
                vx, vy = traj.velocity(rt)
                scale_idx = 1.3 if (vx * vx + vy * vy) ** 0.5 > 900 else (1.15 if (vx * vx + vy * vy) ** 0.5 > 400 else 1.0)
        elif self.flight is not None:
            p0, p1, t0, dur = self.flight""")
rep("""    def point_xy(self, x: float, y: float, label: str = "") -> None:
        self._idle.clear()
        self._q.put(("circle", (x, y, label)))
""", """    def point_xy(self, x: float, y: float, label: str = "") -> None:
        self._idle.clear()
        self._q.put(("circle", (x, y, label)))

    def glide(self, points: Sequence[Tuple[float, float]], widths: Optional[Sequence[float]] = None) -> float:
        \"\"\"Move the (virtual, overlay-only) pointer through several targets as ONE continuous Fitts's-law trajectory. The real mouse is never touched. Returns the planned duration (s).\"\"\"
        start = self.cursor.pos if self.cursor is not None else cursor_pos()
        traj = pointing.stitch([start] + [tuple(p) for p in points], [0.0] + list(widths or []))
        self._idle.clear()
        self._q.put(("glide", ([tuple(p) for p in points], list(widths or []))))
        return traj.duration
""")
rep("""        elif cmd == "circle":
            x, y, label = a""", """        elif cmd == "glide":
            pts, ws = a
            if self.cursor is None:
                self.cursor = CursorActor(cursor_pos())
                self.actors.append(self.cursor)
            self.cursor.fly_route(pointing.stitch([self.cursor.pos] + pts, [0.0] + ws))
        elif cmd == "circle":
            x, y, label = a""")
rep("""    def point_xy(self, x: float, y: float, label: str = "") -> None:
        self.log.append(("point_xy", {"x": x, "y": y, "label": label}))""", """    def glide(self, points: Sequence[Tuple[float, float]], widths: Optional[Sequence[float]] = None) -> float:
        start = self._pos if getattr(self, "_pos", None) else (0.0, 0.0)
        traj = pointing.stitch([start] + [tuple(p) for p in points], [0.0] + list(widths or []))
        self.log.append(("glide", {"points": [list(p) for p in points], "widths": list(widths or []), "seconds": round(traj.duration, 3), "arrivals": [round(a, 3) for a in traj.arrival[1:]]}))
        if points:
            self._pos = tuple(points[-1])
            self.scene = [{"type": "cursor", "x": points[-1][0], "y": points[-1][1]}]
        return traj.duration

    def point_xy(self, x: float, y: float, label: str = "") -> None:
        self.log.append(("point_xy", {"x": x, "y": y, "label": label}))""")
ast.parse(s)
io.open(P, "w", encoding="utf-8", newline="\n").write(s)
print("glide added")
