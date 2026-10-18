"""
harvest.privacy -- nothing personal goes into a training set.

A scan photographs real applications, and real applications show the person: their user name in a folder path, their documents in a 'recent' list, their account initials, their notes. Two safeguards, both
generic (nothing here names an app or a person; the person's own identifiers are read from the machine):

  purge_app(root, key)      removes every pair, frame and section file of an application that must not be in the data at all (a file manager, a notebook)
  scrub(root, since)        reads the text of every frame made since `since` (OCR) and QUARANTINES the pairs whose frames show the person's identifiers (user name, profile folder, computer name, git
                            name / e-mail, any extra term given): the rows move to <dataset>_quarantine.jsonl and their frames are deleted
Quarantined data is kept out of training; nothing is sent anywhere.
"""
from __future__ import annotations

import contextlib
import getpass
import json
import os
import re
import subprocess
import time
from typing import Any, Dict, List, Optional, Sequence, Set


def personal_terms(extra: Sequence[str] = ()) -> List[str]:
    """The person's own identifiers, read from the machine: user name, profile folder name, computer name, git user name / e-mail local part; short or common words are dropped."""
    terms: Set[str] = set()
    for v in (os.environ.get("USERNAME"), getpass.getuser(), os.path.basename(os.environ.get("USERPROFILE", "")), os.environ.get("COMPUTERNAME")):
        if v:
            terms.add(v.strip())
    for key in ("user.name", "user.email"):
        with contextlib.suppress(Exception):
            out = subprocess.run(["git", "config", "--global", key], capture_output=True, text=True, timeout=5).stdout.strip()
            if out:
                terms.update(re.split(r"[\s@._-]+", out.split("@")[0] if key.endswith("email") else out))
    terms.update(e.strip() for e in extra if e.strip())
    common = {"user", "users", "admin", "administrator", "desktop", "laptop", "default", "owner", "home", "pc", "gmail", "com", "the"}
    return sorted({t for t in terms if len(t) >= 4 and t.lower() not in common})


_ACCOUNT_RX = re.compile(r"\b(account|profile|avatar|signed in|sign in|sign-in|your name|user menu|microsoft 365)\b", re.I)
_TERMS_CACHE: List[str] = []


def mask_personal(img: Any, controls: Sequence[Dict[str, Any]], pad: int = 4) -> Any:
    """A copy of `img` with the controls that show the PERSON painted over in neutral grey: account / profile / avatar buttons, initials badges (two or three capitals in the top strip), and any control whose
    name contains one of the person's own identifiers. The picture a model trains on keeps its layout; only who the person is disappears."""
    from PIL import ImageDraw
    if not _TERMS_CACHE:
        _TERMS_CACHE.extend(personal_terms())
        _TERMS_CACHE.append("")                                          # marks the cache as filled even when no identifier was found
    terms = [t.lower() for t in _TERMS_CACHE if t]
    out = img.copy()
    d = ImageDraw.Draw(out)
    for c in controls or []:
        name = str(c.get("name", ""))
        x, y, w, h = c["box"]
        initials = bool(re.fullmatch(r"[A-Z]{2,3}", name.strip())) and y < 100 and w < 120
        if _ACCOUNT_RX.search(name) or initials or any(t in name.lower() for t in terms):
            d.rectangle([x - pad, y - pad, x + w + pad, y + h + pad], fill=(128, 128, 128))
    return out


def _rx(terms: Sequence[str]) -> Optional[re.Pattern]:
    if not terms:
        return None
    pats = [re.escape(t) for t in terms]
    pats.append(r"[A-Za-z]:\\Users\\[^\\\s]+")
    pats.append(r"[\w.+-]+@[\w-]+\.[\w.-]+")                                  # an e-mail address
    return re.compile("|".join(pats), re.I)


def _ocr(path: str) -> str:
    from PIL import Image
    import pytesseract
    img = Image.open(path).convert("L")
    if max(img.size) > 1800:
        img.thumbnail((1800, 1800))
    return pytesseract.image_to_string(img, config="--psm 11")


def _read(path: str) -> List[Dict[str, Any]]:
    if not os.path.isfile(path):
        return []
    out = []
    for line in open(path, encoding="utf-8"):
        with contextlib.suppress(Exception):
            out.append(json.loads(line))
    return out


def _write(path: str, rows: Sequence[Dict[str, Any]], append: bool = False) -> None:
    with open(path, "a" if append else "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def _frames_of(r: Dict[str, Any], root: str) -> List[str]:
    m = r.get("meta", {})
    ps = [m.get("pre"), m.get("post")]
    for c in (r.get("messages", [{}, {}])[1].get("content", []) if len(r.get("messages", [])) > 1 else []):
        if c.get("type") == "image":
            ps.append(c.get("image"))
    return [os.path.join(root, p) for p in ps if isinstance(p, str) and p]


def _datasets(root: str) -> List[str]:
    d = os.path.join(root, "training")
    return [os.path.join(d, "ui_training_dataset.jsonl"), os.path.join(d, "ui_training_dataset_v2.jsonl")]


def purge_app(root: str, app_key: str) -> Dict[str, int]:
    """Every pair / frame / section file of `app_key` leaves the data (the rows are DELETED, not quarantined)."""
    n = {"rows": 0, "frames": 0}
    for ds in _datasets(root):
        rows = _read(ds)
        keep = [r for r in rows if r.get("meta", {}).get("app_key") != app_key]
        for r in rows:
            if r.get("meta", {}).get("app_key") == app_key:
                n["rows"] += 1
                for p in _frames_of(r, root):
                    with contextlib.suppress(Exception):
                        if os.path.isfile(p):
                            os.remove(p)
                            n["frames"] += 1
        if len(keep) != len(rows):
            _write(ds, keep)
    fdir = os.path.join(root, "frames", f"local_{app_key}")
    if os.path.isdir(fdir):
        for f in os.listdir(fdir):
            with contextlib.suppress(Exception):
                os.remove(os.path.join(fdir, f))
                n["frames"] += 1
        with contextlib.suppress(Exception):
            os.rmdir(fdir)
    with contextlib.suppress(Exception):
        os.remove(os.path.join(root, "ui_sections", f"{app_key}.json"))
    return n


def scrub(root: str, since: float = 0.0, extra_terms: Sequence[str] = (), apps: Optional[Sequence[str]] = None, progress: bool = True, all_sources: bool = False) -> Dict[str, Any]:
    """OCR the frames of local pairs made after `since` (epoch seconds; the frame file's own time) and quarantine the pairs that show the person's identifiers."""
    terms = personal_terms(extra_terms)
    rx = _rx(terms)
    rep: Dict[str, Any] = {"terms_checked": len(terms), "frames_read": 0, "pairs_quarantined": 0, "by_app": {}, "errors": 0}
    if rx is None:
        return rep
    bad_ids: Set[str] = set()
    t0 = time.time()
    seen_frames: Dict[str, bool] = {}
    for ds in _datasets(root)[:1]:                                              # the v1 file lists every pair once; v2 pairs share the pair_id
        for r in _read(ds):
            m = r.get("meta", {})
            if (m.get("source") != "local_uia" and not all_sources) or (apps and m.get("app_key") not in apps):
                continue
            pre = os.path.join(root, m.get("pre", ""))
            if not os.path.isfile(pre) or os.path.getmtime(pre) < since:
                continue
            hit = False
            for p in (pre, os.path.join(root, m.get("post", ""))):
                if not os.path.isfile(p):
                    continue
                if p not in seen_frames:
                    try:
                        seen_frames[p] = bool(rx.search(_ocr(p)))
                        rep["frames_read"] += 1
                    except Exception:
                        seen_frames[p] = False
                        rep["errors"] += 1
                hit = hit or seen_frames[p]
            if hit:
                bad_ids.add(m.get("pair_id", ""))
                rep["by_app"][m.get("app_key")] = rep["by_app"].get(m.get("app_key"), 0) + 1
            if progress and rep["frames_read"] and rep["frames_read"] % 50 == 0:
                print(f"[privacy] {rep['frames_read']} frames read, {len(bad_ids)} pairs flagged, {time.time() - t0:.0f}s", flush=True)
    if bad_ids:
        for ds in _datasets(root):
            rows = _read(ds)
            keep = [r for r in rows if r.get("meta", {}).get("pair_id") not in bad_ids]
            gone = [r for r in rows if r.get("meta", {}).get("pair_id") in bad_ids]
            if gone:
                _write(ds.replace(".jsonl", "_quarantine.jsonl"), [dict(r, quarantined="shows a personal identifier") for r in gone], append=True)
                _write(ds, keep)
                for r in gone:
                    for p in _frames_of(r, root):
                        with contextlib.suppress(Exception):
                            if os.path.isfile(p):
                                os.remove(p)
        rep["pairs_quarantined"] = len(bad_ids)
    return rep


if __name__ == "__main__":
    import sys
    from .paths import harvest_dir
    root = harvest_dir()[0]
    if len(sys.argv) > 1 and sys.argv[1] == "purge":
        for k in sys.argv[2:]:
            print(k, purge_app(root, k))
    else:
        since = float(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1] != "all" else 0.0
        print(json.dumps(scrub(root, since, all_sources="all" in sys.argv[1:] or (len(sys.argv) > 2 and sys.argv[2] == "all")), indent=1))
