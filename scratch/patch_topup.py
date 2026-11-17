import ast
import io

R = "D:/new_automation/All codes/core_organs/professor/knowledge/"


def patch(path, pairs):
    s = io.open(path, "r", encoding="utf-8").read()
    for old, new in pairs:
        assert old in s, old[:90]
        s = s.replace(old, new, 1)
    ast.parse(s)
    io.open(path, "w", encoding="utf-8", newline="\n").write(s)


patch(R + "guide_finder.py", [
    ("max_queries: int = 5, sources_wanted: int = 2,\n             winget_runner: Callable[[List[str]], str] = _winget_run) -> Dict[str, Any]:",
     "max_queries: int = 5, sources_wanted: int = 2,\n             winget_runner: Callable[[List[str]], str] = _winget_run, want_docs: int = 0) -> Dict[str, Any]:"),
    ("        if web_enabled(web) and not indexed_docs(ix, key):\n            rep[\"web\"] = \"on\"",
     "        if web_enabled(web) and (not indexed_docs(ix, key) or (want_docs and indexed_docs(ix, key) < want_docs)):          # top-up: an application with only a handful of documents gets more\n            rep[\"web\"] = \"on\""),
])
patch(R + "guide_corpus.py", [
    ("catalog: Optional[List[Dict[str, Any]]] = None, ix: Any = None, max_queries: int = 3) -> Dict[str, Any]:",
     "catalog: Optional[List[Dict[str, Any]]] = None, ix: Any = None, max_queries: int = 3, top_up: int = 0) -> Dict[str, Any]:"),
    ("        if have and not force:\n            log(f\"[{n}/{len(sel)}] {a['name']}: already {have} document(s)\")",
     "        if have and not force and not (top_up and have < top_up):\n            log(f\"[{n}/{len(sel)}] {a['name']}: already {have} document(s)\")"),
    ("max_queries=max_queries, **kw)", "max_queries=max_queries, want_docs=top_up, sources_wanted=(4 if top_up else 2), **kw)"),
    ("force=force, delay_s=delay_s, max_pages=pages", "force=force or bool(top_up and have < top_up), delay_s=delay_s, max_pages=pages"),
])
print("ok")
