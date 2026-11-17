import ast
import io

R = "D:/new_automation/All codes/core_organs/professor/"


def patch(path, pairs):
    s = io.open(path, "r", encoding="utf-8").read()
    for old, new in pairs:
        assert old in s, old[:100]
        s = s.replace(old, new, 1)
    ast.parse(s)
    io.open(path, "w", encoding="utf-8", newline="\n").write(s)


patch(R + "reveal.py", [
    ('''            time.sleep(0.55)
            s = snapshot(self.hwnd)
            why = diff_state(s0, s, tol)
            if not why:
                return " + ".join(tried), True, ""''', '''            end = time.time() + 3.5                                                  # a page that is left re-lays itself out: judge it only after it has had the time to settle
            while True:
                time.sleep(0.5)
                s = snapshot(self.hwnd)
                why = diff_state(s0, s, tol)
                if not why or time.time() > end:
                    break
            if not why:
                return " + ".join(tried), True, ""'''),
])
patch(R + "vision_server.py", [
    ('''    deadline = t0 + wait_s
    while time.time() < deadline:
        if _health().get("up"):
            return {"ok": True, "started": bool(started), "seconds": round(time.time() - t0, 1), **status()}''', '''    deadline = t0 + wait_s
    stuck_after = t0 + 90.0 if (procs and not started) else None                     # a server that is loading answers within about a minute; a process that does not answer is stuck
    while time.time() < deadline:
        if _health().get("up"):
            return {"ok": True, "started": bool(started), "seconds": round(time.time() - t0, 1), **status()}
        if stuck_after is not None and not started and time.time() > stuck_after:
            stop()
            time.sleep(2.0)
            started = start(profile, ngl)
            if not started.get("ok"):
                return {"ok": False, "started": False, **started}'''),
])
print("ok")
