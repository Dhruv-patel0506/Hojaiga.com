import sys
sys.path.insert(0, r"d:\new_automation\All codes")
from core_organs.professor.harvest import normalize_chord, _mouse_word
from core_organs.professor.executor import MOUSE_KEY_WORDS

cases = {
    "Ctrl+Rightmouse": "", "Ctrl+Click": "", "Leftmouse": "", "RMB": "", "MMB": "", "Wheel_Up": "",
    "ctrl + shift+s": "Ctrl+Shift+S", "Ctrl+Shift+O": "Ctrl+Shift+O", "F3": "F3", "Ctrl+P": "Ctrl+P", "Alt+F4": "Alt+F4",
}
bad = [(c, normalize_chord(c)) for c, want in cases.items() if normalize_chord(c) != want]
print("normalize_chord mismatches:", bad or "none")
print("mouse words:", {w: _mouse_word(w) for w in ("click", "LMB", "RmbClick", "WheelUp", "Enter", "Delete")})
print("MOUSE_KEY_WORDS click ->", MOUSE_KEY_WORDS["click"], "| right_click ->", MOUSE_KEY_WORDS.get("rightclick"))
sys.exit(1 if bad else 0)
