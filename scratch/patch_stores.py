import ast, io
P = "D:/new_automation/All codes/core_organs/professor/knowledge/guide_finder.py"
s = io.open(P, "r", encoding="utf-8").read()
old = '''_BAD_HOSTS = ("youtube.", "youtu.be",'''
new = '''# app-store / extension-marketplace listings describe a product to buyers; they are not its user guide
_STORES = ("chromewebstore.google.com", "chrome.google.com", "play.google.com", "apps.apple.com", "itunes.apple.com", "apps.microsoft.com", "microsoft.com/store", "marketplace.visualstudio.com",
           "addons.mozilla.org", "store.steampowered.com", "github.com/marketplace", "chocolatey.org", "sourceforge.net", "softpedia.")
_BAD_HOSTS = ("youtube.", "youtu.be",'''
assert old in s
s = s.replace(old, new, 1)
old2 = '''or any(a in host for a in _AGGREGATORS)'''
new2 = '''or any(a in host for a in _AGGREGATORS) or any(a in host + (urllib.parse.urlsplit(url).path or "") for a in _STORES if a.rstrip(".") != "chrome.google.com") \
        or (host == "chrome.google.com" and "/webstore" in url)'''
assert old2 in s
s = s.replace(old2, new2, 1)
ast.parse(s)
io.open(P, "w", encoding="utf-8", newline="\n").write(s)
print("ok")
