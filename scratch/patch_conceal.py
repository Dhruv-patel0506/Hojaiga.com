import re
p = r"D:\new_automation\All codes\core_organs\background_window.py"
s = open(p, encoding="utf-8").read()
BS = chr(92)


def rep(old, new, label):
    global s
    if old not in s:
        print("MISSING:", label)
        raise SystemExit(1)
    s = s.replace(old, new, 1)
    print("ok:", label)


rep("""        self.moved = 0
        self.hook_hits = 0
        self.refocused = 0
        _ensure_tracker()""", """        self.moved = 0
        self.hook_hits = 0
        self.refocused = 0
        self._concealed: Dict[int, bool] = {}           # popup hwnd -> did WE add WS_EX_LAYERED (so it can be put back)
        _ensure_tracker()""", "init")

rep("""    def run(self) -> None:
        @ctypes.WINFUNCTYPE(ctypes.c_bool, wt.HWND, wt.LPARAM)
        def cb(h, _):""", '''    def _conceal(self, h: int) -> None:
        """A flyout ANIMATES open and its framework re-places it on the screen on every frame, so moving it leaves it visible for the length
        of the animation (measured 130-260 ms). Fully transparent from its first frame it cannot be seen wherever it is, and UI Automation
        and PrintWindow still read it. Dialogs (#32770) are only moved. Everything concealed is put back by _reveal when the session ends."""
        if not CONCEAL_FLYOUTS or h in self._concealed:
            return
        try:
            c = ctypes.create_unicode_buffer(64)
            _u32.GetClassNameW(h, c, 64)
            if c.value == "#32770":
                return
            ex = _u32.GetWindowLongW(h, -20)
            added = not (ex & 0x00080000)
            if added:
                _u32.SetWindowLongW(h, -20, ex | 0x00080000)                   # WS_EX_LAYERED
            _u32.SetLayeredWindowAttributes(h, 0, 0, 2)                         # LWA_ALPHA, alpha 0
            self._concealed[h] = added
        except Exception:
            pass

    def _reveal(self) -> None:
        for h, added in list(self._concealed.items()):
            try:
                if _u32.IsWindow(h):
                    _u32.SetLayeredWindowAttributes(h, 0, 255, 2)
                    if added:
                        _u32.SetWindowLongW(h, -20, _u32.GetWindowLongW(h, -20) & ~0x00080000)
            except Exception:
                pass
        self._concealed.clear()

    def run(self) -> None:
        @ctypes.WINFUNCTYPE(ctypes.c_bool, wt.HWND, wt.LPARAM)
        def cb(h, _):''', "helpers")

rep("""                    if _on_real_screen(_rect(h)):
                        _u32.SetWindowPos(h, 0, PARK_X, PARK_Y, 0, 0, SWP_NOSIZE | SWP_NOZORDER | SWP_NOACTIVATE)
                        self.moved += 1
            except Exception:
                pass
            return True""", """                    if _on_real_screen(_rect(h)):
                        self._conceal(h)
                        _u32.SetWindowPos(h, 0, PARK_X, PARK_Y, 0, 0, SWP_NOSIZE | SWP_NOZORDER | SWP_NOACTIVATE)
                        self.moved += 1
            except Exception:
                pass
            return True""", "sweep")

rep("""                    if _on_real_screen(_rect(h)):
                        _u32.SetWindowPos(h, 0, PARK_X, PARK_Y, 0, 0, SWP_NOSIZE | SWP_NOZORDER | SWP_NOACTIVATE)
                        self.moved += 1
                        self.hook_hits += 1""", """                    if _on_real_screen(_rect(h)):
                        self._conceal(h)
                        _u32.SetWindowPos(h, 0, PARK_X, PARK_Y, 0, 0, SWP_NOSIZE | SWP_NOZORDER | SWP_NOACTIVATE)
                        self.moved += 1
                        self.hook_hits += 1""", "hook")

rep("""                user32.UnhookWinEvent(self._hook)
        except Exception:
            pass
""", """                user32.UnhookWinEvent(self._hook)
        except Exception:
            pass
        self._reveal()                                    # nothing stays transparent once the session is over
""", "reveal")

rep("""class _PopupGuard(threading.Thread):""", """CONCEAL_FLYOUTS = os.environ.get("HOJAIGA_CONCEAL_FLYOUTS", "1") != "0"


class _PopupGuard(threading.Thread):""", "flag")
open(p, "w", encoding="utf-8").write(s)
print("written")
