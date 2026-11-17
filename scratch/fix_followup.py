p = r"D:\new_automation\All codes\core_organs\hojaiga_run.py"
s = open(p, encoding="utf-8").read()
old = '''        kind = classify(tk, dom, rag, names)
        if kind == "web" and routed and routed[-1]["kind"] == "web":'''
assert old in s
new = '''        kind = classify(tk, dom, rag, names)
        if kind != "web" and routed and routed[-1]["kind"] == "web" and kind in ("desktop", "question") and _DO.search(tk) and not TI.detect_apps(tk, TI.installed_app_names()):
            from core_organs import web_executor as WE0
            if not WE0.resolve_site(tk, rag, names):
                kind = "web"                                                                           # 'click Features' right after a web step names no app and no site: it is the next step on the same page
        if kind == "web" and routed and routed[-1]["kind"] == "web":'''
s = s.replace(old, new, 1)
open(p, "w", encoding="utf-8").write(s)
import ast
ast.parse(s)
print("ok")
