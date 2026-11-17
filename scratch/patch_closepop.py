import ast, io
P = "D:/new_automation/All codes/core_organs/professor/effectors.py"
s = io.open(P, "r", encoding="utf-8").read()
old = '''            _u.PostMessageW(w, WM_KEYDOWN, VK_ESCAPE, 0)
            _u.PostMessageW(w, WM_KEYUP, VK_ESCAPE, 0)
            time.sleep(0.25)
            if hin.is_alive(w):
                _u.PostMessageW(w, WM_CLOSE, 0, 0)
                time.sleep(0.25)
            n += 0 if hin.is_alive(w) else 1'''
new = '''            _u.PostMessageW(w, WM_KEYDOWN, VK_ESCAPE, 0)
            _u.PostMessageW(w, WM_KEYUP, VK_ESCAPE, 0)
            time.sleep(0.25)
            try:
                cls = hin._class_name(w)
            except Exception:
                cls = ""
            # a framework's own pop-up host (WinUI PopupWindowSiteBridge, the XAML core window ...) is NEVER destroyed: closing it breaks every later flyout of the application (measured on Notepad).
            # It is dismissed by Escape alone; only real dialogs / top-level windows get WM_CLOSE.
            if hin.is_alive(w) and not re.search(r"(popupwindowsitebridge|sitebridge|corewindow|xamlpopup|xaml_|popup|#32768|tooltip)", cls, re.I):
                _u.PostMessageW(w, WM_CLOSE, 0, 0)
                time.sleep(0.25)
            n += 0 if hin.is_alive(w) else 1'''
assert old in s
s = s.replace(old, new, 1)
ast.parse(s)
io.open(P, "w", encoding="utf-8", newline="\n").write(s)
print("ok")
