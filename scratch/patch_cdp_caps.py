import ast
import io
import os
import shutil

R = "D:/new_automation/All codes/core_organs/professor/"

# cdp.py: BROWSER_VERBS -> CAPABILITIES (what the PROTOCOL can do; names come from the guide)
p = R + "adapters/cdp.py"
s = io.open(p, "r", encoding="utf-8").read()
i0 = s.index("# The browser's own commands, in the words and with the shortcuts a Chrome guide uses.")
new = r'''# What the PROTOCOL can do to a tabbed Chromium window - an ability list of the toolkit, not of any application. `intent` finds the guide's own name for it (its shortcut table:
# 'Ctrl+T  Open a new tab'); `label` is the neutral name used when the guide has none.
CAPABILITIES: List[Dict[str, Any]] = [
    {"kind": "new_tab", "intent": r"\bnew tab\b|\bopen a (?:new )?tab\b", "label": "New tab", "desc": "opens a new tab"},
    {"kind": "new_window", "intent": r"\bnew window\b|\bopen a (?:new )?window\b", "label": "New window", "desc": "opens a new window"},
    {"kind": "close_tab", "intent": r"\bclose (?:the |a |this |current )?tab\b", "label": "Close tab", "desc": "closes the current tab"},
    {"kind": "reload", "intent": r"\breload\b|\brefresh\b", "label": "Reload", "desc": "reloads the page"},
    {"kind": "back", "intent": r"\bgo back\b|\bprevious page\b|^back$", "label": "Back", "desc": "goes back one page"},
    {"kind": "forward", "intent": r"\bgo forward\b|\bnext page\b|^forward$", "label": "Forward", "desc": "goes forward one page"},
    {"kind": "next_tab", "intent": r"\bnext tab\b|\bswitch to the next tab\b", "label": "Next tab", "desc": "switches to the next tab"},
    {"kind": "prev_tab", "intent": r"\bprevious tab\b|\bswitch to the previous tab\b", "label": "Previous tab", "desc": "switches to the previous tab"},
]
'''
s = s[:i0] + new
s = s.replace("  BROWSER_VERBS                       the browser's own commands in the manual's words ('New tab', 'Close tab', 'Reload', 'Back', ...) with the shortcut the guide mentions, each implemented\n                                      with a protocol method (Target.createTarget / closeTarget / Page.reload / history navigation) - the OUTCOME of the shortcut, delivered headlessly",
              "  CAPABILITIES                        what the protocol can do to a tabbed window (open / close / switch a tab, reload, history) - named in the GUIDE's words by the adapter", 1)
ast.parse(s)
io.open(p, "w", encoding="utf-8", newline="\n").write(s)

# chromium.py <- chromium_new.py
shutil.move(R + "adapters/chromium_new.py", R + "adapters/chromium.py")

# apprun: pass the guide's menus
p = R + "apprun.py"
s = io.open(p, "r", encoding="utf-8").read()
old = '''            try:
                shortcuts = GCARD.build_card(self.gkey, self.index, save=False).get("shortcuts", {})
                terms = [t["term"] for t in GCARD.build_card(self.gkey, self.index, save=False)["ui_taxonomy"]["terms"]]
            except Exception:
                shortcuts, terms = {}, []
            self.adapter = ChromiumAdapter(br, log=self.say, guide_shortcuts=shortcuts, guide_terms=terms)'''
new = '''            try:
                card = GCARD.build_card(self.gkey, self.index, save=False)
                shortcuts, terms, menus = card.get("shortcuts", {}), [t["term"] for t in card["ui_taxonomy"]["terms"]], card["ui_taxonomy"]["menus"]
            except Exception:
                shortcuts, terms, menus = {}, [], {}
            self.adapter = ChromiumAdapter(br, log=self.say, guide_shortcuts=shortcuts, guide_terms=terms, guide_menus=menus)'''
assert old in s
s = s.replace(old, new, 1)
ast.parse(s)
io.open(p, "w", encoding="utf-8", newline="\n").write(s)
print("ok")
