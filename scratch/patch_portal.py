import ast
import io

P = "D:/new_automation/All codes/core_organs/professor/knowledge/guide_finder.py"
s = io.open(P, "r", encoding="utf-8").read()
old = '''                    portal = urllib.parse.urlsplit(c["url"]).path in ("", "/")                      # a site ROOT cannot be scoped by path: there, only pages that name the application are kept'''
new = '''                    portal = is_portal_root(c["url"])                                                # a site ROOT cannot be scoped by path: there, only pages that name the application are kept'''
assert old in s
s = s.replace(old, new, 1)
old2 = "def distinctive_words(ident: AppIdentity) -> List[str]:"
new2 = '''_LOCALE_SEG = re.compile(r"^(hc|en|latest|stable|current|home|index\\.html?|[a-z]{2}([-_][a-z]{2,4})?)$", re.I)


def is_portal_root(url: str) -> bool:
    """A site root (or a bare locale root such as /en-us, /hc/en-us): its path names no product, so a crawl from it can wander into every product the site hosts."""
    segs = [x for x in urllib.parse.urlsplit(url).path.split("/") if x]
    return all(_LOCALE_SEG.match(x) for x in segs)


def distinctive_words(ident: AppIdentity) -> List[str]:'''
assert old2 in s
s = s.replace(old2, new2, 1)
ast.parse(s)
io.open(P, "w", encoding="utf-8", newline="\n").write(s)
print("portal detection includes locale roots")
