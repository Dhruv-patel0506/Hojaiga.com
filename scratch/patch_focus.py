import ast
import io

# ---------------------------------------------------------------- effectors: a focus WATCH thread + final hand-back
P = "D:/new_automation/All codes/core_organs/professor/effectors.py"
s = io.open(P, "r", encoding="utf-8").read()


def rep(old, new):
    global s
    assert old in s, old[:70]
    s = s.replace(old, new, 1)


rep("import functools\nimport re\n", "import contextlib\nimport functools\nimport re\n")
rep('''    def _return_focus(self, was: int) -> None:''', '''    # ---- the focus WATCH: while the Professor is probing / executing, a small thread notices the moment the target's process takes the foreground (toolkits activate themselves
    #      a little AFTER the message, longer under load) and hands it back to the user's window; it never fights the user (input within the last 300 ms = the user did it)
    def _user_busy(self) -> bool:
        try:
            from core_organs.background_window import user_idle_ms
            return user_idle_ms() < 300
        except Exception:
            return False

    def restore_user_focus(self) -> bool:
        """Hand the foreground back to the user's window if the target's process holds it right now. True when it was handed back."""
        try:
            tpid = self._pid(self.hwnd)
            cur = _fg()
            back = self.user_fg
            if not cur or not tpid or self._pid(cur) != tpid or not back or not _fgu.IsWindow(back) or _fgu.IsIconic(back) or self._pid(back) == tpid:
                return False
            from core_organs import headless_input as hin
            hin._hand_back_focus(back)
            self.focus_returns += 1
            self.log.append((time.time(), "focus returned", _fg() == back, f"foreground handed back to {back} (watch)"))
            return True
        except Exception:
            return False

    @contextlib.contextmanager
    def focus_watch(self, interval: float = 0.05):
        if not (self.allowed and self.keep_focus):
            yield self
            return
        stop = threading.Event()
        self._note_user_window(_fg())

        def loop() -> None:
            last = 0.0
            while not stop.wait(interval):
                try:
                    cur = _fg()
                    if cur and self._pid(cur) == self._pid(self.hwnd):
                        if time.time() - last > 0.2 and not self._user_busy():
                            self.restore_user_focus()
                            last = time.time()
                    else:
                        self._note_user_window(cur)
                except Exception:
                    pass

        th = threading.Thread(target=loop, name="effector-focus-watch", daemon=True)
        th.start()
        try:
            yield self
        finally:
            stop.set()
            th.join(1.0)
            time.sleep(0.15)
            self.restore_user_focus()

    def _return_focus(self, was: int) -> None:''')
ast.parse(s)
io.open(P, "w", encoding="utf-8", newline="\n").write(s)

# ---------------------------------------------------------------- probe: run under the focus watch; mask the caption strip in pixel comparisons
P = "D:/new_automation/All codes/core_organs/professor/probe.py"
s = io.open(P, "r", encoding="utf-8").read()
rep('''    if a.image is not None and b.image is not None and a.image.size == b.image.size:
        fr = changed_fraction(a.image, b.image, cell=8, thresh=10.0)
        if fr > pixel_tol:
            out.append(f"pixels {fr:.4f} > {pixel_tol}")
    return out''', '''    if a.image is not None and b.image is not None and a.image.size == b.image.size:
        fr = changed_fraction(_below_caption(a.image), _below_caption(b.image), cell=8, thresh=10.0)
        if fr > pixel_tol:
            out.append(f"pixels {fr:.4f} > {pixel_tol}")
    return out''')
rep('''    if a.image is not None and b.image is not None and a.image.size == b.image.size:
        d.pixel_fraction = round(changed_fraction(a.image, b.image, cell=8, thresh=10.0), 5)
        d.pixel_boxes = [bx.to_list() for bx in changed_boxes(a.image, b.image, cell=8, thresh=10.0)[:8]]
    return d''', '''    if a.image is not None and b.image is not None and a.image.size == b.image.size:
        ia, ib = _below_caption(a.image), _below_caption(b.image)
        d.pixel_fraction = round(changed_fraction(ia, ib, cell=8, thresh=10.0), 5)
        off = a.image.height - ia.height
        d.pixel_boxes = [[bx.x1, bx.y1 + off, bx.x2, bx.y2 + off] for bx in changed_boxes(ia, ib, cell=8, thresh=10.0)[:8]]
    return d''')
rep('''# -------------------------------------------------------------------------------------------------------------- delta
@dataclass
class Delta:''', '''CAPTION_ROWS = 24                       # snapshot pictures are half size: ~48 real pixels = the title bar, whose active / inactive painting flips with focus and says nothing about the app


def _below_caption(img: Image.Image) -> Image.Image:
    if img.height <= CAPTION_ROWS * 3:
        return img
    return img.crop((0, CAPTION_ROWS, img.width, img.height))


# -------------------------------------------------------------------------------------------------------------- delta
@dataclass
class Delta:''')
rep('''        t_start = time.time()
        rep = ProbeReport(dry_run=not self.fx.allowed)''', '''        t_start = time.time()
        with self.fx.focus_watch():
            return self._run(hyps, t_start)

    def _run(self, hyps: Optional[Sequence[Hypothesis]], t_start: float) -> ProbeReport:
        from core_organs import fast_uia
        rep = ProbeReport(dry_run=not self.fx.allowed)''')
ast.parse(s)
io.open(P, "w", encoding="utf-8", newline="\n").write(s)
print("focus watch + caption mask patched")
