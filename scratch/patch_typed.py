import ast, io

def patch(path, pairs):
    s = io.open(path, "r", encoding="utf-8").read()
    for old, new in pairs:
        assert old in s, old[:80]
        s = s.replace(old, new, 1)
    ast.parse(s)
    io.open(path, "w", encoding="utf-8", newline="\n").write(s)

patch("D:/new_automation/All codes/core_organs/professor/knowledge/guide_steps.py", [
(r'''    if tm:
        typed = (tm.group(1) or tm.group(2) or "").strip()''', r'''    if tm:
        typed = (tm.group(1) or tm.group(2) or "").strip()
    if not typed:                                                    # 'Type .LOG on the first line': an unquoted literal (starts with a symbol, is ALL CAPS or has a digit) right after the verb
        lm = re.search(r"\b(?:type|enter|write|input)\s+([^\s,;]+)", txt, re.I)
        if lm:
            tok = lm.group(1).strip(".,;:!?\"'")
            raw_tok = lm.group(1)
            if tok.lower() not in ("a", "an", "the", "your", "some", "any", "in", "into", "it", "this", "that", "text", "name", "value", "numbers", "number", "and", "or", "to", "on", "of", "with", "for", "at", "one", "each", "all", "when", "if") \
                    and (raw_tok[:1] in ".&%$#@/\_-+*=<>[]{}()" or (tok.isupper() and len(tok) >= 2) or any(c.isdigit() for c in tok)):
                typed = raw_tok.rstrip(",;:")'''),
])
patch("D:/new_automation/All codes/core_organs/professor/executor.py", [
('''                want = st.action if st.action in ("on", "off") else ""
                txt = st.text if (st.action == "type" and st.text) else ""
                s = self._step_for_verb(g.verb, st.raw, g.conf, "guide", gp["cite"], want, txt)''', '''                want = st.action if st.action in ("on", "off") else ""
                txt = st.text if (st.action == "type" and st.text) else ""
                placeholder = False
                if not txt and st.action in ("type", "set") and (g.verb.role in FIELD_ROLES or g.verb.role == "field"):
                    txt, placeholder = self.placeholder, True            # the manual says WHAT to enter only in general terms ('a descriptive name'): a neutral test string stands in, and the step says so
                s = self._step_for_verb(g.verb, st.raw, g.conf, "guide", gp["cite"], want, txt)
                if placeholder:
                    s.note = (s.note + " " if s.note else "") + "the manual gives no literal value: a neutral placeholder is entered"'''),
('''        self.deny: Optional["re.Pattern"] = None''', '''        self.placeholder = "Hojaiga test"                         # what goes into a field when the guide says only 'enter a name' (never data of the user's)
        self.deny: Optional["re.Pattern"] = None'''),
])
print("ok")
