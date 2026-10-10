import os, sys, tempfile, time
os.environ["HOJAIGA_PROF_DIR"] = os.path.join(tempfile.gettempdir(), "hojaiga_prof_key")
sys.path.insert(0, r"D:\new_automation"); sys.path.insert(0, r"D:\new_automation\All codes")
from core_organs.professor import pointer as PT
from core_organs.professor.lab.labkit import Lab, client_origin
from core_organs.professor.lab.lab_matrix import Fx
from core_organs import headless_input as hin
for name in sys.argv[1:] or ["winforms_aware", "wpf"]:
    lab = Lab(name)
    print("==", name)
    m = lab.mark()
    print(" posted ctrl+a, no agent:", hin.post_key_combo(lab.hwnd, "ctrl+a")[0]); time.sleep(0.5)
    print("   events:", [(e["kind"], e.get("ctrl"), e.get("shift")) for e in lab.since(m) if e["kind"].startswith("keydown")])
    vp = PT.VirtualPointer(lab.hwnd, "keyprobe", Fx(), only=["shim"])
    ox, oy = client_origin(lab.hwnd)
    vp.click(ox + 200, oy + 160)          # attaches the agent
    m = lab.mark()
    print(" posted ctrl+a, agent on:", hin.post_key_combo(lab.hwnd, "ctrl+a")[0]); time.sleep(0.8)
    print("   events:", [(e["kind"], e.get("ctrl"), e.get("shift")) for e in lab.since(m) if e["kind"].startswith("keydown")])
    m = lab.mark()
    print(" posted shift+x, agent on:", hin.post_key_combo(lab.hwnd, "shift+x")[0]); time.sleep(0.8)
    print("   events:", [(e["kind"], e.get("ctrl"), e.get("shift")) for e in lab.since(m) if e["kind"].startswith("keydown")])
    vp.close(); lab.close()
