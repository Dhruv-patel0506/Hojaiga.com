p = r"D:\new_automation\All codes\core_organs\background_window.py"
s = open(p, encoding="utf-8").read()


def rep(old, new, label):
    global s
    if old not in s:
        print("MISSING:", label)
        raise SystemExit(1)
    s = s.replace(old, new, 1)
    print("ok:", label)


# 1. idle helper + policy constant
rep('''CONCEAL_FLYOUTS = os.environ.get("HOJAIGA_CONCEAL_FLYOUTS", "1") != "0"''',
    '''FOCUS_IDLE_MS = int(os.environ.get("HOJAIGA_FOCUS_IDLE_MS", "1500"))     # the user counts as PRESENT if they touched the keyboard / mouse this recently


def user_idle_ms() -> int:
    """Milliseconds since the last REAL input event (GetLastInputInfo): a read-only question, nothing is sent."""
    try:
        class _LII(ctypes.Structure):
            _fields_ = [("cbSize", ctypes.c_uint), ("dwTime", ctypes.c_uint)]
        li = _LII()
        li.cbSize = ctypes.sizeof(_LII)
        if ctypes.windll.user32.GetLastInputInfo(ctypes.byref(li)):
            return int((ctypes.windll.kernel32.GetTickCount() - li.dwTime) & 0xFFFFFFFF)
    except Exception:
        pass
    return 0                                                  # unknown: assume the user IS there (the safe answer)


CONCEAL_FLYOUTS = os.environ.get("HOJAIGA_CONCEAL_FLYOUTS", "1") != "0"''', "idle helper")

# 2. the hold-focus decision
rep('''        ours = fg == self.hwnd or holds_app_focus(fg, self.hwnd, self.pid)
        if ours:
            tgt = self.user_fg or _last_user_fg''', '''        ours = fg == self.hwnd or holds_app_focus(fg, self.hwnd, self.pid)
        if ours and user_idle_ms() > FOCUS_IDLE_MS:
            # Nobody is at the keyboard: a WinUI app that takes the foreground when its flyout opens misdirects no keystroke, and giving the foreground
            # back deactivates the window, which dismisses the very menu being read (measured: a Paint menu crawl returned 13-28 commands instead of 41,
            # File came back EMPTY; with the hand-back off: 41 of 41, four runs of four, and 30% faster). The hand-back is immediate the moment a person
            # touches the keyboard or mouse, and always happens when the session ends.
            self.fg_deferred += 1
            return
        if ours:
            tgt = self.user_fg or _last_user_fg''', "defer when idle")

rep('''        self._concealed: Dict[int, bool] = {}''', '''        self.fg_deferred = 0
        self._concealed: Dict[int, bool] = {}''', "counter")

# 3. restore focus at session end
rep('''    def halt(self) -> None:
        self._halt.set()


class _Parked:''', '''    def restore_focus(self) -> None:
        """Session end: if the app still holds the foreground (the idle policy let it), give it back to what the user had."""
        fg = _u32.GetForegroundWindow()
        if not fg or not (fg == self.hwnd or holds_app_focus(fg, self.hwnd, self.pid)):
            return
        tgt = self.user_fg or _last_user_fg
        if not (tgt and _u32.IsWindow(tgt) and not _u32.IsIconic(tgt) and _pid(tgt) != self.pid):
            tgt = next_user_window(self.pid) or int(_u32.FindWindowW("Shell_TrayWnd", None) or 0)
        if tgt:
            self._give_focus(tgt, fg)

    def halt(self) -> None:
        self._halt.set()


class _Parked:''', "restore_focus")

rep('''        if p.guard is not None:
            time.sleep(0.05)
            p.guard.halt()
            p.guard.join(timeout=1.0)
        return True
    except Exception:
        return False''', '''        if p.guard is not None:
            try:
                p.guard.restore_focus()
            except Exception:
                pass
            time.sleep(0.05)
            p.guard.halt()
            p.guard.join(timeout=1.0)
        return True
    except Exception:
        return False''', "exit restore")
open(p, "w", encoding="utf-8").write(s)
print("chr8:", s.count(chr(8)))
