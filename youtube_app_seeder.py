r"""
youtube_app_seeder.py -- the NAME lists the YouTube harvester searches for: thousands of real desktop apps, web apps and websites, written as plain files.

    python youtube_app_seeder.py --sources winget,wiki,tranco,db --per-kind 10000
    -> <harvest>/youtube_rag/apps_app.txt   apps_web_app.txt   apps_website.txt   (one name per line, a stable shuffle so a run that stops early still covers the alphabet)

then, per kind (the harvester pads each name into a "full tutorial" search and keeps a resumable ledger):
    python youtube_video_rag_harvester.py index --apps-file <...>\apps_app.txt --kind app --per-query 5

Where the names come from (all free, all read-only, paced, no sign-in):
    winget    the winget community repository listing (`winget search`): ~15k packages -> one name per Publisher.Product, runtimes / SDKs / drivers / previews dropped   -> desktop apps
    wiki      Wikipedia category members through the official API (software, web applications, SaaS, DAWs, CAD, IDEs ...), lists / comparisons dropped                   -> desktop apps + web apps
    tranco    the Tranco research top-sites list (tranco-list.eu): registrable domains, CDN / ad / API infrastructure dropped                                            -> websites (written as domains)
    db        plain application names already inside the master RAG (read-only; the templated generator rows are not names and are dropped)                              -> by their domain

Nothing here opens YouTube. Counts are honest: a source that fails contributes 0 and says so; nothing is padded with invented names.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import re
import sqlite3
import subprocess
import sys
import time
import urllib.request
import zipfile
from pathlib import Path
from typing import Dict, List, Optional

ROOT = Path(__file__).resolve().parent
MASTER_DB = ROOT / "data" / "hojaiga_master_rag.db"
UA = "HojaigaResearchSeeder/1.0 (local research)"
KINDS = ("app", "web_app", "website")
DOMAIN_TO_KIND = {"desktop_app": "app", "web_app": "web_app", "website": "website"}

_NOISE = re.compile(r"redist|runtime|\bsdk\b|driver|hotfix|language pack|visual c\+\+|\bjre\b|\bjdk\b|build tools|codec|\bcli\b|\bpackage\b|\bupdater?\b|\binstaller\b|uninstall|"
                    r"\bbeta\b|\bnightly\b|\bpreview\b|\bcanary\b|\blts\b|\bportable\b|\bservice\b|\bagent\b|\bplugin\b|\bextension\b|\bmodule\b|\blibrary\b|\bbootstrapper\b", re.I)
_NAME_OK = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 .+&'_-]{1,44}$")
_CONCEPT = re.compile(r"\b(website|websites|software|service|services|application|applications|platform|industry|protocol|standard|system|systems|market|marketplace|company|foundation|"
                      r"network|networks|engine|framework|language|server|database|format|model|technology|computing|internet|online|digital|cloud|web)\s*$|^(foundation|employment|situational)\b", re.I)
_INFRA = re.compile(r"cdn|akamai|\bapi\b|static|gstatic|googleapis|cloudfront|doubleclick|adservice|analytics|\.gov\.|\.mil|\.edu\.|tracking|metric|telemetry|pixel|beacon", re.I)

WIKI_CATS = {"web_app": ["Web_applications", "Software_as_a_service", "Online_office_suites", "Project_management_software", "Customer_relationship_management_software",
                         "Video_hosting", "Social_networking_services", "Cloud_storage", "Webmail", "Online_marketplaces", "Collaborative_software", "Web_design"],
             "app": ["Windows_software", "Graphics_software", "Audio_editing_software", "Video_editing_software", "Computer-aided_design_software", "3D_graphics_software",
                     "Integrated_development_environments", "Text_editors", "Office_software", "Music_software", "Raster_graphics_editors", "Vector_graphics_editors",
                     "Computer-aided_engineering_software", "Screencasting_software", "Digital_audio_workstation_software", "Spreadsheet_software", "Database_management_systems"]}


def clean_name(n: str) -> str:
    n = re.sub(r"\s+\(.*?\)$", "", (n or "").strip())
    n = re.sub(r"\s+v?\d+(\.\d+)+.*$", "", n)
    return n.strip()


def seed_winget(limit: int = 0) -> List[str]:
    p = subprocess.run(["winget", "search", "--source", "winget", "--accept-source-agreements", ""], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=300)
    lines = (p.stdout or "").splitlines()
    hdr = next((i for i, l in enumerate(lines) if l.startswith("Name") and " Id" in l), None)
    if hdr is None:
        return []
    id_at = lines[hdr].index(" Id") + 1
    ver_at = lines[hdr].index(" Version") + 1 if " Version" in lines[hdr] else 10 ** 6
    out, seen = [], set()
    for l in lines[hdr + 2:]:
        if len(l) <= id_at:
            continue
        name, pid = clean_name(l[:id_at].strip()), l[id_at:ver_at].strip()
        base = ".".join(pid.split(".")[:2]).lower()
        if not name or base in seen or _NOISE.search(name) or _NOISE.search(pid) or not _NAME_OK.match(name):
            continue
        seen.add(base)
        out.append(name)
        if limit and len(out) >= limit:
            break
    return out


class WikiBlocked(Exception):
    pass


def _wiki_json(params: dict) -> dict:
    """One paced API call. Wikipedia answers a too-fast client with HTTP 429 (it did, after the first ~40 calls): that raises WikiBlocked and the source stops."""
    import requests
    time.sleep(1.5)
    r = requests.get("https://en.wikipedia.org/w/api.php", params=params, headers={"User-Agent": UA}, timeout=25)
    if r.status_code == 429:
        raise WikiBlocked(r.headers.get("Retry-After", "unknown"))                # a refusal ends this source for this run; nothing retries into it
    r.raise_for_status()
    return r.json()


def _wiki_members(cat: str, cmtype: str, cap: int) -> List[str]:
    res, cont = [], {}
    while len(res) < cap:
        j = _wiki_json({"action": "query", "list": "categorymembers", "cmtitle": f"Category:{cat}", "cmtype": cmtype, "cmlimit": 500, "format": "json", **cont})
        res += [m["title"] for m in j.get("query", {}).get("categorymembers", [])]
        if "continue" not in j:
            break
        cont = j["continue"]
    return res[:cap]


def seed_wikipedia(kind: str, per_cat: int = 600, depth: int = 1) -> List[str]:
    out, seen = [], set()

    def walk(cat: str, d: int) -> None:
        try:
            for t in _wiki_members(cat, "page", per_cat):
                n = clean_name(t)
                if re.match(r"^(List of|Comparison of|Category:|Template:|Outline of|History of|Timeline of)", n) or "disambiguation" in n.lower() or not _NAME_OK.match(n) or n.lower() in seen or _CONCEPT.search(n):
                    continue
                seen.add(n.lower())
                out.append(n)
            if d > 0:
                for sub in _wiki_members(cat, "subcat", 25):
                    walk(sub.replace("Category:", "").replace(" ", "_"), d - 1)
        except WikiBlocked:
            raise
        except Exception as e:
            print(f"  wiki {cat}: {type(e).__name__}", file=sys.stderr)
    try:
        for c in WIKI_CATS[kind]:
            walk(c, depth)
    except WikiBlocked as e:
        print(f"  wikipedia refused (429, Retry-After {e}); keeping the {len(out)} names found so far. Run again later.", file=sys.stderr)
    return out


def seed_tranco(n: int, cache: Path) -> List[str]:
    if not cache.is_file():
        cache.parent.mkdir(parents=True, exist_ok=True)
        req = urllib.request.Request("https://tranco-list.eu/top-1m.csv.zip", headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=120) as r:
            z = zipfile.ZipFile(io.BytesIO(r.read()))
        cache.write_text("\n".join(z.read(z.namelist()[0]).decode("utf-8", "replace").splitlines()[: n * 4]), encoding="utf-8")
    out = []
    for row in csv.reader(cache.read_text(encoding="utf-8").splitlines()):
        if len(row) < 2:
            continue
        dom = row[1].strip().lower()
        if len(dom.split(".")[0]) < 3 or _INFRA.search(dom):
            continue
        out.append(dom)
        if len(out) >= n:
            break
    return out


def seed_db(db: Path) -> Dict[str, List[str]]:
    out: Dict[str, List[str]] = {k: [] for k in KINDS}
    seen = set()
    try:
        c = sqlite3.connect(f"file:{db}?mode=ro", uri=True, timeout=10)
        for dom, goal in c.execute("SELECT domain, goal FROM causal_procedures_fts WHERE goal LIKE '% in %'"):
            kind = DOMAIN_TO_KIND.get(dom)
            parts_ = re.split(r"\s+in\s+", goal, flags=re.I)
            name = parts_[-1].strip() if len(parts_) > 1 else ""
            if kind and _NAME_OK.match(name) and " via " not in name and name.lower() not in seen and len(name.split()) <= 4 and not re.match(r"^(the|a|an)\b", name, re.I) \
                    and not re.search(r"\d{3,}|#|\bpane\b|\bmodal\b|\bpage\b|\bpalette\b", name, re.I):
                seen.add(name.lower())
                out[kind].append(name)
        c.close()
    except Exception as e:
        print(f"  db: {type(e).__name__}", file=sys.stderr)
    return out


def stable_shuffle(names: List[str]) -> List[str]:
    """Deterministic, so a resumed run sees the same order, and an early stop covers the whole alphabet instead of the A's."""
    uniq: Dict[str, str] = {}
    for n in (x.strip() for x in names):
        k = re.sub(r"[^a-z0-9]+", "", n.lower())
        if k and (k not in uniq or (len(n), n) < (len(uniq[k]), uniq[k])):      # one spelling per name, chosen by rule, not by arrival order
            uniq[k] = n
    return sorted(uniq.values(), key=lambda n: hashlib.md5(re.sub(r"[^a-z0-9]+", "", n.lower()).encode()).hexdigest())


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    ap.add_argument("--sources", default="winget,wiki,tranco", help="winget, wiki, tranco, db (db = names inside the master RAG: mostly UI-part names, off by default)")
    ap.add_argument("--per-kind", type=int, default=10000)
    ap.add_argument("--out-dir", default=str(ROOT / "data" / "ai_root" / "harvest" / "youtube_rag"))
    ap.add_argument("--db", default=str(MASTER_DB))
    ap.add_argument("--wiki-per-cat", type=int, default=600)
    ap.add_argument("--webapps-from-tranco", type=int, default=3000, help="how many of the top Tranco sites are also listed as web apps (by bare name)")
    ap.add_argument("--file", action="append", default=[], help="extra names: 'name' or 'name,kind' per line (kind = app | web_app | website)")
    a = ap.parse_args(argv)
    src, out_dir = set(a.sources.split(",")), Path(a.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    got: Dict[str, List[str]] = {k: [] for k in KINDS}
    report: Dict[str, Dict[str, int]] = {}
    if "db" in src:
        d = seed_db(Path(a.db))
        for k in KINDS:
            got[k] += d[k]
        report["db"] = {k: len(d[k]) for k in KINDS}
    if "winget" in src:
        try:
            w = seed_winget()
        except Exception as e:
            w = []
            print(f"  winget: {type(e).__name__}: {e}", file=sys.stderr)
        got["app"] += w
        report["winget"] = {"app": len(w)}
    if "wiki" in src:
        report["wiki"] = {}
        for k in ("web_app", "app"):
            w = seed_wikipedia(k, a.wiki_per_cat)
            got[k] += w
            report["wiki"][k] = len(w)
    if "tranco" in src:
        try:
            t = seed_tranco(a.per_kind, out_dir / "tranco_top.csv")
        except Exception as e:
            t = []
            print(f"  tranco: {type(e).__name__}: {e}", file=sys.stderr)
        got["website"] += t
        # the most visited sites are mostly interactive web apps (github, linkedin, notion, figma ...): their bare names also go to the web-app list. A heuristic: some are plain content sites,
        # and the index drops any name for which no tutorial turns up
        top_labels = [d.split(".")[0].capitalize() for d in t[: a.webapps_from_tranco] if _NAME_OK.match(d.split(".")[0])]
        got["web_app"] += top_labels
        report["tranco"] = {"website": len(t), "web_app_from_top": len(top_labels)}
    for f in a.file:
        for line in Path(f).read_text(encoding="utf-8").splitlines():
            p = [x.strip() for x in line.split(",")]
            if p and p[0]:
                got[p[1] if len(p) > 1 and p[1] in KINDS else "app"].append(p[0])
    final = {}
    for k in KINDS:
        prev = out_dir / f"apps_{k}.txt"                                  # additive: a run with fewer --sources never shrinks what an earlier run found
        old = [l.strip() for l in prev.read_text(encoding="utf-8").splitlines() if l.strip() and not l.startswith("#")] if prev.is_file() else []
        if k != "website":
            old = [n for n in old if not _CONCEPT.search(n)]               # an older run may have kept concept pages ("Foundation"); they are not products
        names = stable_shuffle(old + got[k])[: a.per_kind]
        (out_dir / f"apps_{k}.txt").write_text("\n".join(names) + "\n", encoding="utf-8")
        final[k] = len(names)
    print(json.dumps({"written": final, "target_each": a.per_kind, "by_source": report, "dir": str(out_dir)}, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
