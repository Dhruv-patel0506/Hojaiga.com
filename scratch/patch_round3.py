base = r"D:\new_automation\All codes\core_organs\atlas"
BS = chr(92)

# ---------------------------------------------------------------- explorer.py: online/account words are never opened
p = base + r"\explorer.py"
s = open(p, encoding="utf-8").read()
old = "|telemetry|privacy)" + BS + "b\", re.I)"
assert old in s, "sensitive tail"
s = s.replace(old, "|telemetry|privacy|online|stock|brand images|onedrive|sharepoint|cloud|bing|marketplace|store|get add-?ins|templates and themes|sign|connected)" + BS + "b\", re.I)", 1)
# browser-chrome / file-dialog noise in captured fields
old = "        info[\"fields\"] = ["
new = '''        NOISE = re.compile(r"(to open this link|translate options|automatic profile switching|app available|search instead|preview pane|view slider|line up|context help|^new folder$|^organize$|^details$|^&?help$|richedit control)", re.I)
        info["fields"] = ['''
assert old in s
s = s.replace(old, new, 1)
s = s.replace('''for c in all_ctrls if c.get("name") and c["kind"] not in ("listitem", "treeitem", "grid", "document") and not (file_dlg and c["kind"] == "list")][:80]''', '''for c in all_ctrls if c.get("name") and c["kind"] not in ("listitem", "treeitem", "grid", "document") and not (file_dlg and c["kind"] == "list") and not NOISE.search(c["name"])][:80]''', 1)
open(p, "w", encoding="utf-8").write(s)

# ---------------------------------------------------------------- uimap.py
p = base + r"\uimap.py"
s = open(p, encoding="utf-8").read()
# sanitizer
old = "def private_context(nodes, n) -> bool:"
new = '''ACCOUNT_RX = re.compile(r"^(onedrive|sharepoint|dropbox|google drive|box|icloud)" + BS + "s*[-:" + chr(0x2013) + "]" + BS + "s*.+$", re.I)
EMAIL_RX = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+" + BS + ".[A-Za-z]{2,}")


def clean_name(name: str) -> str:
    """Account / organisation / e-mail details inside a label are the user's identity, not the program's structure: 'OneDrive - <organisation>' -> 'OneDrive (account)'."""
    m = ACCOUNT_RX.match(name or "")
    if m:
        return f"{m.group(1)} (account)"
    return EMAIL_RX.sub("<email>", name or "")


def private_context(nodes, n) -> bool:'''
assert old in s
s = s.replace(old, new, 1)
# apply clean_name when final map is cleaned
old = '''    @staticmethod
    def clean(o: Any) -> Any:
        if isinstance(o, dict):
            return {k: Cartographer.clean(v) for k, v in o.items() if not k.startswith("_") and k != "rect"}'''
new = '''    @staticmethod
    def clean(o: Any) -> Any:
        if isinstance(o, dict):
            return {k: (clean_name(v) if k == "name" and isinstance(v, str) else Cartographer.clean(v)) for k, v in o.items() if not k.startswith("_") and k != "rect"}'''
assert old in s
s = s.replace(old, new, 1)
# open_menu_items: dedupe by item name, keep 'unwound'
old = '''                for it in todo[:6]:
                    if self.left() < 10 or not self.alive():
                        return'''
new = '''                for it in todo[:6]:
                    if self.left() < 10 or not self.alive():
                        return
                    if it["name"] in self._item_cache:                                 # the same item in many menus (More Colors... under every pen): opened once
                        it["leads_to"] = dict(self._item_cache[it["name"]], same_as_seen=True)
                        continue'''
assert old in s
s = s.replace(old, new, 1)
old = '''                        it["leads_to"] = {k: v for k, v in rec.items() if k in ("effect", "dialog", "controls", "pages", "wizard", "master_detail", "fields", "file_dialog", "commit", "cancel", "why")}
                        it["leads_to"]["type"] = "dialog" if rec.get("effect") == "dialog" else "command"'''
new = '''                        it["leads_to"] = {k: v for k, v in rec.items() if k in ("effect", "dialog", "controls", "pages", "wizard", "master_detail", "fields", "file_dialog", "commit", "cancel", "why", "unwound")}
                        it["leads_to"]["type"] = "dialog" if rec.get("effect") == "dialog" else "command"
                        if rec.get("effect") == "dialog":
                            self._item_cache[it["name"]] = dict(it["leads_to"])'''
assert old in s
s = s.replace(old, new, 1)
s = s.replace('''        self.created_workspace = False
''', '''        self.created_workspace = False
        self._item_cache: Dict[str, Dict[str, Any]] = {}
''', 1)
# menu items in sensitive context: also skip when the item matches the (now wider) sensitive words - already done via SENSITIVE_RX
open(p, "w", encoding="utf-8").write(s)
print("round3 ok")
