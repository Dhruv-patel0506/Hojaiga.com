import ast
import io

P = "D:/new_automation/All codes/core_organs/professor/checkpoints.py"
s = io.open(P, "r", encoding="utf-8").read()


def rep(old, new):
    global s
    assert old in s, old[:100]
    s = s.replace(old, new, 1)


rep('''def run(apps: Sequence[str] = (), tier: int = 1,''', '''def ensure_guide(sp: Any, say: Any = print, min_docs: int = 3) -> int:
    """An application with no (or almost no) guide in the corpus gets its guide looked for BEFORE the scan: install folder, the vendor's own pages, winget's documentation links, then web search -
    the finder's own policy (official sources first, robots.txt kept, no aggregators, no challenge bypass). Returns the number of guide documents the application has afterwards."""
    try:
        from .knowledge import guide_finder as GF, manual_rag as MR, guide_corpus as GCP
        from . import launcher as LN
        key = sp.guide_key or sp.key
        ix = MR.ManualIndex()
        try:
            have = GF.indexed_docs(ix, key)
            if have >= min_docs:
                return have
            say(f"guide: '{sp.name}' has {have} document(s) - looking for its user guide (official sources first)")
            exe, company, seeds = "", "", []
            try:
                exe = LN.resolve(sp.name).exe or ""
            except Exception:
                pass
            for a in GCP.load_catalog():
                if a.get("key") == key:
                    company, seeds = a.get("company", ""), a.get("seeds", [])
                    break
            ident = GF.AppIdentity(app_key=key, product=sp.name, company=company, exe=exe)
            rep_ = GF.discover(ident, ix, web=True, budget_s=240.0, force=bool(have), seeds=seeds, want_docs=min_docs * 4, sources_wanted=4)
            n = GF.indexed_docs(ix, key)
            say(f"guide: {n} document(s) now ({rep_.get('coverage', '')[:90]})")
            return n
        finally:
            ix.close()
    except Exception as exc:
        say(f"guide lookup failed ({type(exc).__name__}): the scan goes on without one")
        return 0


def run(apps: Sequence[str] = (), tier: int = 1,''')
rep('''        only_list: bool = False) -> Dict[str, Any]:''', '''        only_list: bool = False, fetch_guides: bool = True) -> Dict[str, Any]:''')
rep('''            rep: Dict[str, Any] = {}
            try:
                rep = AR.AppRun(''', '''            rep: Dict[str, Any] = {}
            if guide and fetch_guides:
                ensure_guide(sp, print)
            try:
                rep = AR.AppRun(''')
rep('''    ap.add_argument("--no-zip", action="store_true")''', '''    ap.add_argument("--no-zip", action="store_true")
    ap.add_argument("--no-guide-fetch", action="store_true", help="do not look for a guide when the application has none in the corpus")''')
rep('''a.tasks, a.attempts, a.out, not a.no_zip, a.list)''', '''a.tasks, a.attempts, a.out, not a.no_zip, a.list, not a.no_guide_fetch)''')
ast.parse(s)
io.open(P, "w", encoding="utf-8", newline="\n").write(s)
print("ok")
