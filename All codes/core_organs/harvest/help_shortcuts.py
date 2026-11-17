"""
help_shortcuts -- the keyboard shortcuts a product PUBLISHES on its own public help page, as RAG leads.

    python -m core_organs.harvest.help_shortcuts run            fetch the known public shortcut pages (Google Docs / Sheets / Slides / Drive / Calendar / Gmail) and file them
    python -m core_organs.harvest.help_shortcuts url <url> <app_key> [--name N]

A page is read as tables of [action | shortcut]. Only Windows-style chords are kept (Ctrl / Alt / Shift / function keys); macOS symbols are dropped. Each shortcut becomes a hotkey row for the web app
(source 'web_help', trust 'web', verified False): it is what the vendor SAYS, not yet pressed on a live page. The page text is also filed as a document so a question can find it.
No sign-in and nothing but a public GET is involved.
"""
from __future__ import annotations

import argparse
import contextlib
import html as _html
import re
import sys
import time
import urllib.request
from typing import Any, Dict, List, Optional, Sequence, Tuple

PAGES: List[Tuple[str, str, str]] = [
    ("webapp:docs.google.com", "Google Docs", "https://support.google.com/docs/answer/179738?hl=en"),
    ("webapp:docs.google.com/spreadsheets", "Google Sheets", "https://support.google.com/docs/answer/181110?hl=en"),
    ("webapp:docs.google.com/presentation", "Google Slides", "https://support.google.com/docs/answer/1696717?hl=en"),
    ("webapp:drive.google.com", "Google Drive", "https://support.google.com/drive/answer/2563044?hl=en"),
    ("webapp:calendar.google.com", "Google Calendar", "https://support.google.com/calendar/answer/37113?hl=en"),
    ("webapp:mail.google.com", "Gmail", "https://support.google.com/mail/answer/6594?hl=en"),
]
_MAC = re.compile(r"[⌘⌥⌃⇧⌫↩]|\b(cmd|command|option|return)\b", re.I)
_CHORD = re.compile(r"^(?:(?:ctrl|alt|shift|win|meta)\s*\+\s*)*(?:[a-z0-9]|f\d{1,2}|enter|esc|escape|tab|space|home|end|del|delete|backspace|insert|page\s*up|page\s*down|pgup|pgdn|up|down|left|right|\[|\]|,|\.|/|;|'|\\|-|=|`)$", re.I)


def tables_of(page: str) -> List[Tuple[str, str]]:
    """[(action, shortcut)] from every two-cell table row."""
    out = []
    for r in re.findall(r"<tr[^>]*>(.*?)</tr>", page, re.S | re.I):
        cells = [re.sub(r"\s+", " ", _html.unescape(re.sub(r"<[^>]+>", " ", c))).strip() for c in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", r, re.S | re.I)]
        if len(cells) >= 2 and cells[0] and cells[1]:
            out.append((cells[0], cells[1]))
    return out


def windows_pairs(rows: Sequence[Tuple[str, str]]) -> List[Dict[str, str]]:
    pairs, seen = [], set()
    for action, chord in rows:
        c = re.sub(r"\s*\+\s*", "+", chord.strip())
        c = re.split(r"\s+(?:or|/)\s+", c)[0].strip()                          # 'Ctrl+b or Ctrl+B': the first
        if _MAC.search(chord) or len(c) > 24 or not _CHORD.match(c.replace(" ", "")) or len(action) < 3 or len(action) > 90:
            continue
        key = (action.lower(), c.lower())
        if key in seen:
            continue
        seen.add(key)
        pairs.append({"action": action, "keys": c})
    return pairs


def page_text(page: str, limit: int = 60000) -> str:
    t = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", page, flags=re.S | re.I)
    t = _html.unescape(re.sub(r"<[^>]+>", "\n", t))
    t = re.sub(r"\n\s*\n+", "\n", re.sub(r"[ \t]+", " ", t))
    return t[:limit]


def fetch(url: str, timeout: float = 40.0) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
    return urllib.request.urlopen(req, timeout=timeout).read().decode("utf-8", "ignore")


def file_pairs(rag: Any, key: str, name: str, url: str, pairs: Sequence[Dict[str, str]], text: str, run: str) -> Dict[str, Any]:
    from core_organs.harvest import bridge as BR, web_learn as WL
    rows = WL.hotkey_rows(key, pairs, BR)
    for r in rows:
        r["source"], r["context"] = "web_help", f"published on the vendor's public help page: {url}"
    res = {"pairs": len(pairs), "rows": len(rows), "new": 0, "document_chunks": 0}
    with WL.rag_lock():
        fresh = [r for r in rows if not rag.fast.find(key, r["task_pattern"], r["payload"])]
        with contextlib.suppress(Exception):
            for r in fresh:
                r["command_id"] = rag.lex.add_command(key, r["task_pattern"], archetype="web:help", source="web_help", trust="web")
            if fresh:
                rag.fast.upsert(fresh)
            res["new"] = len(fresh)
        with contextlib.suppress(Exception):
            rep = rag.proc.ingest_document(key, f"{name}: keyboard shortcuts published by the vendor.\n" + text, f"web_help:{run}", kind="web_doc", title=f"{name} keyboard shortcuts (help page)", trust="web")
            res["document_chunks"] = int(getattr(rep, "inserted", 0) or 0) + int(getattr(rep, "updated", 0) or 0)
    return res


def run(pages: Sequence[Tuple[str, str, str]] = PAGES) -> List[Dict[str, Any]]:
    from core_organs import rag as R
    rag = R.get_rag()
    stamp = time.strftime("%Y%m%d_%H%M%S")
    out = []
    for key, name, url in pages:
        try:
            page = fetch(url)
            pairs = windows_pairs(tables_of(page))
            res = file_pairs(rag, key, name, url, pairs, page_text(page), stamp)
        except Exception as e:
            res = {"error": f"{type(e).__name__}: {str(e)[:120]}"}
        res.update(key=key, name=name, url=url)
        out.append(res)
        print(f"[help-shortcuts] {name}: {res}", flush=True)
    return out


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["run", "url"])
    ap.add_argument("url", nargs="?", default="")
    ap.add_argument("key", nargs="?", default="")
    ap.add_argument("--name", default="")
    a = ap.parse_args(argv)
    if a.cmd == "run":
        run()
    else:
        run([(a.key, a.name or a.key, a.url)])
    return 0


if __name__ == "__main__":
    sys.exit(main())
