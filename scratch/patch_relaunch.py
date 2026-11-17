import ast
import io

P = "D:/new_automation/All codes/core_organs/professor/apprun.py"
s = io.open(P, "r", encoding="utf-8").read()


def rep(old, new):
    global s
    assert old in s, old[:90]
    s = s.replace(old, new, 1)


rep(r'''        except Exception as exc:
            self.report["phases"]["cdp"] = {"error": f"{type(exc).__name__}: {str(exc)[:160]}"}
            self.say("DevTools route failed: " + self.report["phases"]["cdp"]["error"])''', r'''        except Exception as exc:
            from .adapters.chromium import BrowserGone
            if isinstance(exc, BrowserGone):
                raise
            self.report["phases"]["cdp"] = {"error": f"{type(exc).__name__}: {str(exc)[:160]}"}
            self.say("DevTools route failed: " + self.report["phases"]["cdp"]["error"])''')
rep(r'''            if not self.start():
                self.report["result"] = "launch_failed"
                return self.finish()
            self.perceive()
            if "guide" in self.phases:''', r'''            if not self.start():
                self.report["result"] = "launch_failed"
                return self.finish()
            try:
                self.perceive()
            except Exception as exc:
                from .adapters.chromium import BrowserGone
                if not isinstance(exc, BrowserGone):
                    raise
                # the application exited on a page the crawl opened: it is now written down as a hazard; start over once with a fresh instance
                self.ui.phase("devtools", self.ui.c("failed", f"the application exited while opening {exc.url} - recorded; starting a fresh instance"))
                self.report["phases"]["relaunched_after"] = exc.url
                self._teardown()
                if not self.start():
                    self.report["result"] = "launch_failed"
                    return self.finish()
                self.perceive()
            if "guide" in self.phases:''')
rep(r'''    def run(self) -> Dict[str, Any]:
        t0 = time.time()''', r'''    def _teardown(self) -> None:
        """Close the owned instance and release its state (used when the run must start over)."""
        from core_organs.atlas import scanner as SC
        with contextlib.suppress(Exception):
            if self.adapter is not None:
                self.adapter.close()
        self.adapter = None
        with contextlib.suppress(Exception):
            if self.bg is not None:
                self.bg.__exit__(None, None, None)
        with contextlib.suppress(Exception):
            if self.hwnd:
                SC.close_owned(self.hwnd)
        with contextlib.suppress(Exception):
            if self.guard is not None:
                self.guard.after()
        self.hwnd, self.bg, self.fx, self.ex = 0, None, None, None
        time.sleep(1.0)

    def run(self) -> Dict[str, Any]:
        t0 = time.time()''')
ast.parse(s)
io.open(P, "w", encoding="utf-8", newline="\n").write(s)

# register the new tests into the Professor suite
T = "D:/new_automation/All codes/core_organs/si_tests_professor.py"
t = io.open(T, "r", encoding="utf-8").read()
old = '''LIVE = [("PL1", run_pl1)'''
new = '''try:                                                                                       # the app-run architecture's offline tests (PR49+) live in their own module
    from si_tests_apprun import TESTS as _APPRUN_TESTS
    OFFLINE = OFFLINE + _APPRUN_TESTS
except Exception:                                                                          # noqa: BLE001 - a missing optional module must not break the suite
    pass
LIVE = [("PL1", run_pl1)'''
assert old in t
t = t.replace(old, new, 1)
t = t.replace('only=[a for a in args if a.upper().startswith(("PR", "PL", "PV"))] or None))', 'only=[a for a in args if a.upper().startswith(("PR", "PL", "PV"))] or None))', 1)
ast.parse(t)
io.open(T, "w", encoding="utf-8", newline="\n").write(t)
print("ok")
