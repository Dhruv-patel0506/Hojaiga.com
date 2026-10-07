r"""
boot_health.py — the honest boot health line for start_hojaiga.bat (work order [5]).

One line per SERVICE and per ORGAN: ready / degraded / absent, with the reason.
Nothing here starts anything - the .bat owns starting; this module PROBES what the
bat (or a previous session) actually left running, and never claims a component is
healthy because its import line exists.

Services probed over HTTP (same endpoints the organs themselves use):
  * ollama            :11434  /api/tags
  * vision-QwenVL     :8081   /health + /props   (llama.cpp Qwen VL tier; model name read live)
  * gatekeeper        :11435  /api/tags        (proxy passthrough to Ollama)

Organs probed with a cheap functional check (import + the symbol the CrewAI flow
actually calls; where the check can be done without side effects, it is):
  * organ_01  CrewAI engine        -> CrewAIEngine class + crewai installed + no dead
                                      legacy scan path shadowing fast_scan
  * fast_scan                      -> deep_scan / deep_scan_legacy_shape present
  * organ_31  grounding            -> VisualGroundingEngine instantiable; 7B-preferred
                                      tier live only when :8081 answers (else it degrades
                                      to the Ollama eye - reported, not hidden)
  * organ_49  scan knowledge       -> ENABLED + open_session present
  * organ_48  behavior model       -> BehaviorModel opens a (throwaway) DB, EffectorLadder builds
  * pointer_sentinel               -> preflight() returns a sample (the guard works)
  * env_guard                      -> preflight() (printed FIRST, before everything else)

Exit code: 0 when every CRITICAL item (env_guard, ollama, organ_01, fast_scan) is not
"absent"; 1 otherwise - so the .bat can tell a real boot from a broken one.
"""

from __future__ import annotations

import json
import logging
import os
import sys
import time
import urllib.request

# Path bootstrap: works both as `python ...\core_organs\boot_health.py` from the .bat
# (script dir is core_organs) and as `from core_organs import boot_health`.
_HERE = os.path.dirname(os.path.abspath(__file__))
for _p in (_HERE, os.path.dirname(_HERE)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

logging.getLogger("hojaiga").setLevel(logging.ERROR)   # health lines, not organ chatter

READY, DEGRADED, ABSENT = "ready", "degraded", "absent"


def _get(url: str, timeout_s: float = 3.0, headers=None):
    """(status, snippet) or (None, error string)."""
    try:
        req = urllib.request.Request(url, headers=headers or {"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:
            return int(resp.getcode()), resp.read(160).decode("utf-8", "replace")
    except Exception as exc:                                   # noqa: BLE001
        return None, f"{type(exc).__name__}: {exc}"


# --------------------------------------------------------------------------- services

def check_services() -> list:
    rows = []

    # Probe RAW Ollama on :11434. Do NOT reuse HOJAIGA_BRAIN_URL here: the launcher points
    # BRAIN_URL at the authenticated Gatekeeper (:11435), which answers a bare GET /api/tags
    # with 401 - that falsely marked a perfectly-healthy Ollama as ABSENT/critical and printed
    # "BOOT INCOMPLETE" even though CrewAI was using it fine. The Gatekeeper gets its own
    # authenticated probe below.
    ollama_base = os.environ.get("HOJAIGA_OLLAMA_URL", "http://127.0.0.1:11434").split("/api")[0]
    code, body = _get(ollama_base + "/api/tags")
    if code == 200:
        n = body.count('"name"')
        rows.append(("SERVICE", "ollama :11434", READY, f"{n} model(s) listed"))
    elif code is None:
        rows.append(("SERVICE", "ollama :11434", ABSENT, body))
    else:
        rows.append(("SERVICE", "ollama :11434", DEGRADED, f"HTTP {code}"))

    vis_base = os.environ.get("HOJAIGA_VISION_PRECISION_ENDPOINT", "http://127.0.0.1:8081").rstrip("/")
    vis_port = vis_base.rsplit(":", 1)[-1]
    code, body = _get(vis_base + "/health")
    # Honest label: ask llama-server WHICH model it actually loaded (/props model_path), so this
    # line reads Qwen3-VL-8B after the upgrade and Qwen2.5-VL-7B before it - the probe reports
    # what the .bat left running, never a hard-coded name that could mis-report the boot.
    vname = "vision llama.cpp"
    try:
        with urllib.request.urlopen(vis_base + "/props", timeout=3.0) as _pr:
            _mp = str(json.loads(_pr.read(65536).decode("utf-8", "replace")).get("model_path") or "")
        if _mp:
            vname = "vision " + os.path.basename(_mp).replace(".gguf", "")
    except Exception:                                       # noqa: BLE001 - /props is optional
        pass
    if code == 200:
        rows.append(("SERVICE", f"{vname} :{vis_port}", READY, "llama-server healthy"))
    elif code is None:
        rows.append(("SERVICE", f"vision llama.cpp :{vis_port}", ABSENT, body))
    else:
        rows.append(("SERVICE", f"vision llama.cpp :{vis_port}", DEGRADED, f"HTTP {code}"))

    gk = os.environ.get("HOJAIGA_GATEKEEPER_URL", "http://127.0.0.1:11435")
    # the gatekeeper is the branded proxy: clients pass the organ-side validation header
    # (same constant gatekeeper_wire uses - we read it from that module, never restate it)
    try:
        from core_organs import gatekeeper_wire as _gw
        hdrs = {"Content-Type": "application/json", "X-Hojaiga-Validation": _gw.GATEKEEPER_SECRET}
    except Exception:                                          # noqa: BLE001
        hdrs = {"Content-Type": "application/json"}
    code, body = _get(gk + "/api/tags", headers=hdrs)           # proxy passthrough to Ollama
    if code == 200:
        rows.append(("SERVICE", "gatekeeper :11435", READY, "proxying /api/tags"))
    elif code is None:
        rows.append(("SERVICE", "gatekeeper :11435", ABSENT, body))
    else:
        rows.append(("SERVICE", "gatekeeper :11435", DEGRADED, f"HTTP {code} (handler answered)"))

    return rows


# --------------------------------------------------------------------------- organs

def _check_organ_01(service_rows: list) -> tuple:
    try:
        from core_organs import organ_01_crewai_engine as o1
    except Exception as exc:                                   # noqa: BLE001
        return ABSENT, f"import failed: {type(exc).__name__}: {exc}"
    if not getattr(o1, "_HAS_CREWAI", False):
        return ABSENT, "crewai package not installed - the brain cannot run"
    if not hasattr(o1, "CrewAIEngine"):
        return ABSENT, "CrewAIEngine symbol missing"
    # no dead legacy path shadowing the modern scanner: the flow must route scans to
    # fast_scan and must NOT still drive the legacy serial orchestrator anywhere.
    src = open(o1.__file__, encoding="utf-8", errors="replace").read()
    modern = "fast_scan.deep_scan_legacy_shape" in src
    legacy_calls = src.count("EyeAndBrainOrchestrator(")
    if not modern:
        return DEGRADED, "CrewAIEngine present but scans no longer route through fast_scan"
    if legacy_calls:
        return DEGRADED, f"legacy organ_30 orchestrator still instantiated {legacy_calls}x (shadows fast_scan)"
    ollama_ok = any(r[1].startswith("ollama") and r[2] == READY for r in service_rows)
    if not ollama_ok:
        return DEGRADED, "engine wired but Ollama :11434 not answering"
    return READY, "CrewAI engine + fast_scan routing, no legacy shadow"


def _check_fast_scan() -> tuple:
    try:
        from core_organs import fast_scan
    except Exception as exc:                                   # noqa: BLE001
        return ABSENT, f"import failed: {type(exc).__name__}: {exc}"
    missing = [n for n in ("deep_scan", "deep_scan_legacy_shape", "wait_for_vision") if not hasattr(fast_scan, n)]
    if missing:
        return DEGRADED, f"missing {missing}"
    return READY, "deep_scan + legacy-shape adapter present"


def _check_organ_31(service_rows: list) -> tuple:
    try:
        from core_organs.organ_31_visual_perception import VisualGroundingEngine
    except Exception as exc:                                   # noqa: BLE001
        return ABSENT, f"import failed: {type(exc).__name__}: {exc}"
    try:
        VisualGroundingEngine()                                # cheap ctor, no network
    except Exception as exc:                                   # noqa: BLE001
        return DEGRADED, f"engine not instantiable: {type(exc).__name__}: {exc}"
    seven_b_up = any("vision" in r[1] and r[2] == READY for r in service_rows)
    if seven_b_up:
        return READY, "grounding ready, precision tier (:8081) live"
    return DEGRADED, "grounding ready but :8081 down -> falls back to the Ollama 3B eye (honest degrade)"


def _check_organ_49() -> tuple:
    try:
        from core_organs import organ_49_scan_knowledge as o49
    except Exception as exc:                                   # noqa: BLE001
        return ABSENT, f"import failed: {type(exc).__name__}: {exc}"
    if not getattr(o49, "ENABLED", False):
        return DEGRADED, "HOJAIGA_SCAN_KNOWLEDGE=0 - side-by-side knowledge is switched off"
    if not hasattr(o49, "open_session"):
        return DEGRADED, "open_session symbol missing"
    return READY, "scan+knowledge side-by-side session API live"


def _check_organ_48() -> tuple:
    import tempfile
    import uuid
    try:
        from core_organs import organ_48_app_behavior_model as bm
    except Exception as exc:                                   # noqa: BLE001
        return ABSENT, f"import failed: {type(exc).__name__}: {exc}"
    db = os.path.join(tempfile.gettempdir(), "hj_boot_" + uuid.uuid4().hex[:6] + ".db")
    try:
        m = bm.BehaviorModel(db)
        ladder = bm.EffectorLadder(m)
        tiers = list(getattr(ladder, "DEFAULTS", {}) or getattr(bm.EffectorLadder, "DEFAULTS", {}))
        m.close()
    except Exception as exc:                                   # noqa: BLE001
        return DEGRADED, f"model opens but ladder fails: {type(exc).__name__}: {exc}"
    finally:
        for suf in ("", "-wal", "-shm"):
            try:
                os.remove(db + suf)
            except OSError:
                pass
    return READY, f"BehaviorModel + EffectorLadder ready ({len(tiers)} verb lanes)"


def _check_pointer_sentinel() -> tuple:
    try:
        from core_organs import pointer_sentinel as ps
    except Exception as exc:                                   # noqa: BLE001
        return ABSENT, f"import failed: {type(exc).__name__}: {exc}"
    try:
        rep = ps.preflight(seconds=0.6)
    except Exception as exc:                                   # noqa: BLE001
        return DEGRADED, f"preflight crashed: {type(exc).__name__}: {exc}"
    if not rep:
        return DEGRADED, "preflight returned no sample"
    hook = "on" if rep.get("hook") else "off"
    return (READY if hook == "on" else DEGRADED), f"preflight {ps.classify(rep)} (hook={hook}, hardware={rep.get('hardware_events')})"


def _check_env_guard() -> tuple:
    try:
        from core_organs import env_guard
    except Exception as exc:                                   # noqa: BLE001
        return ABSENT, f"import failed: {type(exc).__name__}: {exc}", ""
    ok, msg = env_guard.preflight()
    return (READY if ok else DEGRADED), msg, msg

def check_organs(service_rows: list) -> list:
    import contextlib
    import io

    eg = _check_env_guard()
    rows = [("ORGAN", "env_guard", eg[0], eg[1])]
    probes = [
        ("organ_01 crewai engine", lambda: _check_organ_01(service_rows)),
        ("fast_scan", _check_fast_scan),
        ("organ_31 grounding", lambda: _check_organ_31(service_rows)),
        ("organ_49 scan knowledge", _check_organ_49),
        ("organ_48 behavior model", _check_organ_48),
        ("pointer_sentinel", _check_pointer_sentinel),
    ]
    for name, fn in probes:
        try:
            # organ imports print their own load chatter; the health line must stay
            # readable, so import-time stdout/stderr is captured and dropped
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                status, detail = fn()
        except Exception as exc:                               # noqa: BLE001 - a probe must never kill the boot report
            status, detail = DEGRADED, f"probe crashed: {type(exc).__name__}: {exc}"
        rows.append(("ORGAN", name, status, detail))
    return rows


# --------------------------------------------------------------------------- report

CRITICAL = ("env_guard", "ollama :11434", "organ_01 crewai engine", "fast_scan")


def run(verbose: bool = True) -> dict:
    # 1) env_guard preflight printed FIRST (work order: the .bat shows it at boot)
    eg = _check_env_guard()
    lines = []
    if verbose:
        print(f"[env_guard preflight] {eg[2] or eg[1]}")

    # 2) services, then organs (organ probes read the service table, so order matters)
    services = check_services()
    organs = check_organs(services)
    t0 = time.perf_counter()
    for kind, name, status, detail in services + organs:
        lines.append({"kind": kind, "name": name, "status": status, "detail": detail})
        if verbose:
            print(f"  [{status.upper():8s}] {kind:7s} {name:34s} {detail[:90]}")

    crit_bad = [l["name"] for l in lines if l["name"] in CRITICAL and l["status"] == ABSENT]
    counts = {s: sum(1 for l in lines if l["status"] == s) for s in (READY, DEGRADED, ABSENT)}
    if verbose:
        print(f"[boot health] ready={counts[READY]} degraded={counts[DEGRADED]} absent={counts[ABSENT]} "
              f"in {(time.perf_counter() - t0) * 1000:.0f}ms | critical_absent={crit_bad or 'none'}")
    return {"lines": lines, "counts": counts, "critical_absent": crit_bad,
            "ok": not crit_bad}


def main() -> int:
    rep = run(verbose=True)
    if "--json" in sys.argv:
        print(json.dumps(rep, indent=2))
    return 0 if rep["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
