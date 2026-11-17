import ast
import io


def patch(path, pairs):
    s = io.open(path, "r", encoding="utf-8").read()
    for old, new in pairs:
        assert old in s, old[:90]
        s = s.replace(old, new, 1)
    ast.parse(s)
    io.open(path, "w", encoding="utf-8", newline="\n").write(s)


patch("D:/new_automation/All codes/core_organs/professor/executor.py", [
    (r'''        self.deny: Optional["re.Pattern"] = None''', r'''        self.allow: Optional["re.Pattern"] = None                 # verbs that look 'sensitive' to the generic safety rules but are harmless HERE (the profile of a throw-away Chrome the run itself created)
        self.deny: Optional["re.Pattern"] = None'''),
    (r'''        if self.deny is not None and self.deny.search(v.label + " " + " ".join(v.path)):
            hum, cls = True, ("sensitive" if cls == "safe" else cls)''', r'''        if hum and cls == "sensitive" and self.allow is not None and self.allow.search(v.label):
            hum = False
        if self.deny is not None and self.deny.search(v.label + " " + " ".join(v.path)):
            hum, cls = True, ("sensitive" if cls == "safe" else cls)'''),
])
patch("D:/new_automation/All codes/core_organs/professor/apprun.py", [
    (r'''    focus_rx: str = ""  ''', r'''    allow_rx: str = ""             # labels the generic safety rules call sensitive but that are harmless in this owned, throw-away context
    focus_rx: str = ""  '''),
    (r'''        self.ex.deny = NAV_FORBID_RX if self.spec.mode == "navigate" else DENY_RX''', r'''        self.ex.deny = NAV_FORBID_RX if self.spec.mode == "navigate" else DENY_RX
        if self.spec.allow_rx:
            self.ex.allow = re.compile(self.spec.allow_rx, re.I)'''),
    (r'''focus_rx=r"profile|account|sync|customi[sz]e|theme|avatar|sign|homepage|startup|default browser|settings",''', r'''focus_rx=r"profile|account|sync|customi[sz]e|theme|avatar|sign|homepage|startup|default browser|settings", allow_rx=r"^(profile|people|add (chrome )?profile|customi[sz]e (chrome|profile)|switch profile|guest)\b",'''),
])
print("ok")
