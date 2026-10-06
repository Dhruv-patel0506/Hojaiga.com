import sys, os, json, tempfile, uuid, time, ctypes
sys.path[:0] = [r"D:\new_automation", r"D:\new_automation\All codes"]
from core_organs import si_tests_behavior as sb, organ_48_app_behavior_model as bm
u32 = ctypes.windll.user32
db = os.path.join(tempfile.gettempdir(), "hj_d1_" + uuid.uuid4().hex[:6] + ".db")
m = bm.BehaviorModel(db); m.load_pack_dir()
txt, png = [os.path.join(tempfile.gettempdir(), "hj_day_" + uuid.uuid4().hex[:6] + e) for e in (".txt", ".png")]
marker = "daytask-" + uuid.uuid4().hex[:5]
with sb.LiveApp("notepad") as ln, sb.LiveApp("paint") as lp:
    hw = {"notepad": ln.hwnd, "paint": lp.hwnd}
    tasks = [{"id": "T1 write note", "app": "notepad", "task": "write text and save as file", "params": {"text": marker, "path": txt}, "expect": "DONE", "file": txt},
             {"id": "T2 save drawing", "app": "paint", "task": "save the image as file", "params": {"path": png}, "expect": "DONE", "file": png}]
    runner = bm.TemplateRunner(m)
    orig = runner.g.find_window
    runner.g.find_window = lambda hint, _o=orig: hw.get(hint) or _o(hint)
    def verify(task, res):
        f = task.get("file")
        return os.path.exists(f), "exists" if os.path.exists(f) else "missing"
    rep = bm.run_task_list(tasks, model=m, runner=runner, verify_fn=verify)
    print(json.dumps(rep, default=str)[:3000])
    key = bm._app_key("paint")
    cmds = m.commands(key, limit=5000)
    print("paint commands known:", len(cmds), "| with shortcut:", sum(1 for c in cmds if c["shortcut"]), "| ctrl+s:", [(c["name"], c["menu_path"], c["risk"]) for c in cmds if (c["shortcut"] or "").lower().replace(" ", "") in ("ctrl+s",)])
    print("crawled set:", getattr(runner, "ladder", None) and getattr(runner.ladder, "_crawled", None))
for f in (txt, png):
    try: os.remove(f)
    except Exception: pass
