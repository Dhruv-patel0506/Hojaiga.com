import re, sys
sys.path.insert(0, r"d:\new_automation\All codes")
from core_organs.professor.knowledge import version_fit as VF

t = "Select the text you want to format."
print("scope:", VF.step_scope(t, "any", ("powerpoint",)))

def which(rx, text, name):
    m = rx.search(text)
    if m:
        print(f"{name} MATCH: {m.group(0)!r} at {m.start()}")
        return True
    return False

which(VF.CHOICE_RX, t, "CHOICE")
which(VF.CONTENT_RX, t, "CONTENT")
which(VF.OBJECT_REF_RX, t, "OBJREF")
which(VF.DIALOG_BUTTON_RX, t, "DLGBTN")

t2 = "Select the text you want to change."
print("t2 scope:", VF.step_scope(t2, "any", ("powerpoint",)))
which(VF.CHOICE_RX, t2, "CHOICE-t2")
which(VF.CONTENT_RX, t2, "CONTENT-t2")

# control cases must stay choice
for c in ["Select the layout you want from the menu.", "Select the option you want.", "Select **New Slide**."]:
    print(repr(c), VF.step_scope(c, "any", ("powerpoint",)))
