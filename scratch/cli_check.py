import sys, io, contextlib
sys.path[:0] = ["D:/new_automation", "D:/new_automation/All codes", "D:/new_automation/All codes/core_organs"]
import hojaiga_professor as H
from core_organs.atlas.fixture import harness
from core_organs import background_window as bw
from core_organs.atlas import scanner as SC

h = harness.launch(minimized=True)
hwnd = h["hwnd"]
try:
    with bw.BackgroundSession(hwnd) as bg:
        SC.ensure_tree(hwnd, bg)
        for argv in (["catalog", "--hwnd", str(hwnd), "--limit", "8", "--name", "atlas_fixture_cli"],
                     ["probe", "--hwnd", str(hwnd), "--max", "6"],
                     ["exec", "add a marker then zoom in", "--hwnd", str(hwnd)],
                     ["probe", "--hwnd", str(hwnd), "--allow-input"],
                     ["exec", "add a marker", "--hwnd", str(hwnd), "--run"]):
            print("$ hojaiga_professor.py", " ".join(argv))
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                rc = H.main(argv)
            out = buf.getvalue().strip().splitlines()
            print("\n".join(out[:14]), f"\n  (rc={rc}, {len(out)} lines)\n")
        print("state after refused/dry commands:", harness.read_state_text(hwnd))
finally:
    harness.close(h)
