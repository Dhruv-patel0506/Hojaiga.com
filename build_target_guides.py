"""
build_target_guides -- Phase-1 data fix.

The scraped master corpus (app_guides_master.xlsx) is ~6,600 obscure WinGet packages
and does NOT contain the mainstream desktop apps we actually want the model to learn
(VS Code, Blender, GIMP, OBS, Notepad++, ...). Feeding the difficulty ladder that
corpus yields ~40% empty apps because the source guides are thin.

This script curates a small set of REAL, feature-rich Windows desktop apps spanning
easy -> hard and pulls specific high-quality procedural manual pages for each, reusing
guide_extractor's proven scrape/clean pipeline. It writes a dedicated workbook in the
exact schema decompose_guides reads, so we can train Phase-1 on guides that actually
contain click/type steps.

It touches no window and no cursor -- pure offline ingestion, like Phase-1 must be.

Usage:
  python build_target_guides.py                 # scrape all target apps
  python build_target_guides.py --out target_apps_guides.xlsx
Then:
  $env:HOJAIGA_GUIDES_XLSX="target_apps_guides.xlsx"
  $env:HOJAIGA_TRAJ_DIR="trajectories_target"
  python decompose_guides.py --ladder 10 --engine ollama --throttle-ms 120
"""

from __future__ import annotations

import argparse
import re
import sys
import time
from pathlib import Path

import requests

# Reuse the proven scraper + cleaners; importing guide_extractor does NOT run its main()
# (module is __main__-guarded). We import the MODULE so we can swap the User-Agent:
# the default one self-identifies as a bot and gets 403'd by many doc-site WAFs.
try:
    import guide_extractor as _gx
    from guide_extractor import (
        scrape_page_to_markdown, is_guide_like, now_iso,
        MAX_MARKDOWN_CHARS,
    )
except Exception as exc:  # pragma: no cover
    print(f"could not import guide_extractor helpers: {exc}")
    raise

# Two clean browser identities; scrape_all retries with the second if the first 403s.
UA_A = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}
UA_B = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:128.0) "
                   "Gecko/20100101 Firefox/128.0"),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
}

try:
    from openpyxl import Workbook
    from openpyxl.cell.cell import ILLEGAL_CHARACTERS_RE
except ImportError:
    print("openpyxl is required: pip install openpyxl")
    raise

SHEET_NAME = "App_Guides"
# Header must contain at least "App Name" + "Guide Markdown" (decompose required cols).
HEADERS = ["App Name", "Publisher", "Category", "Homepage", "Docs URL",
           "Guide Title", "Guide Markdown", "Word Count", "Status", "Source URL"]


# Curated mainstream DESKTOP-GUI apps spanning easy -> hard, each with specific deep
# manual pages that contain numbered click/type steps. Chosen because their docs are
# static HTML (scrapeable) and teach real on-screen widget interaction. This is an
# operator selection of WHAT to learn from -- the trajectory CONTENT is still generated
# by the model in decompose_guides, never here.
TARGETS = [
    # ---- easy -------------------------------------------------------------
    {"app": "Notepad++", "pub": "Notepad++ Team", "cat": "Text Editor", "home": "https://notepad-plus-plus.org/",
     "urls": ["https://npp-user-manual.org/docs/searching/",
              "https://npp-user-manual.org/docs/editing/",
              "https://npp-user-manual.org/docs/preferences/"]},
    {"app": "7-Zip", "pub": "Igor Pavlov", "cat": "File Archiver", "home": "https://www.7-zip.org/",
     "urls": ["https://www.7-zip.org/manual/",
              "https://www.7-zip.org/7zpm.htm"]},

    # ---- moderate ---------------------------------------------------------
    {"app": "VLC media player", "pub": "VideoLAN", "cat": "Media Player", "home": "https://www.videolan.org/vlc/",
     "urls": ["https://www.videolan.org/vlc/features.html",
              "https://wiki.videolan.org/VLC_HowTo/",
              "https://wiki.videolan.org/Preferences/"]},
    {"app": "Audacity", "pub": "Audacity Team", "cat": "Audio Editor", "home": "https://www.audacityteam.org/",
     # manual.audacityteam.org 403s a scraper; the same manual pages are served raw from
     # GitHub (audacity/audacity-manual/manual/man/*.html) and bypass the WAF entirely.
     "urls": ["https://raw.githubusercontent.com/Audacity/audacity-manual/master/manual/man/amplify.html",
              "https://raw.githubusercontent.com/Audacity/audacity-manual/master/manual/man/making_a_recording.html"],
     "github": [{"repo": "Audacity/audacity-manual", "ref": "master", "dir": "manual/man",
                 "exts": [".html"], "limit": 18}]},
    {"app": "Inkscape", "pub": "Inkscape Project", "cat": "Vector Graphics", "home": "https://inkscape.org/",
     "urls": ["https://inkscape-manuals.readthedocs.io/en/latest/drawing-lines.html",
              "https://inkscape-manuals.readthedocs.io/en/latest/selecting-objects.html",
              "https://inkscape-manuals.readthedocs.io/en/latest/filling-colors.html"]},

    # ---- complex ----------------------------------------------------------
    {"app": "GIMP", "pub": "GNU Image Manipulation Program", "cat": "Image Editor", "home": "https://www.gimp.org/",
     "urls": ["https://docs.gimp.org/2.10/en/gimp-concepts-selection.html",
              "https://docs.gimp.org/2.10/en/gimp-using-paths.html",
              "https://docs.gimp.org/2.10/en/gimp-concepts-layer-modes.html",
              "https://docs.gimp.org/2.10/en/script-fu.html"]},
    {"app": "OBS Studio", "pub": "OBS Project", "cat": "Screen Recorder", "home": "https://obsproject.com/",
     "urls": ["https://obsproject.com/wiki/Quick-Start-Guide",
              "https://obsproject.com/docs/",
              "https://obsproject.com/wiki/Settings-Walkthrough"]},

    # ---- very complex -----------------------------------------------------
    {"app": "Blender", "pub": "Blender Foundation", "cat": "3D Modeler", "home": "https://www.blender.org/",
     "urls": ["https://docs.blender.org/manual/en/latest/getting_started/about/interfacing.html",
              "https://docs.blender.org/manual/en/latest/editors/3dview/index.html",
              "https://docs.blender.org/manual/en/latest/interface/header.html",
              "https://docs.blender.org/manual/en/latest/modeling/meshes/editing/vertex/index.html"]},
    {"app": "Microsoft Visual Studio Code", "pub": "Microsoft", "cat": "Code Editor", "home": "https://code.visualstudio.com/",
     # code.visualstudio.com intermittently 403s; the docs source is markdown in the
     # microsoft/vscode-docs repo (docs/**/*.md). Raw GitHub pull is clean, task-dense markdown.
     "urls": ["https://raw.githubusercontent.com/microsoft/vscode-docs/main/docs/editing/codebasics.md",
              "https://raw.githubusercontent.com/microsoft/vscode-docs/main/docs/editing/intellisense.md",
              "https://raw.githubusercontent.com/microsoft/vscode-docs/main/docs/configure/keybindings.md"],
     "github": [{"repo": "microsoft/vscode-docs", "ref": "main", "dir": "docs/editing",
                 "exts": [".md"], "limit": 8},
                {"repo": "microsoft/vscode-docs", "ref": "main", "dir": "docs/configure",
                 "exts": [".md"], "limit": 6}]},
    {"app": "LibreOffice Writer", "pub": "The Document Foundation", "cat": "Word Processor", "home": "https://www.libreoffice.org/",
     "urls": ["https://help.libreoffice.org/latest/en-US/text/shared/01/01010000.html",
              "https://help.libreoffice.org/latest/en-US/text/swriter/01/05130000.html"]},
]


def log(m: str) -> None:
    print(f"[targets] {m}", flush=True)


def xlsx_safe(s: str) -> str:
    return ILLEGAL_CHARACTERS_RE.sub(" ", s or "")


def _fetch(url: str, session: requests.Session):
    """scrape_page_to_markdown reads the module-global SCRAPER_HEADERS, so swapping that
    global is enough to present a clean browser identity. Retry once on a second UA."""
    last_exc = None
    for ua in (UA_A, UA_B):
        _gx.SCRAPER_HEADERS = ua
        try:
            return scrape_page_to_markdown(url, session)
        except Exception as exc:
            last_exc = exc
    if last_exc is not None:
        raise last_exc
    raise RuntimeError(f"no headers attempted for {url}")


# Markdown / reStructuredText served raw from GitHub is already clean source text; running
# it through the HTML scraper would strip its structure, so we read it verbatim instead.
RAW_TEXT_EXT = (".md", ".markdown", ".rst")


def _ingest(url: str, session: requests.Session):
    """Return (title, markdown) for either a raw source file or a normal HTML doc page."""
    low = url.lower().split("?")[0]
    if low.endswith(RAW_TEXT_EXT):
        r = session.get(url, headers=UA_A, timeout=30)
        r.raise_for_status()
        text = r.text
        m = re.search(r"^#[ \t]+(.+?)\s*$", text, flags=re.M)
        title = m.group(1).strip() if m else url.rsplit("/", 1)[-1]
        return title, text
    return _fetch(url, session)


def _list_github(spec: dict, session: requests.Session) -> list[str]:
    """Enumerate a GitHub directory (via the contents API) and return raw-file URLs, capped
    by spec['limit'] and filtered to spec['exts']. This is how one app fans out to many
    task pages for multi-page decomposition without hand-enumerating every URL."""
    repo, ref, path = spec["repo"], spec.get("ref", "main"), spec.get("dir", "")
    exts = tuple(e.lower() for e in spec.get("exts", [".md"]))
    limit = int(spec.get("limit", 12))
    api = f"https://api.github.com/repos/{repo}/contents/{path}?ref={ref}"
    try:
        r = session.get(api, headers={**UA_A, "Accept": "application/vnd.github+json"}, timeout=30)
        r.raise_for_status()
        entries = r.json()
    except Exception as exc:
        log(f"  GITHUB-LIST-FAIL {repo}/{path} ({type(exc).__name__})")
        return []
    out: list[str] = []
    for e in entries:
        if e.get("type") != "file" or not str(e.get("name", "")).lower().endswith(exts):
            continue
        out.append(f"https://raw.githubusercontent.com/{repo}/{ref}/{path}/{e['name']}")
        if len(out) >= limit:
            break
    return out


def target_urls(t: dict, session: requests.Session) -> list[str]:
    urls: list[str] = list(t.get("urls", []))
    for spec in t.get("github", []):
        urls.extend(_list_github(spec, session))
    return urls


def scrape_all(delay_s: float) -> list[dict]:
    session = requests.Session()
    rows: list[dict] = []
    for t in TARGETS:
        urls = target_urls(t, session)
        log(f"{t['app']:28s} -> {len(urls)} pages to scrape")
        for url in urls:
            try:
                title, md = _ingest(url, session)
            except Exception as exc:
                log(f"  FETCH-FAIL {t['app']:30s} {url[:60]}  ({type(exc).__name__})")
                rows.append(_row(t, url, "", "", 0, f"fetch_error:{type(exc).__name__}"))
                time.sleep(delay_s)
                continue
            wc = len(md.split())
            if wc < 60:
                log(f"  TOO-SHORT  {t['app']:30s} {url[:60]}  ({wc} words)")
                rows.append(_row(t, url, title, md[:2000], wc, "too_short"))
            else:
                status = "extracted" if is_guide_like(md) else "extracted_weak"
                log(f"  {status:15s} {t['app']:30s} {title[:40]:40s} ({wc}w)")
                rows.append(_row(t, url, title, md[:MAX_MARKDOWN_CHARS], wc, status))
            time.sleep(delay_s)
    return rows


def _row(t: dict, url: str, title: str, md: str, wc: int, status: str) -> dict:
    return {"app": t["app"], "pub": t["pub"], "cat": t["cat"], "home": t["home"],
            "docs": url, "title": (title or "")[:200], "md": md or "",
            "wc": wc, "status": status, "src": url}


def write_workbook(rows: list[dict], out: Path) -> None:
    wb = Workbook()
    ws = wb.active
    ws.title = SHEET_NAME
    ws.append(HEADERS)
    good = 0
    for r in rows:
        if not r["md"]:
            continue
        good += 1
        ws.append([xlsx_safe(r["app"]), xlsx_safe(r["pub"]), xlsx_safe(r["cat"]),
                   xlsx_safe(r["home"]), xlsx_safe(r["docs"]), xlsx_safe(r["title"]),
                   xlsx_safe(r["md"]), int(r["wc"]), xlsx_safe(r["status"]), xlsx_safe(r["src"])])
    wb.save(out)
    log(f"Wrote {good} usable guide rows ({len(rows)} scraped incl. failures) -> {out.resolve()}")


def main() -> int:
    ap = argparse.ArgumentParser(description="Build a curated Phase-1 guide workbook for mainstream desktop apps.")
    ap.add_argument("--out", default="target_apps_guides.xlsx")
    ap.add_argument("--delay", type=float, default=1.0, help="polite seconds between fetches")
    args = ap.parse_args()
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    log(f"Scraping {len(TARGETS)} target apps, {sum(len(t['urls']) for t in TARGETS)} guide pages...")
    rows = scrape_all(args.delay)
    write_workbook(rows, Path(args.out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
