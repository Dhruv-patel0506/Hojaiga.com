"""Production RAG / archetype audit for HoJaiga.

This is deliberately an *audit*, not an action runner.  It reads either the
built-in demonstration cases or a real AppScanner JSON capture, sends the
observed controls to the production ``ArchetypeRouter``, and queries the
production five-RAG store.  It never clicks, types, or promotes a shortcut.

Examples
--------
    python run_live_rag_verification.py
    python run_live_rag_verification.py --scan-json obs_scan_result.json --app-key obs_studio
    python run_live_rag_verification.py --json-out data/live_rag_audit.json

How to read the result
----------------------
``token_only`` is the fair zero-shot result: neither the app name nor window
title is supplied to the classifier.  ``production_candidate`` may use the
title/name as an additional supporting signal.  Neither number is a calibrated
probability.  A missing direct-app result is reported as ``SCAN_REQUIRED``;
the script exposes only a capped, non-executable archetype skeleton in that
case.  It must not be represented as proof that an unseen app was operated.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from core_organs import rag
from core_organs.rag import archetypes as A
from core_organs.rag.types import Query


@dataclass(frozen=True)
class Scenario:
    """A transparent manual-audit case, not a training example."""

    app: str
    tokens: Tuple[str, ...]
    goal: str
    expected_archetype: str = ""  # Human audit label only; never fed to the router.
    rag_app_key: str = ""          # Optional exact, previously verified RAG identity.


DEMONSTRATION_CASES: Tuple[Scenario, ...] = (
    Scenario("Microsoft Excel", ("role=grid", "Name Box", "fx", "Sheet1"),
             "Explain how to enter a value in a cell and save the workbook.", "spreadsheet"),
    Scenario("Grist", ("role=grid", "Column Header", "Cell"),
             "Explain how to enter a value in a cell.", "spreadsheet"),
    Scenario("Blender", ("webgl", "Outliner", "Position X", "Transform Gizmo"),
             "Explain how to move an object without deleting it.", "3d_modeler"),
    Scenario("Shapr3D Web", ("canvas", "Perspective", "Transform"),
             "Explain how to move an object without changing its dimensions.", "3d_modeler"),
    Scenario("Obsidian", ("contenteditable=true", "role=textbox", "Heading"),
             "Explain how to create and organize a note.", "note_taking"),
    Scenario("Quip", ("role=textbox", "RichEdit", "Document"),
             "Explain how to create a document and add a heading.", "word_processor"),
    Scenario("ComfyUI", ("react-flow", "node", "socket", "Queue Prompt"),
             "Explain the safe first step before queuing a workflow.", ""),
)


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_") or "unknown_app"


def _as_controls(tokens: Iterable[str]) -> List[Tuple[str, str]]:
    """Retain each scanner label as a production router control pair."""
    return [("observed", str(token)) for token in tokens if str(token).strip()]


def _ranked(router: A.ArchetypeRouter, signature: Mapping[str, Any], limit: int = 3) -> List[Dict[str, Any]]:
    return [{"archetype_id": aid, "archetype_name": A.BY_ID[aid]["label"], "relative_score": round(float(score), 4)}
            for aid, score in router.classify(dict(signature), top=limit)]


def _scanner_cases(paths: Sequence[Path], app_keys: Sequence[str] = ()) -> List[Scenario]:
    """Convert an AppScanner result (``elements`` with ``name``/``type``) to audit cases.

    The conversion is intentionally conservative: an arbitrary JSON file is
    rejected instead of being silently treated as a successful live scan.
    """
    if app_keys and len(app_keys) != len(paths):
        raise ValueError("--app-key must be supplied once for every --scan-json (or omitted entirely)")
    cases: List[Scenario] = []
    for index, path in enumerate(paths):
        data = json.loads(path.read_text(encoding="utf-8"))
        elements = data.get("elements")
        if not isinstance(elements, list):
            raise ValueError(f"{path}: expected an AppScanner result with an 'elements' list")
        controls: List[str] = []
        for item in elements:
            if not isinstance(item, Mapping):
                continue
            name, kind = str(item.get("name", "")).strip(), str(item.get("type", "")).strip()
            if name:
                controls.append(f"{kind}: {name}" if kind else name)
        if not controls:
            raise ValueError(f"{path}: scanner capture contains no named controls")
        title = str(data.get("window_title") or data.get("app_name") or path.stem.replace("_scan_result", ""))
        cases.append(Scenario(title, tuple(controls), "Explain the visible controls safely.", rag_app_key=app_keys[index] if app_keys else ""))
    return cases


def _evidence_summary(evidence: Sequence[Any], limit: int = 3) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for ev in evidence[:limit]:
        payload = getattr(ev, "payload", {}) or {}
        out.append({
            "kind": getattr(ev, "kind", ""),
            "trust": getattr(ev, "trust", ""),
            "confidence": round(float(getattr(ev, "confidence", 0.0)), 4),
            "citation": getattr(ev, "citation", ""),
            "source_kind": payload.get("source_kind", ""),
            "heading": payload.get("heading_path", ""),
            "excerpt": str(getattr(ev, "text", "")).replace("\n", " ")[:280],
        })
    return out


def _safe_count(fn: Any, app_key: str) -> int:
    try:
        return int(fn(app_key))
    except Exception:
        return 0


def _direct_app_key(store: Any, name: str, verified_key: str = "") -> str:
    """Use an exact RAG app key when one is registered; never borrow by fuzzy title."""
    if verified_key.strip():
        return verified_key.strip()
    resolved = store.resolve_app(name)
    return resolved or _slug(name)


def audit_case(store: Any, router: A.ArchetypeRouter, case: Scenario) -> Dict[str, Any]:
    controls = _as_controls(case.tokens)
    token_signature = {"app": "", "title": "", "controls": controls}
    production_signature = {"app": case.app, "title": case.app, "controls": controls}
    token_ranked = _ranked(router, token_signature)
    production_ranked = _ranked(router, production_signature)
    routing_assessment = router.assess(token_signature)
    top_id = token_ranked[0]["archetype_id"] if token_ranked else ""
    app_key = _direct_app_key(store, case.app, case.rag_app_key)

    # Direct evidence is intentionally app-partitioned.  A document about
    # Blender is not evidence about Shapr3D, even if they share an archetype.
    chunks = store.proc.query(app_key, case.goal, k=3)
    procedures = store.proc.find_procedures(app_key, case.goal, k=3)
    direct_counts = {
        "chunks": _safe_count(store.proc.chunk_count, app_key),
        "commands": _safe_count(store.lex.n_commands, app_key),
        "fast_paths": _safe_count(store.fast.count, app_key),
        "matching_chunks": len(chunks),
        "matching_procedures": len(procedures),
    }
    has_direct_app_knowledge = any((direct_counts["chunks"], direct_counts["commands"], direct_counts["fast_paths"]))
    has_direct_goal_evidence = bool(chunks or procedures)

    # This calls the public RAG router only in tutor mode.  It is useful for
    # auditing the actual store's evidence/gaps, but its returned plan is not
    # executed by this script.
    retrieval = store.retrieve(Query(
        text=case.goal,
        app_key=app_key,
        mode="tutor",
        budget_ms=800,
        allow_llm_rewrite=False,
    ))
    # A known app is not the same thing as a supported task. Only direct
    # passages/procedures relevant to this goal suppress the fallback here.
    skeleton = A.hint(case.app, case.goal, has_direct_goal_evidence, token_signature, router)
    archetype = A.BY_ID.get(top_id, {})
    signal_words = set(archetype.get("signals", ()))
    observed_words = set(router.words(token_signature))
    trap_hits = [label for _, label in controls if A.is_trap(top_id, label)]
    expected = case.expected_archetype

    return {
        "app": case.app,
        "rag_app_key": app_key,
        "goal": case.goal,
        "observed_control_count": len(controls),
        "observed_controls": [label for _, label in controls],
        "expected_archetype_for_manual_audit": expected or None,
        "token_only": {
            "candidates": token_ranked,
            "supporting_signal_words": sorted(observed_words & signal_words),
            "routing_assessment": {
                "status": routing_assessment["status"],
                "margin": routing_assessment["margin"],
                "note": "Margin and relative scores rank candidates; neither is a calibrated probability.",
            },
            "match_is_correct_against_manual_label": (top_id == expected) if expected else None,
        },
        "production_candidate": production_ranked[0] if production_ranked else None,
        "direct_app_evidence": {
            "counts": direct_counts,
            "chunks": _evidence_summary(chunks),
            "procedures": _evidence_summary(procedures),
            "router_evidence": _evidence_summary(retrieval.evidence),
            "router_gaps": retrieval.gaps,
            "router_plan_count_not_executed": len(retrieval.plans),
        },
        "archetype_context": {
            "action_grammar": archetype.get("grammar", []),
            "trap_guards": sorted(set(archetype.get("traps", ())) | set(A._UNIVERSAL_TRAPS)),
            "visible_trap_hits": trap_hits,
            "fallback_skeleton": skeleton,
        },
        "automation_verdict": (
            "DIRECT_GOAL_EVIDENCE_PRESENT__STILL_REQUIRES_LIVE_STATE_GROUNDING_AND_POSTCONDITION_CHECKS"
            if has_direct_goal_evidence else
            "APP_KNOWLEDGE_PRESENT_BUT_NO_DIRECT_GOAL_EVIDENCE__SCAN_AND_EXPLORE_REQUIRED"
            if has_direct_app_knowledge else
            "SCAN_REQUIRED__ONLY_A_NON_EXECUTABLE_ARCHETYPE_SKELETON_IS_AVAILABLE"
        ),
    }


def run_audit(cases: Sequence[Scenario]) -> Dict[str, Any]:
    store = rag.get_rag()
    router = A.ArchetypeRouter()
    results = [audit_case(store, router, case) for case in cases]
    labelled = [row for row in results if row["expected_archetype_for_manual_audit"]]
    correct = sum(1 for row in labelled if row["token_only"]["match_is_correct_against_manual_label"])
    return {
        "audit_kind": "read_only_production_rag_and_archetype_routing",
        "execution": "NO_UI_ACTIONS_WERE_ATTEMPTED",
        "warning": (
            "A structural match is not proof of live app autonomy.  A real autonomy claim requires a fresh scan, "
            "grounded controls, verified state transitions, and task-specific postconditions."
        ),
        "store": asdict(store.status()),
        "real_scanned_control_holdout_evaluation": A.evaluate_70_30_split(seeds=20),
        "manual_demo_token_only_accuracy": {
            "correct": correct,
            "labelled_cases": len(labelled),
            "note": "Small hand-labelled smoke test only; not a benchmark or a training score.",
        },
        "cases": results,
    }


def _print_human(report: Mapping[str, Any]) -> None:
    print("=" * 78)
    print("HOJAIGA PRODUCTION RAG & ARCHETYPE AUDIT (READ ONLY)")
    print("=" * 78)
    print(f"Actions attempted: {report['execution']}")
    print(f"RAG tables: {report['store']['tables']}")
    holdout = report["real_scanned_control_holdout_evaluation"]
    print("Real scanned-control holdout: "
          f"n={holdout.get('held_out_predictions', 0)}, "
          f"signals top-1={holdout.get('signals_only_top1', 'n/a')}, "
          f"top-3={holdout.get('signals_plus_fitted_top3', 'n/a')}")
    demo = report["manual_demo_token_only_accuracy"]
    print(f"Manual token-only smoke audit: {demo['correct']}/{demo['labelled_cases']} (not a benchmark)")
    for row in report["cases"]:
        candidate = row["token_only"]["candidates"][0] if row["token_only"]["candidates"] else {}
        direct = row["direct_app_evidence"]["counts"]
        print(f"\n[{row['app']}] token-only -> {candidate.get('archetype_name', 'none')} "
              f"({candidate.get('archetype_id', '')}; relative_score={candidate.get('relative_score', 0)})")
        print(f"  direct app key={row['rag_app_key']} evidence={direct}")
        print(f"  verdict: {row['automation_verdict']}")
        if row["archetype_context"]["visible_trap_hits"]:
            print(f"  visible safety guard hits: {row['archetype_context']['visible_trap_hits']}")
        for ev in row["direct_app_evidence"]["chunks"][:1]:
            print(f"  retrieved chunk: {ev['citation']} [{ev['source_kind'] or ev['kind']}]")
    print("\n" + report["warning"])


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Read-only audit of HoJaiga's production RAG and archetype router.")
    parser.add_argument("--scan-json", action="append", default=[], metavar="PATH",
                        help="AppScanner JSON capture to audit; may be supplied more than once.")
    parser.add_argument("--app-key", action="append", default=[], metavar="KEY",
                        help="Exact pre-verified RAG app key for the corresponding --scan-json; never inferred fuzzily.")
    parser.add_argument("--json-out", metavar="PATH", help="Write the complete audit report to this path.")
    parser.add_argument("--json", action="store_true", help="Print the complete report as JSON instead of a human summary.")
    args = parser.parse_args(argv)
    try:
        cases = _scanner_cases([Path(p) for p in args.scan_json], args.app_key) if args.scan_json else list(DEMONSTRATION_CASES)
        report = run_audit(cases)
    except Exception as exc:
        print(f"AUDIT FAILED: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2
    if args.json_out:
        out = Path(args.json_out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        _print_human(report)
        if args.json_out:
            print(f"\nFull audit saved to: {Path(args.json_out).resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
