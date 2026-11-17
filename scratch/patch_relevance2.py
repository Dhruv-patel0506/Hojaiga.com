import ast
import io

P = "D:/new_automation/All codes/core_organs/professor/knowledge/guide_finder.py"
s = io.open(P, "r", encoding="utf-8").read()


def rep(old, new):
    global s
    assert old in s, old[:90]
    s = s.replace(old, new, 1)


rep('''    n = 0
    for p in pages:
        if words and not relevant(p, words):
            rep["skipped"].append((p.url, "off-topic: the page never names the application"))
            continue''', '''    n = 0
    if words and pages and not relevant(pages[0], words):                       # the SOURCE must name the application (its start page); its sub-pages need not repeat the name
        rep["skipped"].append((pages[0].url, f"off-topic source: its start page never names the application ({', '.join(words[:3])}); {len(pages)} page(s) dropped"))
        return 0
    for p in pages:''')
rep('''                    if _ingest_pages(ix, key, pages, rep, reg, "web", ident.version, embed_small, distinctive_words(ident)):''', '''                    vetted = c.get("kind") in ("winget-docs", "seed")                              # vetted by where it came from (the package catalogue / an official root that answered)
                    if _ingest_pages(ix, key, pages, rep, reg, "web", ident.version, embed_small, () if vetted else distinctive_words(ident)):''')
ast.parse(s)
io.open(P, "w", encoding="utf-8", newline="\n").write(s)
print("source-level relevance gate")
