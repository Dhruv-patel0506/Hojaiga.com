import pathlib

p = pathlib.Path(r"D:\new_automation\train_by_category_auto_switch.py")
if p.exists():
    code = p.read_text(encoding="utf-8")
    old_line = 'ultron_cp100 = TRAIN_DIR / "runs" / "hojaiga_4b_ultron_complete" / "checkpoint-100"'
    new_line = 'ultron_cp100 = TRAIN_DIR / "runs" / "hojaiga_4b_ultron_complete" / "checkpoint-800"'
    if old_line in code:
        code = code.replace(old_line, new_line)
        p.write_text(code, encoding="utf-8")
        print("[+] Updated starting adapter to hojaiga_4b_ultron_complete/checkpoint-800 (Loss: 0.005445)!")
