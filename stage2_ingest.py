"""
stage2_ingest -- fetch the real Windows Calculator / Notepad / Paint user guides into a
decompose-ready workbook. These apps are pre-installed so they were NOT in the WinGet
corpus; this pulls their actual documentation so trajectories are GUIDE-DERIVED, not
hand-written. Reuses guide_extractor's proven scrape pipeline (clean browser UA).

Output: three_app_guides.xlsx (schema decompose_guides reads).
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

import requests

import guide_extractor as _gx
from guide_extractor import scrape_page_to_markdown, is_guide_like, MAX_MARKDOWN_CHARS
from openpyxl import Workbook

UA_A = {"User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                       "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9"}
UA_B = {"User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:128.0) "
                       "Gecko/20100101 Firefox/128.0"),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5"}

GUIDES = [
    ("Calculator", "Windows Calculator user guide", "https://www.serverman.co.uk/windows-calculator/using-the-windows-calculator/"),
    ("Calculator", "Calculator memory functions M+ MS MR MC", "https://localdoc.org/blog/calculator-memory-keys-m-plus-mr-mc-guide.html"),
    ("Notepad", "Notepad help (File/Edit/View, Save As)", "https://support.microsoft.com/en-us/windows/apps/help-in-notepad"),
    ("Paint", "Microsoft Paint drawing guide", "https://windowsreport.com/microsoft-paint/"),
]
HEADERS = ["App Name", "Publisher", "Category", "Homepage", "Docs URL",
           "Guide Title", "Guide Markdown", "Word Count", "Status", "Source URL"]
OUT = "three_app_guides.xlsx"


def log(m):
    print(f"[stage2] {m}", flush=True)


def fetch(url, session):
    last = None
    for ua in (UA_A, UA_B):
        _gx.SCRAPER_HEADERS = ua
        try:
            return scrape_page_to_markdown(url, session)
        except Exception as exc:
            last = exc
    raise last


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    session = requests.Session()
    wb = Workbook(); ws = wb.active; ws.title = "App_Guides"
    ws.append(HEADERS)
    good = 0
    for app, title, url in GUIDES:
        try:
            got_title, md = fetch(url, session)
        except Exception as exc:
            log(f"FETCH-FAIL {app} {url[:50]} ({type(exc).__name__})"); continue
        wc = len(md.split())
        status = "extracted" if (wc >= 200 and is_guide_like(md)) else "weak"
        log(f"{status:9s} {app:10s} {wc:5d}w  {title[:40]}")
        if wc < 120:
            continue
        ws.append([app, "Microsoft", "System App", "", url, (got_title or title)[:200],
                   md[:MAX_MARKDOWN_CHARS], wc, status, url])
        good += 1
        time.sleep(0.5)
    wb.save(OUT)
    log(f"wrote {good} guide rows -> {Path(OUT).resolve()}")


if __name__ == "__main__":
    main()
