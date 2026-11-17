p = r"D:\new_automation\All codes\core_organs\hojaiga_run.py"
s = open(p, encoding="utf-8").read()
old = "and not TI.detect_apps(tk, TI.installed_app_names()):"
assert old in s
new = "and not [a for a, _p in TI.detect_apps(tk, TI.installed_app_names()) if a.lower() in tk.lower()]:   # the intake's fuzzy match took 'click' for the app 'Click to Do': an app counts only when its whole name is in the words"
s = s.replace(old, new, 1)
open(p, "w", encoding="utf-8").write(s)
import ast
ast.parse(s)

t = r"D:\new_automation\All codes\core_organs\si_tests_mind.py"
u = open(t, encoding="utf-8").read()
old = 'c["a_drawing_program_is_live"] = sf("Inkscape", exe="x.exe") == "live"'
assert old in u
u = u.replace(old, 'c["a_drawing_program_is_live"] = sf("Inkscape", exe="x.exe", sources=["start_menu"]) == "live"', 1)
old = 'c["a_messenger_is_static_only"] = sf("WhatsApp", exe="x.exe") == "static_only"'
assert old in u
open(t, "w", encoding="utf-8").write(u)
print("ok")
