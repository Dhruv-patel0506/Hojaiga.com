p = r"D:\new_automation\All codes\core_organs\atlas\teach.py"
s = open(p, encoding="utf-8").read()
old = "def howto(key: str, question: str"
new = '''def _com_libs(key: str) -> List[Dict[str, Any]]:
    f = os.path.join(C.ATLAS_DIR, "com", f"{key}.json")
    try:
        with open(f, "r", encoding="utf-8") as fh:
            d = json.load(fh)
        progs = [c.get("progid") for c in d.get("classes", []) if c.get("progid")]
        return [dict(lib, _progids=progs) for lib in (d.get("typelibs") or {}).values() if lib.get("ok")]
    except Exception:
        return []


def api_routes(key: str, question: str, *, limit: int = 3, store: Optional[C.AtlasStore] = None) -> List[Dict[str, Any]]:
    """Programmatic ways to do the same thing: the program's registered object model (COM type library: member names + parameter names) and the operators its own
    runtime reported (introspection). Input-independent, so they matter for programs that ignore posted input."""
    qt, w, _ = expand_query(question, False)
    out: List[Dict[str, Any]] = []
    for lib in _com_libs(key):
        sigs = lib.get("sigs") or {}
        meth = lib.get("methods") or {}
        seen = set()
        for tname in set(list(sigs.keys()) + list(meth.keys())):
            tt = set(toks(tname.lstrip("_")))
            for m in list(sigs.get(tname, {}).keys()) + [x for x in meth.get(tname, []) if "[" not in x]:
                if (tname, m) in seen:
                    continue
                seen.add((tname, m))
                mt = set(toks(m))
                s = sum(3.0 * w.get(t, 1.0) for t in qt if t in mt) + sum(1.0 * w.get(t, 1.0) for t in qt if t in tt)
                if s <= 0 or not any(t in mt for t in qt):
                    continue
                params = sigs.get(tname, {}).get(m)
                call = (f"{tname.lstrip('_')}.{m}(" + ", ".join(params) + ")") if params is not None else f"{tname.lstrip('_')}.{m}"
                out.append({"score": s + (0.8 if params is not None else 0.0), "via": "COM object model" + (f" ({lib['_progids'][0]})" if lib.get("_progids") else ""),
                            "member": f"{tname.lstrip('_')}.{m}", "call": call, "params": params or []})
    try:
        from . import introspect
        st = store or C.get_store()
        tmpl = introspect.call_template_of(key, st)
        if tmpl:
            for o in introspect.operators_of(key, st):
                mt = set(toks(o.get("name", ""))) | set(toks(o["id"].replace(".", " ").replace("_", " ")))
                s = sum(3.0 * w.get(t, 1.0) for t in qt if t in mt)
                if s > 0:
                    out.append({"score": s, "via": "the program's own scripting runtime", "member": o["id"], "call": tmpl.format(id=o["id"]), "params": [x[0] for x in o.get("props", [])][:8],
                                "doc": o.get("desc", "")[:120]})
    except Exception:
        pass
    out.sort(key=lambda r: -r["score"])
    return out[:limit]


def howto(key: str, question: str'''
assert old in s
s = s.replace(old, new, 1)
NL = chr(92) + "n"
old = '    res["answer"] = "' + NL + '".join(lines)' + chr(10) + '    res["best"] = best'
new = '''    try:
        api = api_routes(key, question)
    except Exception:
        api = []
    if api:
        res["api"] = api
        lines += ["", "Programmatic route (no clicking):"]
        for a in api[:2]:
            lines.append(f"- `{a['call']}` - {a['via']}" + (f"; {a['doc']}" if a.get("doc") else ""))
    res["answer"] = "''' + NL + '''".join(lines)
    res["best"] = best'''
assert old in s, "tail"
s = s.replace(old, new, 1)
open(p, "w", encoding="utf-8").write(s)
print("ok")
