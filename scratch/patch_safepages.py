import ast, io
P = "D:/new_automation/All codes/core_organs/professor/adapters/chromium.py"
s = io.open(P, "r", encoding="utf-8").read()
old = s[s.index("            urls = [u for u in urls if not DANGEROUS_PAGES.search(u)"):s.index("            for u in urls:\n                if time.time() - t0 > budget_s:")]
new = '''            urls = [u for u in urls if SAFE_PAGE_RX.search(u) and not DANGEROUS_PAGES.search(u) and not re.search(r"sync|optin|signin|dialog|side-panel|top-chrome|internals|feedback", u) and u.count("/") <= 3][:60]
'''
s = s.replace(old, new, 1)
s = s.replace('CACHE_PATH = os.path.join(CFG.DATA_DIR, "adapters", "chromium_pages.json")', '''CACHE_PATH = os.path.join(CFG.DATA_DIR, "adapters", "chromium_pages.json")
# only ordinary user-facing pages are opened to read their titles (some internal pages close or crash the browser: measured with chrome://history-sync-optin)
SAFE_PAGE_RX = re.compile(r"^chrome://(settings|history|downloads|bookmarks|extensions|password-manager|apps|about|version|accessibility|flags|components|help|credits|terms|new-tab-page|management|read-later|tab-search|"
                          r"privacy-sandbox|profile-picker|certificate-manager|app-settings|system|sandbox)\b", re.I)''', 1)
ast.parse(s)
io.open(P, "w", encoding="utf-8", newline="\n").write(s)
print("ok")
