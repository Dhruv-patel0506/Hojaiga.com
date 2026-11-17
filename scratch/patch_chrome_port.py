import ast
import io

P = "D:/new_automation/All codes/core_organs/professor/apprun.py"
s = io.open(P, "r", encoding="utf-8").read()


def rep(old, new):
    global s
    assert old in s, old[:90]
    s = s.replace(old, new, 1)


rep(r'''        args = [exe, f"--user-data-dir={prep.tmp}", "--no-first-run", "--no-default-browser-check", "--force-renderer-accessibility", "--disable-sync", "--new-window", "about:blank", *spec.args]
        subprocess.Popen(args, startupinfo=si)''', r'''        from .adapters.cdp import free_port
        port = free_port()
        args = [exe, f"--user-data-dir={prep.tmp}", "--no-first-run", "--no-default-browser-check", "--force-renderer-accessibility", "--disable-sync", f"--remote-debugging-port={port}",
                "--remote-allow-origins=*", "--disable-features=CalculateNativeWinOcclusion", "--new-window", "about:blank", *spec.args]
        subprocess.Popen(args, startupinfo=si)''')
rep(r'''        info: Dict[str, Any] = {"launched": bool(hwnd), "hwnd": hwnd, "notes": [], "launch_s": round(time.time() - t0, 2)}''', r'''        info: Dict[str, Any] = {"launched": bool(hwnd), "hwnd": hwnd, "notes": [], "launch_s": round(time.time() - t0, 2), "cdp_port": port}''')
ast.parse(s)
io.open(P, "w", encoding="utf-8", newline="\n").write(s)
print("ok")
