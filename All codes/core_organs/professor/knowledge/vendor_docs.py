"""
professor.knowledge.vendor_docs -- THE VENDOR'S OWN OFFLINE DOCUMENTATION, read from its official download (never run).

Some vendors publish their whole manual (and their scripting API reference) as one archive. Read once, it gives the Professor the complete guide - not the handful of pages a crawl
reaches - with every page's official URL kept as its citation:

  ingest_manual(app, zip_path, url_base, chapters)   the HTML pages of the chosen CHAPTERS (the parts about doing work, not about installing) -> the manual index (manual_rag)
  api_commands(zip_path, prefix)                       the command reference (e.g. 'bpy.ops.*' pages): id -> description + parameters  (pairs with a scripting bridge's command ids)
The archive is treated as untrusted data: extracted into its own folder, only .html text is read, nothing inside it is executed.
"""

from __future__ import annotations

import html
import json
import os
import re
import time
import zipfile
from typing import Any, Callable, Dict, List, Optional, Sequence

TITLE_RX = re.compile(r"<title>(.*?)</title>", re.I | re.S)
MAIN_RX = re.compile(r"<(?:article|div|main)[^>]*(?:role=\"main\"|itemprop=\"articleBody\")[^>]*>(.*?)</(?:article|div|main)>\s*(?:<footer|<div class=\"related|</div>\s*</div>\s*<footer|$)",
                     re.I | re.S)


def _title(raw: str) -> str:
    m = TITLE_RX.search(raw)
    t = html.unescape(re.sub(r"\s+", " ", m.group(1))).strip() if m else ""
    return re.sub(r"\s*[-—|]\s*Blender.*$", "", t) or t


def ingest_manual(app: str, zip_path: str, url_base: str, chapters: Sequence[str], ix: Any = None, log: Callable[[str], None] = print, limit: int = 4000) -> Dict[str, Any]:
    """Index the chosen chapters of an offline HTML manual. Returns counts. Pages already indexed under the same official URL are replaced (re-runnable)."""
    from . import manual_rag as MR
    own = ix is None
    ix = ix or MR.ManualIndex()
    t0 = time.time()
    rep: Dict[str, Any] = {"pages": 0, "chunks": 0, "skipped": 0, "by_chapter": {}}
    try:
        with zipfile.ZipFile(zip_path) as z:
            names = [n for n in z.namelist() if n.lower().endswith(".html")]
            root = os.path.commonprefix([n for n in names if "/" in n]).split("/")[0] + "/" if names and all("/" in n for n in names[:50]) else ""
            for n in names:
                rel = n[len(root):] if root and n.startswith(root) else n
                chap = rel.split("/", 1)[0]
                if chap not in chapters or rep["pages"] >= limit:
                    continue
                raw = z.read(n).decode("utf-8", "replace")
                title = _title(raw)
                body = MAIN_RX.search(raw)                                        # a manual page repeats the whole table of contents around its article: only the article is the page
                art = body.group(1) if body else raw
                # the manual's own mark-up becomes the step parser's: emphasis / interface terms / key caps -> **term**, its menu paths ('Edit ‣ Preferences') stay paths
                art = re.sub(r"<(em|kbd|strong|b)\b[^>]*>(.*?)</\1>", lambda m: "<b>" + re.sub(r"<[^>]+>", "", m.group(2)) + "</b>", art, flags=re.S)
                art = re.sub(r'<span class="menuselection">(.*?)</span>', lambda m: "<b>" + re.sub(r"<[^>]+>", "", m.group(1)) + "</b>", art, flags=re.S)
                content = MR._html_to_text(f"<h1>{html.escape(title)}</h1>" + art)
                r = ix.ingest_text(app, title, content, url_base.rstrip("/") + "/" + rel, "md", embed=False)
                if r.get("ok") and r.get("chunks", 0) > 0:
                    rep["pages"] += 1
                    rep["chunks"] += r["chunks"]
                    rep["by_chapter"][chap] = rep["by_chapter"].get(chap, 0) + 1
                else:
                    rep["skipped"] += 1
                if rep["pages"] % 200 == 0 and rep["pages"]:
                    log(f"  {rep['pages']} pages indexed ...")
    finally:
        if own:
            ix.close()
    rep["seconds"] = round(time.time() - t0, 1)
    return rep


OFFICE_KEYS = {"Excel": "excel", "Word": "winword", "PowerPoint": "powerpnt", "Outlook": "outlook"}       # the keys the manual index already files Office under (the program's file name)
_FRONT = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.S)


def _md_text(md: str) -> str:
    """A reference page's markdown as plain text: front matter dropped, links kept as their words, emphasis marks removed, tables kept as rows."""
    md = _FRONT.sub("", md, count=1)
    md = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", md)
    md = re.sub(r"[*_]{1,3}([^*_\n]+)[*_]{1,3}", r"\1", md)
    md = re.sub(r"^\|?\s*:?-{3,}.*$", "", md, flags=re.M)
    md = re.sub(r"^!include\[.*$", "", md, flags=re.M)                                           # docs-build directives, not content
    return re.sub(r"\n{3,}", "\n\n", md).strip()


def ingest_markdown_reference(zip_path: str, keys: Optional[Dict[str, str]] = None, url_base: str = "https://learn.microsoft.com/office/vba/api/", ix: Any = None,
                              log: Callable[[str], None] = print, limit: int = 40000) -> Dict[str, Any]:
    """An object-model reference published as markdown (MicrosoftDocs/VBA-Docs): every 'api/<App>.<Object>.<Member>.md' page of the chosen apps -> the manual index
    under that app's key, cited by its official URL; also returns the members themselves ({app_key: [{'name': 'Range.Value', 'kind': 'property', 'title': ...}]})
    so they can be filed as the app's commands. Re-runnable (pages are replaced by URL). The archive is data: only .md text is read."""
    from . import manual_rag as MR
    keys = keys or OFFICE_KEYS
    own = ix is None
    ix = ix or MR.ManualIndex()
    t0 = time.time()
    rep: Dict[str, Any] = {"pages": 0, "chunks": 0, "skipped": 0, "by_app": {}, "members": {}}
    try:
        with zipfile.ZipFile(zip_path) as z:
            for n in z.namelist():
                m = re.search(r"/api/([A-Za-z]+)\.([^/]+)\.md$", n)
                if not m or m.group(1) not in keys or rep["pages"] >= limit:
                    continue
                key, stem = keys[m.group(1)], m.group(1) + "." + m.group(2)
                raw = z.read(n).decode("utf-8", "replace")
                fm = _FRONT.match(raw)
                title = (re.search(r"^title:\s*(.+)$", fm.group(1), re.M).group(1).strip() if fm and re.search(r"^title:", fm.group(1), re.M) else stem)
                r = ix.ingest_text(key, title, f"# {title}\n\n" + _md_text(raw), url_base + stem.lower(), "md", embed=False)
                if r.get("ok") and r.get("chunks", 0) > 0:
                    rep["pages"] += 1
                    rep["chunks"] += r["chunks"]
                    rep["by_app"][key] = rep["by_app"].get(key, 0) + 1
                    k = re.search(r"\b(property|method|event|object|enumeration)\b", title, re.I)
                    rep["members"].setdefault(key, []).append({"name": m.group(2).replace("(object)", "").replace("(enumerations)", ""), "kind": (k.group(1).lower() if k else "page"),
                                                              "title": title, "url": url_base + stem.lower()})
                else:
                    rep["skipped"] += 1
                if rep["pages"] % 1000 == 0 and rep["pages"]:
                    log(f"  {rep['pages']} reference pages indexed ...")
    finally:
        if own:
            ix.close()
    rep["seconds"] = round(time.time() - t0, 1)
    return rep


def file_members(rag: Any, members: Dict[str, List[Dict[str, Any]]]) -> Dict[str, int]:
    """Object-model members as the app's commands in the RAG lexicon (what the app's own scripting can do, from its vendor's reference): trust 'official_doc', never 'verified'."""
    out: Dict[str, int] = {}
    for key, rows in members.items():
        for r in rows:
            if r["kind"] not in ("property", "method", "event", "object"):
                continue
            try:
                rag.lex.add_command(key, f"{r['name']} ({r['kind']})", archetype=f"om:{r['kind']}", source="vba_docs", trust="official_doc")
                out[key] = out.get(key, 0) + 1
            except Exception:
                pass
    return out


def file_api_commands(app: str, cmds: Dict[str, Dict[str, Any]], url_base: str, prefix: str = "bpy.ops.", ix: Any = None, rag: Any = None) -> Dict[str, int]:
    """A scripting API's command reference (api_commands) -> one manual page per command (what it does, every parameter, cited by the official page) and, given the
    RAG, the command in the app's lexicon. The 3D builder scripts against these ids; the planner and the question part can now read what each one takes."""
    from . import manual_rag as MR
    own = ix is None
    ix = ix or MR.ManualIndex()
    out = {"pages": 0, "commands": 0}
    try:
        for cid, d in sorted(cmds.items()):
            module = cid.split(".", 1)[0]
            text = f"# {prefix}{cid}\n\n{d.get('desc', '')}\n\n## Parameters\n\n" + "\n".join(f"- {p['name']} ({p.get('type', '')}): {p.get('desc', '')}" for p in d.get("params", []))
            r = ix.ingest_text(app, f"{prefix}{cid}", text, f"{url_base.rstrip('/')}/{prefix}{module}.html#{prefix}{cid}", "md", embed=False)
            out["pages"] += int(bool(r.get("ok")))
            if rag is not None:
                try:
                    rag.lex.add_command(app, f"{prefix}{cid}", archetype="api:operator", source="api_reference", trust="official_doc")
                    out["commands"] += 1
                except Exception:
                    pass
    finally:
        if own:
            ix.close()
    return out


def api_commands(zip_path: str, page_rx: str = r"bpy\.ops\.[a-z_]+\.html$") -> Dict[str, Dict[str, Any]]:
    """The command reference of a scripting API archive: {'mesh.primitive_cube_add': {'desc': ..., 'params': [{'name','type','desc'}]}} parsed from its HTML (Sphinx 'dl.py.function')."""
    out: Dict[str, Dict[str, Any]] = {}
    rx = re.compile(page_rx)
    with zipfile.ZipFile(zip_path) as z:
        for n in z.namelist():
            if not rx.search(n):
                continue
            raw = z.read(n).decode("utf-8", "replace")
            for m in re.finditer(r'<dt class="sig sig-object py" id="bpy\.ops\.([a-z_]+\.[a-z0-9_]+)">(.*?)</dt>\s*<dd>(.*?)</dd>', raw, re.S):
                op, sig, body = m.group(1), m.group(2), m.group(3)
                txt = lambda s: html.unescape(re.sub(r"<[^>]+>", " ", s)).strip()
                desc = re.sub(r"\s+", " ", txt(body.split("<dl", 1)[0]))[:400]
                params = []
                for pm in re.finditer(r"<li><p><strong>([a-z_0-9]+)</strong>\s*\((.*?)\)\s*[–-]\s*(.*?)</p>", body, re.S):
                    params.append({"name": pm.group(1), "type": re.sub(r"\s+", " ", txt(pm.group(2)))[:120], "desc": re.sub(r"\s+", " ", txt(pm.group(3)))[:200]})
                out[op] = {"desc": desc, "params": params}
    return out
