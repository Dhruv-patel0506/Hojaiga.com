import sys
sys.path[:0] = ["D:/new_automation", "D:/new_automation/All codes"]
from core_organs import universal_scan as us, static_knowledge as sk
from core_organs.atlas import scanner as SC
for n in ("notepad", "paint", "chrome", "visual studio code", "discord", "whatsapp", "blender", "obs studio", "word", "settings"):
    r = us.resolve_app(n)
    print(n.ljust(20), r, "| exe_for:", sk.exe_for(n)[:70], "| installed:", SC.resolve_installed(n)[:70])
