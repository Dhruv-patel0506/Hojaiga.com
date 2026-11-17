"""harvest.curriculum -- build the 25-archetype knowledge curriculum.

This is the coordinator for the knowledge-first learning loop:

    1. inspect the five RAG stores and identify which app archetypes are thin;
    2. acquire cited, app-specific learning material without depending on
       YouTube captions (official documentation and illustrated tutorials first,
       open-media clips only as a permitted fallback);
    3. add documents as non-executable teaching evidence and procedures as
       unverified hypotheses; and
    4. leave promotion to the live scanner/executor, which verifies a procedure
       against the installed application before it becomes a fast path.

The module deliberately does *not* make a general web claim executable, scan an
application repeatedly, or train a language model on unverified targets.  It
creates the curated RAG and grounded-pair queue consumed by ``train_qlora``.

Examples::

    python -m core_organs.harvest.curriculum plan
    python -m core_organs.harvest.curriculum collect --limit 3 --pages 3

``collect`` performs network reads and writes new local RAG/data records.  It
never signs in, submits a form, or downloads YouTube videos.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from collections import Counter
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set

from core_organs.rag import archetypes as A

# Cited, vendor-published starting pages for high-value gaps.  These are source
# locations rather than action rules; the harvester extracts current content
# from them and the scanner must still verify every executable route locally.
OFFICIAL_SOURCE_SEEDS: Dict[str, List[str]] = {
    "AutoCAD": ["https://help.autodesk.com/cloudhelp/2026/ENU/AutoCAD-OnBoarding/files/ACD_FOUNDATIONS_MAIN2.html"],
    "Modo": ["https://learn.foundry.com/modo/content/help/pages/user_guide.html"],
    "Logic Pro": ["https://support.apple.com/guide/logicpro/welcome/mac"],
    "Zoom Chat": ["https://support.zoom.com/hc/pb/article?id=zm_kb&sysparm_article=KB0059918"],
    "Discord": ["https://support.discord.com/hc/en-us/articles/360033931551-Getting-Started"],
    "File Explorer": ["https://support.microsoft.com/en-us/windows/experience/fileexplorer/fix-file-explorer-if-it-won-t-open-or-start"],
    "Visual Studio Code": ["https://code.visualstudio.com/docs/getstarted/overview"],
    "WhatsApp": ["https://faq.whatsapp.com/451924530376167/?cms_platform=windows-desktop"],
    "SSMS": ["https://learn.microsoft.com/sql/ssms/quickstarts/ssms-connect-query-sql-server"],
    "Outlook": ["https://support.microsoft.com/en-us/outlook/basic-tasks-in-outlook"],
    "OBS Studio": ["https://obsproject.com/kb/quick-start-guide"],
    "Windows Settings": ["https://support.microsoft.com/en-US/Windows/Experience/exploring-windows-settings"],
    "Windows Terminal": ["https://learn.microsoft.com/en-us/windows/terminal/install"],
    "Illustrator": ["https://helpx.adobe.com/ca/illustrator/desktop/get-started/learn-the-basics/workspace-overview.html"],
    "Premiere Pro": ["https://helpx.adobe.com/ph_fil/premiere-pro/how-to/create-project-import-media.html"],
}

# Keep named acquisition aligned with the application namespaces already used
# by the five RAG stores.  This prevents a tutorial for "WhatsApp" from being
# filed under a second, unreachable key when the scanner identifies the live
# client as ``whatsapp_desktop``.
APP_KEY_ALIASES: Dict[str, str] = {
    "WhatsApp": "whatsapp_desktop",
}

# Some vendors deliberately reject non-browser public readers (Adobe is one
# current example).  These compact, cited digests preserve only stable tutoring
# concepts extracted from the official page.  They are a low-quality *document*
# source -- never a procedure, action, fast path, or visual-training example --
# and the scanner still supplies the app-specific UI evidence on first use.
OFFICIAL_SOURCE_DIGESTS: Dict[str, Dict[str, str]] = {
    "Illustrator": {
        "url": "https://helpx.adobe.com/ca/illustrator/desktop/get-started/learn-the-basics/workspace-overview.html",
        "title": "Official Illustrator workspace overview (source digest)",
        "text": "Illustrator organizes work in a document window with a toolbar, panels, and a canvas. The toolbar is normally docked on the left and contains creation, editing, and navigation tools. The Properties and Control panels expose options that depend on the selected object or active tool. The contextual task bar offers the most relevant actions for the current workflow. Workspace presets can be selected or rearranged. Use the live scanner to identify the current tool, panel, and control locations before suggesting a click.",
    },
    "Premiere Pro": {
        "url": "https://helpx.adobe.com/premiere/desktop/organize-media/create-projects/create-new-project.html",
        "title": "Official Premiere project setup overview (source digest)",
        "text": "Premiere starts projects from its home screen. A project has a name, a storage location, optional template choices, media to import, and project settings. Imported media appears in the project workspace and can be organized before editing. A new sequence may use the first selected asset's settings. Treat project creation and media import as a user-reviewed workflow: inspect the current dialog and destination before any action that writes files or imports media.",
    },
}


def _fold(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (value or "").lower()).strip()


def _slug(value: str) -> str:
    return _fold(value).replace(" ", "_")


def _words(value: str) -> Set[str]:
    return {word for word in _fold(value).split() if len(word) > 1 and word not in {"app", "desktop", "microsoft", "windows"}}


def _matches_app_name(app_key: str, app_name: str) -> bool:
    """Conservative alias match for coverage accounting, never for execution."""
    key_words, name_words = _words(app_key), _words(app_name)
    if not key_words or not name_words:
        return False
    compact_key = "".join(sorted(key_words))
    compact_name = "".join(sorted(name_words))
    if compact_key == compact_name:
        return True
    return name_words <= key_words or key_words <= name_words


def _registered_domain_keys(root: str) -> Set[str]:
    """Read registered keys.  Registration alone is deliberately not coverage."""
    path = os.path.join(root, "rag", "domains.json")
    try:
        with open(path, encoding="utf-8") as handle:
            return set(json.load(handle))
    except (OSError, ValueError, TypeError):
        return set()


def _evidence_for(rag: Any, app_key: str) -> Dict[str, int]:
    """Counts actual stored learning evidence for one namespace.

    A domain can be registered before a network source succeeds.  Treating that
    bookkeeping record as knowledge caused a failed collection to suppress the
    next retry.  Coverage therefore requires at least one record in one of the
    live RAG stores (UI/graph, documentation/procedure, fast-path, recovery, or
    command/icon vocabulary).  The counts are only for curriculum accounting;
    they are never used to authorize an action.
    """
    graph = rag.graph.stats(app_key)
    proc = rag.proc.stats(app_key)
    recovery = rag.rec.stats(app_key)
    return {
        "graph_nodes": int(graph.get("nodes", 0)),
        "graph_edges": int(graph.get("edges", 0)),
        "observations": int(graph.get("observations", 0)),
        "documents": int(proc.get("chunks", 0)),
        "procedures": int(proc.get("procedures", 0)),
        "fast_paths": int(rag.fast.count(app_key)),
        "recovery": int(recovery.get("playbooks", 0)),
        "commands": int(rag.lex.n_commands(app_key)),
    }


def evidence_bearing_apps(app_keys: Iterable[str], rag: Any) -> Set[str]:
    """Return only keys with actual RAG evidence, ignoring registry-only rows."""
    out: Set[str] = set()
    for app_key in app_keys:
        try:
            if any(_evidence_for(rag, app_key).values()):
                out.add(app_key)
        except Exception:
            # A damaged optional store must not claim coverage.  The next
            # collection retry is safer than silently skipping a curriculum gap.
            continue
    return out


def registered_apps(root: str = "") -> Set[str]:
    """Return registered app keys that have real stored evidence, not just metadata."""
    base = root or os.environ.get("AI_STORAGE_ROOT") or r"D:\new_automation\data\ai_root"
    keys = _registered_domain_keys(base)
    if not keys:
        return set()
    rag = None
    try:
        # Make an isolated reader rather than reuse the process singleton: the
        # plan command should not initialise an LLM rewriter or alter executor
        # state.  `seed=False` also ensures a fresh empty root stays empty.
        from core_organs.rag import Rag, Storage
        rag = Rag(Storage(root=base), seed=False, icons=False)
        return evidence_bearing_apps(keys, rag)
    except Exception:
        return set()
    finally:
        if rag is not None:
            rag.close()


def coverage(known_apps: Iterable[str]) -> Dict[str, List[str]]:
    """Map evidence-bearing (or explicitly supplied) app keys to archetypes."""
    known = sorted({str(app) for app in known_apps if app})
    report: Dict[str, List[str]] = {}
    for archetype in A.ARCHETYPES:
        examples = list(archetype["train"]) + list(archetype["test"])
        report[archetype["id"]] = [key for key in known if any(_matches_app_name(key, name) for name in examples)]
    return report


def _target_for(archetype: Dict[str, Any], represented: Sequence[str]) -> str:
    """Choose a new example first; repeat a seed only when this class is unseen."""
    candidates = list(archetype["test"]) + list(archetype["train"]) if represented else list(archetype["train"]) + list(archetype["test"])
    for candidate in candidates:
        if not any(_matches_app_name(key, candidate) for key in represented):
            return candidate
    return candidates[0]


def plan(known_apps: Optional[Iterable[str]] = None) -> List[Dict[str, Any]]:
    """Return exactly one evidence-acquisition target for each universal pattern."""
    known = set(known_apps) if known_apps is not None else registered_apps()
    by_archetype = coverage(known)
    rows: List[Dict[str, Any]] = []
    for archetype in A.ARCHETYPES:
        represented = by_archetype[archetype["id"]]
        target = _target_for(archetype, represented)
        rows.append({
            "archetype": archetype["id"],
            "label": archetype["label"],
            "target": target,
            "app_key": _slug(target),
            "represented_by": represented,
            "priority": 100 if not represented else max(10, 70 - 10 * len(represented)),
            "acquisition_order": ["curriculum_seed", "official_documentation", "illustrated_tutorial", "open_media"],
            "source_urls": list(OFFICIAL_SOURCE_SEEDS.get(target, [])),
            "promotion_rule": "live verification on two distinct runs before a reusable fast path",
        })
    return sorted(rows, key=lambda row: (-row["priority"], row["archetype"]))


def rows_for_apps(app_names: Iterable[str], known_apps: Optional[Iterable[str]] = None) -> List[Dict[str, Any]]:
    """Build curriculum rows for explicitly requested applications.

    This is deliberately an acquisition helper, not a route authorizer: it maps
    an app name to one of the existing 25 patterns only to select source
    material.  The live UI signature remains the authority at execution time.
    """
    represented = coverage(set(known_apps) if known_apps is not None else registered_apps())
    rows: List[Dict[str, Any]] = []
    seen: Set[str] = set()
    for raw_name in app_names:
        target = str(raw_name or "").strip()
        app_key = APP_KEY_ALIASES.get(target, _slug(target))
        if not app_key or app_key in seen:
            continue
        seen.add(app_key)
        matches = [archetype for archetype in A.ARCHETYPES if any(
            _matches_app_name(app_key, example)
            for example in list(archetype["train"]) + list(archetype["test"])
        )]
        archetype = matches[0] if len(matches) == 1 else None
        archetype_id = archetype["id"] if archetype else "unclassified"
        rows.append({
            "archetype": archetype_id,
            "label": archetype["label"] if archetype else "Unclassified application",
            "target": target,
            "app_key": app_key,
            "represented_by": list(represented.get(archetype_id, [])),
            "priority": 110,
            "acquisition_order": ["curriculum_seed", "official_documentation", "illustrated_tutorial", "open_media"],
            "source_urls": list(OFFICIAL_SOURCE_SEEDS.get(target, [])),
            "promotion_rule": "live verification on two distinct runs before a reusable fast path",
        })
    return rows


def summary(rows: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    missing = [row["archetype"] for row in rows if not row["represented_by"]]
    return {
        "archetypes": len(rows),
        "represented": len(rows) - len(missing),
        "unrepresented": len(missing),
        "missing": missing,
        "targets": [{key: row[key] for key in ("archetype", "target", "app_key", "priority", "represented_by")} for row in rows],
    }


def _output_path(root: str) -> str:
    directory = os.path.join(root, "curriculum_runs")
    os.makedirs(directory, exist_ok=True)
    return os.path.join(directory, f"curriculum_{time.strftime('%Y%m%d_%H%M%S')}.json")


def ingest_official_digest(rag: Any, item: Dict[str, Any]) -> int:
    """Store one cited fallback digest as teaching context, never as an action."""
    digest = OFFICIAL_SOURCE_DIGESTS.get(str(item.get("target", "")))
    if not digest:
        return 0
    report = rag.proc.ingest_document(item["app_key"], digest["text"], digest["url"], kind="source_digest",
                                      title=digest["title"], trust="official_doc", build_procedures=False)
    return int(report.inserted + report.updated)


def collect(rows: Sequence[Dict[str, Any]], root: str = "", limit: int = 0, max_pages: int = 4, max_pairs: int = 12,
            include_page_clips: bool = False, include_open_media: bool = False, log: Any = print) -> Dict[str, Any]:
    """Harvest a bounded, priority-ordered curriculum batch and write its audit record."""
    from core_organs import rag as R
    from core_organs.harvest import web_search_failover as W
    from core_organs.harvest.paths import harvest_dir

    root = root or harvest_dir()[0]
    selected = list(rows[:limit] if limit else rows)
    rag = R.get_rag()
    outcomes: List[Dict[str, Any]] = []
    totals: Counter = Counter()
    try:
        for item in selected:
            rag.register_domain(item["app_key"], "desktop_app", {
                "why": "25-archetype curriculum acquisition",
                "archetype": item["archetype"],
                "target": item["target"],
            })
            try:
                result = W.harvest_app(item["target"], root=root, rag=rag, app_key=item["app_key"], max_pages=max_pages, max_pairs=max_pairs,
                                       with_clips=include_page_clips, with_open_video=include_open_media, source_urls=item.get("source_urls", ()), log=log)
                result = {key: result.get(key) for key in ("app", "engine", "pages", "steps", "documents", "procedures", "hotkeys", "pairs", "clip_pairs", "seconds", "urls", "sources", "search_failed")}
                result["success"] = bool(result.get("steps") or result.get("documents") or result.get("procedures"))
                if not result["success"]:
                    result["source_digest_documents"] = ingest_official_digest(rag, item)
                    result["documents"] = int(result.get("documents") or 0) + result["source_digest_documents"]
                    result["success"] = bool(result["source_digest_documents"])
            except Exception as exc:  # one unavailable source cannot end the curriculum
                result = {"success": False, "error": f"{type(exc).__name__}: {exc}"}
            outcome = {**item, "result": result}
            outcomes.append(outcome)
            for key in ("pages", "steps", "documents", "source_digest_documents", "procedures", "hotkeys", "pairs", "clip_pairs"):
                totals[key] += int(result.get(key) or 0)
            log(json.dumps({"archetype": item["archetype"], "target": item["target"], "success": result["success"],
                            **{key: result.get(key, 0) for key in ("pages", "steps", "documents", "procedures", "pairs")}}, ensure_ascii=False))
    finally:
        rag.close()
    report = {"created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "root": root,
              "policy": "cited documents/procedures are hypotheses; only live verified outcomes promote executable fast paths",
              "page_clips": include_page_clips,
              "open_media": include_open_media,
              "selected": len(selected), "successful": sum(bool(row["result"].get("success")) for row in outcomes),
              "totals": dict(totals), "outcomes": outcomes}
    path = _output_path(root)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2, ensure_ascii=False)
    report["report_path"] = path
    return report


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m core_organs.harvest.curriculum")
    parser.add_argument("command", choices=("plan", "collect"))
    parser.add_argument("--limit", type=int, default=0, help="number of archetypes to collect; 0 means all 25")
    parser.add_argument("--app", action="append", default=[], metavar="NAME", help="collect a named app instead of the 25-pattern plan; repeat for multiple apps")
    parser.add_argument("--pages", type=int, default=4, help="maximum source pages per app")
    parser.add_argument("--pairs", type=int, default=12, help="maximum grounded visual pairs per app")
    parser.add_argument("--root", default="", help="harvest root (defaults to the configured AI storage root)")
    parser.add_argument("--page-clips", action="store_true", help="also process clips embedded in accepted documentation pages; disabled by default because a clip can create many frames")
    parser.add_argument("--open-media", action="store_true", help="also process Internet Archive/Wikimedia clips; disabled by default because a clip can create many frames")
    args = parser.parse_args(argv)
    rows = rows_for_apps(args.app) if args.app else plan()
    if args.command == "plan":
        print(json.dumps(summary(rows), indent=2, ensure_ascii=False))
        return 0
    report = collect(rows, root=args.root, limit=args.limit, max_pages=args.pages, max_pairs=args.pairs, include_page_clips=args.page_clips, include_open_media=args.open_media)
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if report["successful"] else 2


if __name__ == "__main__":
    sys.exit(main())
