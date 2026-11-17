import ast, io
P = "D:/new_automation/All codes/core_organs/professor/knowledge/guide_finder.py"
s = io.open(P, "r", encoding="utf-8").read()
old = '''    seen, uniq = set(), []
    for c in sorted(out, key=lambda c: -c["score"]):
        if c["url"] not in seen:'''
new = '''    seen, uniq = set(), []
    for c in sorted(out, key=lambda c: -c["score"]):
        if not_a_user_guide(c["url"]):
            continue
        if c["url"] not in seen:'''
assert old in s
s = s.replace(old, new, 1)
old = '''def unsafe_result(url: str, title: str) -> bool:'''
new = '''# developer / API reference portals are not the GUI user's guide (a package manager's 'Documentation' link for a browser can point at one)
_DEV_PORTALS = ("developer.chrome.com", "chromestatus.com", "developer.mozilla.org", "developers.google.com", "developer.apple.com", "developer.android.com", "developer.blender.org", "api.")


def not_a_user_guide(url: str) -> bool:
    """A store listing, a marketplace page or a developer-API portal: never an application's user guide."""
    sp = urllib.parse.urlsplit(url)
    host, path = (sp.hostname or "").lower(), (sp.path or "").lower()
    if host == "chrome.google.com":
        return path.startswith("/webstore")
    full = host + path
    return any(x in full for x in _STORES if x != "chrome.google.com") or any(host == d or host.endswith("." + d) or (d.endswith(".") and host.startswith(d)) for d in _DEV_PORTALS)


def unsafe_result(url: str, title: str) -> bool:'''
assert old in s
s = s.replace(old, new, 1)
# unsafe_result uses the same predicate
import re
s = re.sub(r'''or any\(a in host for a in _AGGREGATORS\) or any\(a in host \+ \(urllib\.parse\.urlsplit\(url\)\.path or ""\) for a in _STORES if a\.rstrip\("\."\) != "chrome\.google\.com"\) \\n\s+or \(host == "chrome\.google\.com" and "/webstore" in url\)''',
           'or any(a in host for a in _AGGREGATORS) or not_a_user_guide(url)', s, count=1)
ast.parse(s)
io.open(P, "w", encoding="utf-8", newline="\n").write(s)
print("ok", "not_a_user_guide(url)" in s)
