import ast
import io

P = "D:/new_automation/All codes/core_organs/professor/checkpoints.py"
s = io.open(P, "r", encoding="utf-8").read()
old = '''                rep = {"error": f"{type(exc).__name__}: {str(exc)[:200]}", "trace": traceback.format_exc()[-800:], "phases": {}}
                print("ERROR in", sp.key, rep["error"])'''
new = '''                rep = {"error": f"{type(exc).__name__}: {str(exc)[:200]}", "trace": traceback.format_exc()[-800:], "phases": {}}
                print("ERROR in", sp.key, rep["error"])
                try:                                                                # the folder of a crashed application still holds what is known about it
                    os.makedirs(app_dir, exist_ok=True)
                    with open(os.path.join(app_dir, "report.json"), "w", encoding="utf-8") as fh:
                        json.dump(rep, fh, indent=1, ensure_ascii=False)
                    with open(os.path.join(app_dir, "report.html"), "w", encoding="utf-8") as fh:
                        fh.write(f"<!doctype html><meta charset=utf-8><title>{html.escape(sp.key)}</title><h1>{html.escape(sp.key)}: the run stopped</h1><pre>{html.escape(rep['error'] + chr(10) + rep['trace'])}</pre>")
                except Exception:
                    pass'''
assert old in s
s = s.replace(old, new, 1)
ast.parse(s)
io.open(P, "w", encoding="utf-8", newline="\n").write(s)
print("ok")
