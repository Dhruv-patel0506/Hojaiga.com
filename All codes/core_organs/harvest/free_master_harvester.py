"""
harvest.free_master_harvester -- apps -> YouTube tutorial search -> timestamped transcripts -> workbook sheets 1-2. $0, no API key, no video downloaded.

What differs from the original brief script, and why (measured 2026-10-16):
  * the Winget index (svrooij/winget-pkgs-index index.v2.csv) has columns PackageId, Version, Name, LastUpdate -- NO 'Tags'. The brief's filter would raise KeyError, be swallowed, and silently queue
    only the seed apps. Here the index is used as it is: seed apps first (matched to their PackageId), then the most recently maintained entries, tier = -1 ("not yet classified by a scan").
  * youtube-transcript-api 1.x removed get_transcript(); the instance API fetch() is used (the old one is tried as a fallback).
  * resumable (state file), batchable (start / max_apps), rate-limited, every network step injectable (Net) so the whole thing runs offline in tests.
Honest statuses are recorded per video: Downloaded | Cached | No_Subtitles | Blocked | Error:<type>.
"""
from __future__ import annotations

import io
import json
import os
import re
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from .paths import harvest_dir, workbook_path

WINGET_CSV = "https://raw.githubusercontent.com/svrooij/winget-pkgs-index/main/index.v2.csv"
SHEET_APPS, SHEET_VIDEOS = "1_Master_1000_Apps", "2_YouTube_And_Transcripts"

CORE_APPS: List[Dict[str, Any]] = [
    # Tier 0: simple native Win32
    {"app_name": "Notepad", "tier": 0, "category": "Text Editor"}, {"app_name": "Windows Calculator", "tier": 0, "category": "Utility"},
    {"app_name": "MS Paint", "tier": 0, "category": "Graphics"}, {"app_name": "Snipping Tool", "tier": 0, "category": "Utility"},
    {"app_name": "7-Zip", "tier": 0, "category": "Archiver"}, {"app_name": "VLC Media Player", "tier": 0, "category": "Media"},
    # Tier 1: modern desktop / web-wrapped / comms
    {"app_name": "WhatsApp Desktop", "tier": 1, "category": "Communication"}, {"app_name": "Discord", "tier": 1, "category": "Communication"},
    {"app_name": "Slack", "tier": 1, "category": "Communication"}, {"app_name": "Microsoft Teams", "tier": 1, "category": "Communication"},
    {"app_name": "Spotify", "tier": 1, "category": "Media"}, {"app_name": "Windows 11 Settings", "tier": 1, "category": "System"},
    {"app_name": "Zoom", "tier": 1, "category": "Communication"}, {"app_name": "Notion", "tier": 1, "category": "Productivity"},
    # Tier 2: multi-panel and ribbon suites
    {"app_name": "Microsoft Word", "tier": 2, "category": "Office Suite"}, {"app_name": "Microsoft Excel", "tier": 2, "category": "Office Suite"},
    {"app_name": "Microsoft PowerPoint", "tier": 2, "category": "Office Suite"}, {"app_name": "OBS Studio", "tier": 2, "category": "Broadcasting"},
    {"app_name": "Visual Studio Code", "tier": 2, "category": "Development"}, {"app_name": "Audacity", "tier": 2, "category": "Audio Editing"},
    {"app_name": "GIMP", "tier": 2, "category": "Image Editing"}, {"app_name": "Inkscape", "tier": 2, "category": "Vector Graphics"},
    {"app_name": "Postman", "tier": 2, "category": "Development"},
    # Tier 3: blind-tree 3D / CAD / NLE / canvas suites
    {"app_name": "Blender 3D", "tier": 3, "category": "3D Modeling"}, {"app_name": "AutoCAD", "tier": 3, "category": "CAD Engineering"},
    {"app_name": "FreeCAD", "tier": 3, "category": "CAD Engineering"}, {"app_name": "DaVinci Resolve", "tier": 3, "category": "Video Editing"},
    {"app_name": "Unreal Engine 5", "tier": 3, "category": "Game Engine"}, {"app_name": "Unity Editor", "tier": 3, "category": "Game Engine"},
    {"app_name": "Adobe Photoshop", "tier": 3, "category": "Design"}, {"app_name": "SolidWorks", "tier": 3, "category": "CAD Engineering"},
]
_EXCLUDE = ("redistributable", "sdk", "driver", "runtime", "font", "cli", " cli", "library", "package", "plugin", "extension", "toolkit", "framework", "language pack", "updater", "service")


_CATALOG: Optional[Dict[str, Any]] = None


def app_key_of(name: str) -> str:
    """The key the rest of the project uses for an application: the Professor's app catalog when it knows the name, a slug otherwise."""
    low = re.sub(r"[^a-z0-9]+", " ", name.lower()).strip()
    global _CATALOG
    if _CATALOG is None:
        try:
            here = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "professor", "data", "app_catalog.json")
            _CATALOG = json.load(open(here, encoding="utf-8"))
        except Exception:
            _CATALOG = {"apps": []}
    cat = _CATALOG
    for a in cat.get("apps", []):
        names = {re.sub(r"[^a-z0-9]+", " ", str(a.get("name", "")).lower()).strip()} | {re.sub(r"[^a-z0-9]+", " ", str(x).lower()).strip() for x in a.get("aliases", [])}
        if low in names and a.get("key"):
            return str(a["key"])
    return re.sub(r"[^a-z0-9]+", "_", low).strip("_")


@dataclass
class Net:
    """Everything that touches the network, replaceable in tests."""
    http_get: Callable[[str], Optional[bytes]] = None            # url -> bytes | None
    search: Callable[[str, int], List[Dict[str, Any]]] = None    # (query, n) -> [{id,title,duration,view_count,uploader}]
    transcript: Callable[[str, List[str]], List[Dict[str, Any]]] = None   # (video_id, languages) -> [{text,start,duration}]
    sleep: Callable[[float], None] = time.sleep

    def __post_init__(self):
        self.http_get = self.http_get or _http_get
        self.search = self.search or _yt_search
        self.transcript = self.transcript or _yt_transcript


def _http_get(url: str, timeout: float = 30.0) -> Optional[bytes]:
    try:
        import requests
        r = requests.get(url, timeout=timeout, headers={"User-Agent": "HoJaiga-harvester/1.0 (+local research tool)"})
        return r.content if r.status_code == 200 else None
    except Exception:
        return None


def _yt_search(query: str, n: int) -> List[Dict[str, Any]]:
    import yt_dlp
    opts = {"quiet": True, "no_warnings": True, "extract_flat": True, "skip_download": True, "socket_timeout": 20}
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(f"ytsearch{n}:{query}", download=False)
    return [{"id": e.get("id"), "title": e.get("title", ""), "duration": e.get("duration") or 0, "view_count": e.get("view_count") or 0, "uploader": e.get("uploader") or e.get("channel") or ""}
            for e in (info or {}).get("entries", []) if e and e.get("id")]


class TranscriptUnavailable(Exception):
    pass


def _yt_transcript(video_id: str, languages: List[str]) -> List[Dict[str, Any]]:
    import youtube_transcript_api as Y
    try:
        api = Y.YouTubeTranscriptApi()
        if hasattr(api, "fetch"):
            return [dict(text=s["text"], start=s["start"], duration=s["duration"]) for s in api.fetch(video_id, languages=languages).to_raw_data()]
        return Y.YouTubeTranscriptApi.get_transcript(video_id, languages=languages)         # youtube-transcript-api < 1.0
    except Exception as exc:
        name = type(exc).__name__
        if "Block" in name or "TooMany" in name or "RequestBlocked" in name:
            raise PermissionError(name)
        if name == "NoTranscriptFound":                       # captions exist, just not in the languages asked for: say which, so the person can choose (translate, or skip)
            try:
                other = [t.language_code for t in Y.YouTubeTranscriptApi().list(video_id)]
            except Exception:
                other = []
            raise TranscriptUnavailable("other:" + ",".join(other) if other else name)
        raise TranscriptUnavailable(name)


# ---- apps ---------------------------------------------------------------------------------------------------------------------------------------------
def load_winget(net: Net) -> List[Dict[str, Any]]:
    """The Winget index as rows {app_name, package_id, last_update}. [] when unreachable (the caller records that)."""
    raw = net.http_get(WINGET_CSV)
    if not raw:
        return []
    import csv
    rows = []
    for r in csv.DictReader(io.StringIO(raw.decode("utf-8-sig", "replace"))):
        name = (r.get("Name") or "").strip()
        if name and r.get("PackageId"):
            rows.append({"app_name": name, "package_id": r["PackageId"], "last_update": r.get("LastUpdate", "")})
    return rows


def build_app_list(net: Net, limit: int = 1000) -> Dict[str, Any]:
    """Seed apps first (matched to Winget PackageIds when the name is there), then the most recently maintained user-facing Winget entries."""
    wg = load_winget(net)
    by_name = {re.sub(r"[^a-z0-9]+", " ", w["app_name"].lower()).strip(): w for w in wg}
    apps: List[Dict[str, Any]] = []
    seen = set()
    for a in CORE_APPS:
        key = re.sub(r"[^a-z0-9]+", " ", a["app_name"].lower()).strip()
        w = by_name.get(key) or by_name.get(key.replace(" desktop", "").replace(" 3d", "").strip())
        apps.append(dict(a, app_key=app_key_of(a["app_name"]), package_id=w["package_id"] if w else "", source="seed"))
        seen.add(key)
    extra = 0
    for w in sorted(wg, key=lambda x: x["last_update"], reverse=True):
        if len(apps) >= limit:
            break
        low = re.sub(r"[^a-z0-9]+", " ", w["app_name"].lower()).strip()
        if not low or low in seen or len(low) < 3 or any(k in low for k in _EXCLUDE):
            continue
        seen.add(low)
        apps.append({"app_name": w["app_name"], "tier": -1, "category": "", "app_key": app_key_of(w["app_name"]), "package_id": w["package_id"], "source": "winget"})
        extra += 1
    return {"apps": apps, "winget_rows": len(wg), "winget_ok": bool(wg), "from_winget": extra}


# ---- videos + transcripts -----------------------------------------------------------------------------------------------------------------------------
_GENERIC = {"windows", "microsoft", "ms", "desktop", "app", "application", "studio", "editor", "pro", "the", "adobe", "free", "tool", "11", "10", "3d", "engine", "a", "for", "of", "and"}


def app_tokens(app_name: str) -> List[str]:
    """The words that identify an application in a title / transcript: its name without the generic ones ('Windows Calculator' -> ['calculator'], 'MS Paint' -> ['paint'])."""
    toks = [t for t in re.findall(r"[a-z0-9]+", app_name.lower()) if t not in _GENERIC and len(t) > 2]
    return toks or [t for t in re.findall(r"[a-z0-9]+", app_name.lower()) if len(t) > 1]


def on_topic(app_name: str, title: str, transcript_text: str = "", min_mentions: int = 5) -> bool:
    """A tutorial is about the application if its TITLE names it, or the speaker names it at least `min_mentions` times. (A search for 'Windows Calculator shortcuts' also returns general Windows
    shortcut videos; filing those under the calculator would put clipboard and virtual-desktop advice into the calculator's partition.)"""
    toks = app_tokens(app_name)
    low_t = (title or "").lower()
    if any(re.search(rf"\b{re.escape(t)}", low_t) for t in toks):
        return True
    text = (transcript_text or "").lower()
    return sum(len(re.findall(rf"\b{re.escape(t)}", text)) for t in toks) >= min_mentions


def pick_videos(found: List[Dict[str, Any]], per_app: int, min_s: int = 120, max_s: int = 3600) -> List[Dict[str, Any]]:
    """Tutorials of a useful length, most-viewed first, one per id."""
    seen, out = set(), []
    for v in sorted(found, key=lambda v: -(v.get("view_count") or 0)):
        d = v.get("duration") or 0
        if v["id"] in seen or (d and not (min_s <= d <= max_s)):
            continue
        seen.add(v["id"])
        out.append(v)
        if len(out) >= per_app:
            break
    return out


def transcript_path(root: str, app_key: str, video_id: str) -> str:
    return os.path.join(root, "transcripts_json", f"{app_key}__{video_id}.json")


def fetch_transcript(net: Net, root: str, app_key: str, video_id: str, languages=("en", "en-US", "en-GB")) -> Dict[str, Any]:
    path = transcript_path(root, app_key, video_id)
    if os.path.isfile(path):
        try:
            n = len(json.load(open(path, encoding="utf-8")))
        except Exception:
            n = 0
        return {"status": "Cached", "segments": n, "path": path}
    try:
        segs = net.transcript(video_id, list(languages))
    except PermissionError as exc:
        return {"status": f"Blocked:{exc}", "segments": 0, "path": ""}
    except TranscriptUnavailable as exc:
        why = str(exc)
        return {"status": ("Other_Language:" + why[6:]) if why.startswith("other:") else "No_Subtitles", "segments": 0, "path": "", "why": why}
    except Exception as exc:
        return {"status": f"Error:{type(exc).__name__}", "segments": 0, "path": ""}
    if not segs:
        return {"status": "No_Subtitles", "segments": 0, "path": ""}
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(segs, f, ensure_ascii=False)
    os.replace(tmp, path)
    return {"status": "Downloaded", "segments": len(segs), "path": path}


# ---- the run --------------------------------------------------------------------------------------------------------------------------------------------
def run_harvester(max_apps: int = 5, videos_per_app: int = 2, start: int = 0, net: Optional[Net] = None, root: str = "", delay_s: float = 1.0, app_limit: int = 1000,
                  queries=("{app} full tutorial for beginners step by step english", "{app} shortcuts tips and tricks workflow english"), only_apps: Optional[List[str]] = None,
                  write_workbook: bool = True, stop_on_block: bool = True) -> Dict[str, Any]:
    """Harvest one batch: apps[start : start+max_apps]. Returns a report. Safe to re-run: finished apps are skipped, transcripts are cached, sheets are merged."""
    net = net or Net()
    root = root or harvest_dir()[0]
    os.makedirs(os.path.join(root, "transcripts_json"), exist_ok=True)
    state_path = os.path.join(root, "harvest_state.json")
    try:
        state = json.load(open(state_path, encoding="utf-8"))
    except Exception:
        state = {"done_apps": {}}
    plan = build_app_list(net, app_limit)
    apps = plan["apps"]
    if only_apps:
        want = {a.lower() for a in only_apps}
        apps = [a for a in apps if a["app_name"].lower() in want or a["app_key"] in want]
    batch = apps[start:start + max_apps]
    video_rows: List[Dict[str, Any]] = []
    stats = {"apps_processed": 0, "apps_skipped_done": 0, "videos": 0, "downloaded": 0, "cached": 0, "no_subtitles": 0, "other_language": 0, "off_topic": 0, "blocked": 0, "errors": 0}
    blocked = False
    for app in batch:
        if app["app_key"] in state["done_apps"]:
            stats["apps_skipped_done"] += 1
            continue
        found: List[Dict[str, Any]] = []
        for q in queries:
            try:
                found += net.search(q.format(app=app["app_name"]), max(videos_per_app, 3))
            except Exception as exc:
                stats["errors"] += 1
                video_rows.append({"app_name": app["app_name"], "app_key": app["app_key"], "video_id": "", "transcript_status": f"SearchError:{type(exc).__name__}"})
            net.sleep(delay_s)
        for v in pick_videos(found, videos_per_app):
            t = fetch_transcript(net, root, app["app_key"], v["id"])
            st = t["status"]
            if st in ("Downloaded", "Cached"):
                try:
                    body = " ".join(s.get("text", "") for s in json.load(open(t["path"], encoding="utf-8")))
                except Exception:
                    body = ""
                if not on_topic(app["app_name"], v["title"], body):
                    off = os.path.join(root, "transcripts_json", "_off_topic")
                    os.makedirs(off, exist_ok=True)
                    os.replace(t["path"], os.path.join(off, os.path.basename(t["path"])))          # quarantined, not deleted: the person can overrule the gate
                    st, t = "Off_Topic", {"status": "Off_Topic", "segments": 0, "path": ""}
            stats["videos"] += 1
            stats["downloaded" if st == "Downloaded" else "cached" if st == "Cached" else "no_subtitles" if st == "No_Subtitles" else "other_language" if st.startswith("Other_Language") else "off_topic" if st == "Off_Topic" else
                  "blocked" if st.startswith("Blocked") else "errors"] += 1
            video_rows.append({"app_name": app["app_name"], "app_key": app["app_key"], "video_id": v["id"], "title": v["title"], "url": f"https://www.youtube.com/watch?v={v['id']}",
                               "duration_sec": v.get("duration", 0), "view_count": v.get("view_count", 0), "channel": v.get("uploader", ""), "transcript_status": st,
                               "transcript_segments": t["segments"], "local_json_path": os.path.relpath(t["path"], root).replace("\\", "/") if t["path"] else ""})
            if st.startswith("Blocked"):
                blocked = True
                break
            net.sleep(delay_s)
        if blocked and stop_on_block:
            break                                              # YouTube is rate-limiting this address: stop and let the person decide; do not hammer it
        state["done_apps"][app["app_key"]] = {"ts": time.time(), "videos": len([r for r in video_rows if r["app_key"] == app["app_key"]])}
        stats["apps_processed"] += 1
    with open(state_path, "w", encoding="utf-8") as f:
        json.dump(state, f)
    out = {"root": root, "winget_ok": plan["winget_ok"], "winget_rows": plan["winget_rows"], "apps_planned": len(plan["apps"]), "batch": [a["app_name"] for a in batch], "stats": stats, "blocked": blocked}
    if write_workbook:
        out["workbook"] = write_sheets(root, plan["apps"], video_rows)
    return out


def write_sheets(root: str, apps: List[Dict[str, Any]], videos: List[Dict[str, Any]]) -> str:
    """Sheets 1-2, MERGED with whatever the workbook already holds (other sheets, earlier batches) -- never overwritten blindly."""
    import pandas as pd
    path = workbook_path(root)
    existing: Dict[str, Any] = {}
    if os.path.isfile(path):
        try:
            existing = pd.read_excel(path, sheet_name=None)
        except Exception:
            existing = {}
    sheets = dict(existing)
    sheets[SHEET_APPS] = _merge(existing.get(SHEET_APPS), pd.DataFrame(apps), ["app_key"])
    if videos or SHEET_VIDEOS in existing:
        sheets[SHEET_VIDEOS] = _merge(existing.get(SHEET_VIDEOS), pd.DataFrame(videos), ["app_key", "video_id"])
    _save(path, sheets)
    return path


def _merge(old, new, keys):
    import pandas as pd
    if old is None or len(old) == 0:
        return new
    if new is None or len(new) == 0:
        return old
    both = pd.concat([old, new], ignore_index=True)
    return both.drop_duplicates(subset=[k for k in keys if k in both.columns], keep="last").reset_index(drop=True)


def _save(path: str, sheets: Dict[str, Any]) -> None:
    import pandas as pd
    tmp = path + ".tmp.xlsx"
    with pd.ExcelWriter(tmp, engine="openpyxl") as w:
        for name, df in sheets.items():
            df.to_excel(w, sheet_name=name[:31], index=False)
    os.replace(tmp, path)


if __name__ == "__main__":
    import sys
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 3
    print(json.dumps(run_harvester(max_apps=n), indent=2, default=str))
