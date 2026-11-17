"""
professor.knowledge.repo_graph -- one or many Git repositories -> a single graph that answers "what code runs when this button is pressed?".

Ingest (offline, stdlib + sqlite + networkx, no tree-sitter needed):
  files      path, language, line count, Hojaiga sub-division (knowledge.divisions)
  symbols    classes / functions / methods with line spans (Python via `ast`; JS/TS, C/C++/C#/Java/Kotlin/Swift/Go/Rust via declaration patterns)
  edges      import / include between files; call between symbols (by name), inheritance
  strings    UI-label-shaped string literals with the symbol that contains them (Python call arguments such as text="Save", bl_label = "Add Cube",
             SwiftUI Button("Commit"), JSX >Save<, C/C++ N_("Open"), XAML Content="Open", .rc MENUITEM, .po msgid ...) -- the BRIDGE from screen to code
  effects    per symbol: db / network / file / process / ui markers found in its body -> "this handler writes a database and starts a process"
Query: link_label("Add Cube") -> files, symbols, callers/callees, division, effects. Several repos can be ingested under one project name; labels resolve across all.
"""

from __future__ import annotations

import ast
import os
import re
import sqlite3
import time
from collections import defaultdict
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Tuple

from .. import config as CFG
from ..schema import fold
from . import divisions

SKIP_DIRS = {".git", "node_modules", "venv", "hojaiga_env", ".venv", "__pycache__", "build", "dist", "out", "target", ".idea", ".vs", "bin", "obj",
             "Pods", "DerivedData", ".gradle", "vendor", "third_party", "thirdparty", ".mypy_cache", ".pytest_cache", "site-packages"}
LANG = {".py": "python", ".js": "js", ".jsx": "js", ".ts": "ts", ".tsx": "ts", ".mjs": "js", ".c": "c", ".h": "c", ".cc": "cpp", ".cpp": "cpp", ".cxx": "cpp",
        ".hpp": "cpp", ".cs": "csharp", ".java": "java", ".kt": "kotlin", ".swift": "swift", ".go": "go", ".rs": "rust", ".xaml": "xaml", ".rc": "rc",
        ".po": "po", ".resx": "resx", ".ui": "qtui", ".qml": "qml", ".json": "json", ".html": "html", ".vue": "vue"}
CODE_LANGS = {"python", "js", "ts", "c", "cpp", "csharp", "java", "kotlin", "swift", "go", "rust", "vue", "qml"}
MAX_FILE = 1_500_000

EFFECT_PATTERNS = {
    "database": re.compile(r"\b(sqlite3|cursor\(|\.execute\(|SELECT\s+.+\s+FROM|INSERT\s+INTO|UPDATE\s+\w+\s+SET|DELETE\s+FROM|\.objects\.|session\.(add|commit)|"
                           r"createQuery|DbContext|SaveChanges|prisma\.|mongoose|\.findOne\()", re.I),
    "network": re.compile(r"\b(requests\.|urllib|httpx|aiohttp|fetch\(|axios|XMLHttpRequest|WebSocket|HttpClient|URLSession|socket\.|curl_|http\.(Get|Post)|reqwest)", re.I),
    "file": re.compile(r"\b(open\(|os\.remove|shutil\.|fs\.(write|read|unlink)|File\.(Write|Read|Delete)|fopen\(|std::ofstream|std::ifstream|FileManager|"
                       r"write_text|read_text|json\.dump|pickle\.dump)", re.I),
    "process": re.compile(r"\b(subprocess|os\.system|Process\.Start|CreateProcess|ShellExecute|child_process|exec\(|spawn\(|Runtime\.getRuntime\(\)\.exec)", re.I),
    "ui": re.compile(r"\b(show\w*Dialog|MessageBox|setVisible|\.show\(\)|present\(|NSAlert|QDialog|Toast|notify\()", re.I),
}
_LABEL_OK = re.compile(r"^[^\W\d_][\w &'\-/.…,:()]{0,46}$", re.UNICODE)
_FMT = re.compile(r"%[sdif]|\{\d*\}|\$\{|\\n|</?\w+>|^\W+$|https?://|\.\w{2,4}$")
_LABEL_KWARGS = {"text", "label", "title", "tooltip", "description", "name", "caption", "placeholder", "content", "header", "bl_label", "bl_description",
                 "heading", "subtitle"}
_LABEL_ATTRS = {"bl_label", "bl_description", "label", "title", "name", "text", "caption", "description", "tooltip", "bl_idname"}
_LABEL_FUNCS = re.compile(r"(operator|button|menu|label|item|action|add_?item|addaction|tooltip|prop|separator|header|tab|checkbox|radio|slider|text|title)", re.I)


def _is_label(s: str) -> bool:
    s = s.strip()
    if not (2 <= len(s) <= 48) or _FMT.search(s) or not _LABEL_OK.match(s):
        return False
    return len(s.split()) <= 6


class RepoGraph:
    def __init__(self, path: Optional[str] = None):
        self.path = path or CFG.REPO_DB
        os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
        self.db = sqlite3.connect(self.path, check_same_thread=False)
        c = self.db
        c.executescript("""
        CREATE TABLE IF NOT EXISTS repos(id INTEGER PRIMARY KEY, project TEXT, name TEXT, path TEXT UNIQUE, ingested REAL, files INTEGER, symbols INTEGER);
        CREATE TABLE IF NOT EXISTS files(id INTEGER PRIMARY KEY, repo INTEGER, path TEXT, lang TEXT, lines INTEGER, division TEXT, why TEXT, UNIQUE(repo,path));
        CREATE TABLE IF NOT EXISTS symbols(id INTEGER PRIMARY KEY, file INTEGER, name TEXT, kind TEXT, line INTEGER, end_line INTEGER, parent TEXT, doc TEXT, effects TEXT);
        CREATE TABLE IF NOT EXISTS edges(src INTEGER, dst INTEGER, kind TEXT);
        CREATE TABLE IF NOT EXISTS calls(symbol INTEGER, callee TEXT);
        CREATE TABLE IF NOT EXISTS strings(id INTEGER PRIMARY KEY, file INTEGER, symbol INTEGER, line INTEGER, text TEXT, folded TEXT, ctx TEXT);
        CREATE INDEX IF NOT EXISTS i_sym_name ON symbols(name);
        CREATE INDEX IF NOT EXISTS i_str_fold ON strings(folded);
        CREATE INDEX IF NOT EXISTS i_calls_callee ON calls(callee);
        CREATE INDEX IF NOT EXISTS i_edges ON edges(src);
        """)
        c.commit()

    # ------------------------------------------------------------------------------------------------- ingest
    def ingest(self, repo_path: str, project: str = "", name: str = "", max_files: int = 30000, progress=None) -> Dict[str, Any]:
        t0 = time.time()
        repo_path = os.path.abspath(repo_path)
        if not os.path.isdir(repo_path):
            return {"ok": False, "error": "not a directory: " + repo_path}
        name = name or os.path.basename(repo_path.rstrip("\\/"))
        project = project or name
        cur = self.db.cursor()
        old = cur.execute("SELECT id FROM repos WHERE path=?", (repo_path,)).fetchone()
        if old:
            rid = old[0]
            for t in ("strings", "calls", "symbols", "edges"):
                pass
            fids = [r[0] for r in cur.execute("SELECT id FROM files WHERE repo=?", (rid,))]
            for f in fids:
                sids = [r[0] for r in cur.execute("SELECT id FROM symbols WHERE file=?", (f,))]
                cur.executemany("DELETE FROM calls WHERE symbol=?", [(s,) for s in sids])
                cur.execute("DELETE FROM strings WHERE file=?", (f,))
                cur.execute("DELETE FROM symbols WHERE file=?", (f,))
                cur.execute("DELETE FROM edges WHERE src=?", (f,))
            cur.execute("DELETE FROM files WHERE repo=?", (rid,))
            cur.execute("UPDATE repos SET project=?, name=?, ingested=? WHERE id=?", (project, name, time.time(), rid))
        else:
            cur.execute("INSERT INTO repos(project,name,path,ingested,files,symbols) VALUES(?,?,?,?,0,0)", (project, name, repo_path, time.time()))
            rid = cur.lastrowid
        nfiles = nsyms = nstr = 0
        files_by_rel: Dict[str, int] = {}
        pending_imports: List[Tuple[int, str, str]] = []
        for root, dirs, fnames in os.walk(repo_path):
            dirs[:] = [d for d in dirs if d not in SKIP_DIRS and not d.startswith(".")]
            for fn in fnames:
                ext = os.path.splitext(fn)[1].lower()
                lang = LANG.get(ext)
                if lang is None:
                    continue
                full = os.path.join(root, fn)
                try:
                    if os.path.getsize(full) > MAX_FILE:
                        continue
                    with open(full, "r", encoding="utf-8", errors="replace") as fh:
                        text = fh.read()
                except Exception:
                    continue
                if lang == "json" and not re.search(r"(locale|i18n|lang|strings|menu|messages)", fn, re.I):
                    continue
                rel = os.path.relpath(full, repo_path).replace("\\", "/")
                div, _score, _ru, why = divisions.classify(rel, text)
                cur.execute("INSERT INTO files(repo,path,lang,lines,division,why) VALUES(?,?,?,?,?,?)",
                            (rid, rel, lang, text.count("\n") + 1, div, ",".join(why)))
                fid = cur.lastrowid
                files_by_rel[rel] = fid
                nfiles += 1
                syms, strs, imps = _parse(lang, text, rel)
                sid_by_name: Dict[str, int] = {}
                for s in syms:
                    cur.execute("INSERT INTO symbols(file,name,kind,line,end_line,parent,doc,effects) VALUES(?,?,?,?,?,?,?,?)",
                                (fid, s["name"], s["kind"], s["line"], s["end"], s.get("parent", ""), (s.get("doc") or "")[:300], ",".join(sorted(s.get("effects", [])))))
                    sid = cur.lastrowid
                    sid_by_name.setdefault(s["name"], sid)
                    s["_id"] = sid
                    nsyms += 1
                    cur.executemany("INSERT INTO calls(symbol,callee) VALUES(?,?)", [(sid, c) for c in sorted(set(s.get("calls", [])))[:60]])
                for st in strs:
                    owner = None
                    for s in syms:
                        if s["line"] <= st["line"] <= s["end"] and (owner is None or (s["end"] - s["line"]) < (owner["end"] - owner["line"])):
                            owner = s
                    cur.execute("INSERT INTO strings(file,symbol,line,text,folded,ctx) VALUES(?,?,?,?,?,?)",
                                (fid, owner["_id"] if owner else None, st["line"], st["text"], fold(st["text"]), st.get("ctx", "")))
                    nstr += 1
                for imp in imps:
                    pending_imports.append((fid, imp, rel))
                if nfiles >= max_files:
                    break
                if progress and nfiles % 500 == 0:
                    progress("ingest", {"files": nfiles, "symbols": nsyms})
            if nfiles >= max_files:
                break
        # resolve imports to files
        by_base: Dict[str, List[int]] = defaultdict(list)
        for rel, fid in files_by_rel.items():
            base = os.path.splitext(os.path.basename(rel))[0].lower()
            by_base[base].append(fid)
            by_base[os.path.basename(rel).lower()].append(fid)
        nedge = 0
        for fid, imp, rel in pending_imports:
            key = re.split(r"[./\\]", imp.strip("./\\"))[-1].lower() if imp else ""
            tail = os.path.basename(imp).lower()
            for dst in (by_base.get(tail) or by_base.get(key) or [])[:3]:
                if dst != fid:
                    cur.execute("INSERT INTO edges(src,dst,kind) VALUES(?,?,'import')", (fid, dst))
                    nedge += 1
        cur.execute("UPDATE repos SET files=?, symbols=? WHERE id=?", (nfiles, nsyms, rid))
        self.db.commit()
        return {"ok": True, "repo": name, "project": project, "files": nfiles, "symbols": nsyms, "ui_strings": nstr, "import_edges": nedge,
                "seconds": round(time.time() - t0, 1)}

    # --------------------------------------------------------------------------------------------------- query
    def link_label(self, label: str, project: str = "", limit: int = 6) -> List[Dict[str, Any]]:
        """Code locations whose UI-label strings match what the screen shows. Exact folded match scores 1.0; a contained/containing phrase 0.6."""
        q = fold(label)
        if not q:
            return []
        cur = self.db.cursor()
        rows = cur.execute("SELECT s.id, s.file, s.symbol, s.line, s.text, s.ctx, f.path, f.division, r.name, r.project FROM strings s JOIN files f ON f.id=s.file "
                           "JOIN repos r ON r.id=f.repo WHERE s.folded=?" + (" AND r.project=?" if project else ""), ((q, project) if project else (q,))).fetchall()
        score = 1.0
        if not rows:
            like = f"%{q}%"
            rows = cur.execute("SELECT s.id, s.file, s.symbol, s.line, s.text, s.ctx, f.path, f.division, r.name, r.project FROM strings s JOIN files f ON f.id=s.file "
                               "JOIN repos r ON r.id=f.repo WHERE s.folded LIKE ? AND length(s.folded) <= ?" + (" AND r.project=?" if project else "") + " LIMIT 40",
                               ((like, len(q) * 3, project) if project else (like, len(q) * 3))).fetchall()
            score = 0.6
        out: List[Dict[str, Any]] = []
        for sid, fid, symid, line, text, ctx, path, div, repo, proj in rows:
            sym = cur.execute("SELECT name,kind,line,end_line,effects,doc FROM symbols WHERE id=?", (symid,)).fetchone() if symid else None
            ctxw = {"label_attr": 0.15, "kwarg": 0.1, "call_arg": 0.05}.get(ctx, 0.0)
            hit = {"score": round(min(1.0, score + ctxw), 2), "repo": repo, "file": path, "line": line, "text": text, "context": ctx, "division": div,
                   "symbol": ({"name": sym[0], "kind": sym[1], "line": sym[2], "end": sym[3], "effects": [e for e in (sym[4] or "").split(",") if e], "doc": sym[5]} if sym else None)}
            if sym:
                hit["callees"] = [r[0] for r in cur.execute("SELECT DISTINCT callee FROM calls WHERE symbol=? LIMIT 12", (symid,))]
                hit["callers"] = [f"{r[0]} ({r[1]}:{r[2]})" for r in cur.execute(
                    "SELECT s.name, f.path, s.line FROM calls c JOIN symbols s ON s.id=c.symbol JOIN files f ON f.id=s.file WHERE c.callee=? LIMIT 8", (sym[0],))]
            out.append(hit)
        out.sort(key=lambda h: (-h["score"], 0 if h["symbol"] else 1))
        return out[:limit]

    def reach_effects(self, symbol_name: str, depth: int = 3, limit: int = 60) -> Dict[str, Any]:
        """Breadth-first over call edges (by name): which side effects (database / network / file / process / ui) can pressing the handler reach?"""
        cur = self.db.cursor()
        seen: Set[str] = set()
        frontier = [symbol_name]
        found: Dict[str, List[str]] = defaultdict(list)
        for d in range(depth):
            nxt: List[str] = []
            for name in frontier:
                if name in seen:
                    continue
                seen.add(name)
                for eff, fpath, line in cur.execute("SELECT s.effects, f.path, s.line FROM symbols s JOIN files f ON f.id=s.file WHERE s.name=? LIMIT 6", (name,)):
                    for e in (eff or "").split(","):
                        if e:
                            found[e].append(f"{name} ({fpath}:{line})")
                for (callee,) in cur.execute("SELECT DISTINCT c.callee FROM calls c JOIN symbols s ON s.id=c.symbol WHERE s.name=? LIMIT 40", (name,)):
                    if callee not in seen:
                        nxt.append(callee)
            frontier = nxt[:limit]
        return {"symbol": symbol_name, "depth": depth, "effects": {k: v[:4] for k, v in found.items()}, "visited": len(seen)}

    def divisions_of(self, project: str = "") -> List[Dict[str, Any]]:
        cur = self.db.cursor()
        q = "SELECT f.division, COUNT(*) FROM files f JOIN repos r ON r.id=f.repo" + (" WHERE r.project=?" if project else "") + " GROUP BY f.division"
        rows = cur.execute(q, (project,) if project else ()).fetchall()
        return divisions.summarize(rows)

    def graph(self, project: str = ""):
        """networkx DiGraph of file-level import edges (nodes carry path, repo, division)."""
        import networkx as nx
        g = nx.DiGraph()
        cur = self.db.cursor()
        for fid, path, div, repo in cur.execute("SELECT f.id, f.path, f.division, r.name FROM files f JOIN repos r ON r.id=f.repo" + (" WHERE r.project=?" if project else ""),
                                                 (project,) if project else ()):
            g.add_node(fid, path=path, division=div, repo=repo)
        for s, d in cur.execute("SELECT src, dst FROM edges WHERE kind='import'"):
            if s in g and d in g:
                g.add_edge(s, d)
        return g

    def central_files(self, project: str = "", n: int = 10) -> List[Dict[str, Any]]:
        g = self.graph(project)
        if not g.number_of_nodes():
            return []
        try:
            import networkx as nx
            pr = nx.pagerank(g)
        except Exception:
            pr = {k: g.in_degree(k) for k in g}
        top = sorted(pr.items(), key=lambda kv: -kv[1])[:n]
        return [{"path": g.nodes[k]["path"], "repo": g.nodes[k]["repo"], "division": g.nodes[k]["division"], "rank": round(float(v), 4)} for k, v in top]

    def stats(self) -> Dict[str, Any]:
        cur = self.db.cursor()
        return {"repos": cur.execute("SELECT COUNT(*) FROM repos").fetchone()[0], "files": cur.execute("SELECT COUNT(*) FROM files").fetchone()[0],
                "symbols": cur.execute("SELECT COUNT(*) FROM symbols").fetchone()[0], "ui_strings": cur.execute("SELECT COUNT(*) FROM strings").fetchone()[0],
                "projects": [r[0] for r in cur.execute("SELECT DISTINCT project FROM repos")]}

    def close(self) -> None:
        try:
            self.db.commit()
            self.db.close()
        except Exception:
            pass


# ======================================================================================================== parsing
def _effects_of(body: str) -> Set[str]:
    return {k for k, rx in EFFECT_PATTERNS.items() if rx.search(body)}


def _parse(lang: str, text: str, rel: str) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[str]]:
    if lang == "python":
        return _parse_python(text)
    if lang in ("po",):
        return [], [{"line": text[:m.start()].count("\n") + 1, "text": m.group(1), "ctx": "msgid"} for m in re.finditer(r'^msgid\s+"([^"]{2,48})"', text, re.M) if _is_label(m.group(1))], []
    if lang == "rc":
        return [], [{"line": text[:m.start()].count("\n") + 1, "text": m.group(1).replace("&", ""), "ctx": "menu"}
                    for m in re.finditer(r'(?:MENUITEM|POPUP|PUSHBUTTON|DEFPUSHBUTTON|CHECKBOX|LTEXT|CAPTION)\s+"([^"]{2,48})"', text) if _is_label(m.group(1).replace("&", ""))], []
    if lang in ("xaml", "qtui", "html", "vue", "qml", "resx", "json"):
        pat = r'(?:Content|Header|Title|Text|Label|ToolTip|title|label|text|placeholder|aria-label|name)\s*[=:]\s*["\']([^"\']{2,48})["\']|>\s*([A-Z][\w &\-]{1,40})\s*<'
        out = []
        for m in re.finditer(pat, text):
            s = (m.group(1) or m.group(2) or "").replace("&", "")
            if _is_label(s):
                out.append({"line": text[:m.start()].count("\n") + 1, "text": s.strip(), "ctx": "markup"})
        syms = _decls(lang, text) if lang in ("vue", "qml") else []
        return syms, out[:3000], []
    return _parse_generic(lang, text)


def _parse_python(text: str) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[str]]:
    syms: List[Dict[str, Any]] = []
    strs: List[Dict[str, Any]] = []
    imps: List[str] = []
    try:
        tree = ast.parse(text)
    except Exception:
        return _parse_generic("python", text)
    lines = text.splitlines()

    def body_text(node) -> str:
        return "\n".join(lines[node.lineno - 1:getattr(node, "end_lineno", node.lineno)])

    class V(ast.NodeVisitor):
        def __init__(self) -> None:
            self.stack: List[Dict[str, Any]] = []

        def _sym(self, node, kind: str) -> Dict[str, Any]:
            parent = self.stack[-1]["name"] if self.stack else ""
            s = {"name": node.name, "kind": kind, "line": node.lineno, "end": getattr(node, "end_lineno", node.lineno), "parent": parent,
                 "doc": (ast.get_docstring(node) or "").split("\n")[0], "calls": [], "effects": _effects_of(body_text(node)) if kind != "class" else set()}
            syms.append(s)
            return s

        def visit_ClassDef(self, node):
            s = self._sym(node, "class")
            self.stack.append(s)
            for b in node.bases:
                if isinstance(b, (ast.Name, ast.Attribute)):
                    s["calls"].append(getattr(b, "id", getattr(b, "attr", "")))
            for st in node.body:
                if isinstance(st, ast.Assign) and isinstance(st.value, ast.Constant) and isinstance(st.value.value, str):
                    for t in st.targets:
                        if isinstance(t, ast.Name) and t.id in _LABEL_ATTRS and _is_label(st.value.value):
                            strs.append({"line": st.lineno, "text": st.value.value, "ctx": "label_attr"})
            self.generic_visit(node)
            self.stack.pop()

        def visit_FunctionDef(self, node):
            s = self._sym(node, "method" if self.stack and self.stack[-1]["kind"] == "class" else "function")
            self.stack.append(s)
            self.generic_visit(node)
            self.stack.pop()

        visit_AsyncFunctionDef = visit_FunctionDef

        def visit_Call(self, node):
            fname = getattr(node.func, "id", getattr(node.func, "attr", ""))
            if self.stack and fname:
                self.stack[-1]["calls"].append(fname)
            for kw in node.keywords:
                if kw.arg in _LABEL_KWARGS and isinstance(kw.value, ast.Constant) and isinstance(kw.value.value, str) and _is_label(kw.value.value):
                    strs.append({"line": kw.value.lineno, "text": kw.value.value, "ctx": "kwarg"})
            if node.args and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str) and _LABEL_FUNCS.search(fname or "") and _is_label(node.args[0].value):
                strs.append({"line": node.args[0].lineno, "text": node.args[0].value, "ctx": "call_arg"})
            self.generic_visit(node)

        def visit_Import(self, node):
            imps.extend(a.name for a in node.names)

        def visit_ImportFrom(self, node):
            if node.module:
                imps.append(node.module)

    V().visit(tree)
    return syms, strs, imps


_DECLS = {
    "js": [(r"\bfunction\s+([A-Za-z_$][\w$]*)\s*\(", "function"), (r"\bclass\s+([A-Za-z_$][\w$]*)", "class"),
           (r"\b(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=\s*(?:async\s*)?(?:\([^)]*\)|[A-Za-z_$][\w$]*)\s*=>", "function")],
    "c": [(r"^[A-Za-z_][\w \*]*\s+\**([A-Za-z_]\w*)\s*\([^;{)]*\)\s*\{", "function"), (r"\b(?:struct|class)\s+([A-Za-z_]\w*)\s*[{:]", "class")],
    "csharp": [(r"\b(?:public|private|protected|internal|static|async|override|virtual)[\w <>\[\],\.\? ]*\s+([A-Za-z_]\w*)\s*\([^;{)]*\)\s*\{?", "function"),
               (r"\bclass\s+([A-Za-z_]\w*)", "class")],
    "java": [(r"\b(?:public|private|protected|static|final)[\w <>\[\],\.\? ]*\s+([A-Za-z_]\w*)\s*\([^;{)]*\)\s*(?:throws [\w, ]+)?\{", "function"),
             (r"\bclass\s+([A-Za-z_]\w*)", "class")],
    "swift": [(r"\bfunc\s+([A-Za-z_]\w*)", "function"), (r"\b(?:class|struct|enum|protocol)\s+([A-Za-z_]\w*)", "class")],
    "kotlin": [(r"\bfun\s+(?:[\w<>\.]+\.)?([A-Za-z_]\w*)", "function"), (r"\b(?:class|object|interface)\s+([A-Za-z_]\w*)", "class")],
    "go": [(r"\bfunc\s+(?:\([^)]*\)\s*)?([A-Za-z_]\w*)", "function"), (r"\btype\s+([A-Za-z_]\w*)\s+(?:struct|interface)", "class")],
    "rust": [(r"\bfn\s+([A-Za-z_]\w*)", "function"), (r"\b(?:struct|enum|trait|impl)\s+([A-Za-z_]\w*)", "class")],
}
_DECLS["ts"] = _DECLS["js"]
_DECLS["cpp"] = _DECLS["c"]
_DECLS["vue"] = _DECLS["js"]
_DECLS["qml"] = _DECLS["js"]
_DECLS["python"] = [(r"^\s*def\s+([A-Za-z_]\w*)", "function"), (r"^\s*class\s+([A-Za-z_]\w*)", "class")]

_INCLUDE = re.compile(r'^\s*#\s*include\s*[<"]([^>"]+)[>"]|^\s*(?:import|from)\s+(?:[\w*{},\s]+\s+from\s+)?[\'"]([^\'"]+)[\'"]|require\(\s*[\'"]([^\'"]+)[\'"]\s*\)|^\s*using\s+([\w\.]+);|'
                      r'^\s*import\s+([\w\.]+)', re.M)
_STR_FUNCS = re.compile(r'\b(?:N_|IFACE_|CTX_IFACE_|TIP_|_|tr|QObject::tr|gettext|Text|Button|Label|Toggle|Link|Section|NavigationLink|MenuItem|addAction|AppendMenu|'
                        r'setText|setTitle|setToolTip|setLabel|CreateButton|MenuItemFor|Menu|Tab|TabItem|createMenu)\s*\(\s*(?:[A-Za-z_]\w*\s*,\s*)?"([^"\n]{2,48})"')
_STR_PROPS = re.compile(r'\b(?:label|title|text|tooltip|placeholder|aria-label|caption|name|header|Content|Text|Title|description)\s*[=:]\s*["\']([^"\'\n]{2,48})["\']')
_JSX_TEXT = re.compile(r">\s*([A-Z][A-Za-z0-9 &\-']{1,40})\s*<")


def _decls(lang: str, text: str) -> List[Dict[str, Any]]:
    pats = _DECLS.get(lang, [])
    found: List[Tuple[int, str, str]] = []
    for pat, kind in pats:
        for m in re.finditer(pat, text, re.M):
            nm = m.group(1)
            if nm in ("if", "for", "while", "switch", "return", "else", "catch", "sizeof", "main") and kind == "function":
                continue
            found.append((text[:m.start()].count("\n") + 1, nm, kind))
    found.sort()
    n_lines = text.count("\n") + 1
    out = []
    for i, (ln, nm, kind) in enumerate(found):
        end = (found[i + 1][0] - 1) if i + 1 < len(found) else n_lines
        out.append({"name": nm, "kind": kind, "line": ln, "end": max(ln, end), "calls": [], "effects": set()})
    return out


_CALL = re.compile(r"\b([A-Za-z_]\w{2,})\s*\(")
_KEYWORDS = {"if", "for", "while", "switch", "return", "catch", "sizeof", "function", "class", "def", "elif", "else", "with", "print", "len", "int", "str", "range",
             "super", "self", "this", "new", "await", "async", "lambda", "typeof", "None", "True", "False", "null", "true", "false"}


def _parse_generic(lang: str, text: str) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[str]]:
    syms = _decls(lang, text)
    lines = text.splitlines()
    for s in syms:
        body = "\n".join(lines[s["line"] - 1:s["end"]])
        s["effects"] = _effects_of(body)
        s["calls"] = [c for c in _CALL.findall(body)[:400] if c not in _KEYWORDS and c != s["name"]]
    strs: List[Dict[str, Any]] = []
    for rx, ctx in ((_STR_FUNCS, "call_arg"), (_STR_PROPS, "kwarg"), (_JSX_TEXT, "markup")):
        for m in rx.finditer(text):
            s = m.group(1).replace("&", "").strip()
            if _is_label(s):
                strs.append({"line": text[:m.start()].count("\n") + 1, "text": s, "ctx": ctx})
    imps = [next(g for g in m.groups() if g) for m in _INCLUDE.finditer(text) if any(m.groups())]
    return syms, strs[:4000], imps
