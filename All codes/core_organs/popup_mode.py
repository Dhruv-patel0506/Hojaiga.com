"""
popup_mode.py — one tiny, cross-process answer to "how should a popup be treated RIGHT NOW?"

Complements popup_policy.py (which decides HOW to answer a dialog); this decides which
rulebook applies — scan-time probe (cancel-only) or task-time (full ladder).

Why it exists
-------------
The scanner (organ_30) and the popup handler (organ_29) run in different threads/processes
(CNS bridge). A dialog that the scanner's own probe just opened is NOT a roadblock — it is
the thing being learned — and accepting it (semantic "OK", Enter on a message box) could
commit a change. A dialog that appears mid-task is a different animal. The handler needs to
know which situation it is in, so the scanner publishes a policy flag that expires on its own.

    policy "task"   (default) full resolution ladder: semantic accept, cache, lexical, LLM, Escape
    policy "probe"  CANCEL-ONLY: Escape -> IDCANCEL -> WM_CLOSE. Never accepts, never pays for the
                    LLM tier (so exploration is also faster).

The flag is a small JSON file with a TTL, so a crashed scanner can never leave the handler stuck
in probe mode, and there is no shared-memory / port coupling between organs.

The TTL alone was not enough (measured 2026-10-06): a run whose process was killed mid-scan left
policy='probe' with a 120 s clock still running, and every popup decision in the NEXT process spent
up to two minutes answering real dialogs cancel-only - four suite tests failed at once on
'cancel_only_no_handle' while passing standalone. So a flag is only honoured while the process that
wrote it is still alive: "the scanner is exploring right now" is a claim about a live process, and a
dead one is making it. The TTL stays as the backstop for a live-but-stuck writer, and for PID reuse.

And one writer is not enough either, for the opposite reason. probe is not a MODE somebody switches
on and off - it is a set of claims, one per live scanner, and the answer is probe while ANY of them
holds. A single global field let an unrelated process (an abandoned scan being cleaned up, a test
resetting itself) answer 'task' in the middle of a scan that was still probing dialogs: f6's four
scan-path degradations. So: `claim()`/`unclaim()`/`heartbeat()` with a token per claimant; a release
removes exactly its own claim, and `set_policy()` is the same thing under a per-process token.

`expect_popup()` is the second half: a task step that WANTS a dialog (Save As after Ctrl+Shift+S,
a Settings window a learned transition says will open) registers its title so the handler leaves
it alone instead of "mitigating" the very thing the task is waiting for.
"""

from __future__ import annotations

import json
import os
import threading
import time
import uuid
from typing import Any, Dict, List

_FLAG_PATH = os.path.join(os.environ.get("TEMP", "."), "hojaiga_popup_mode.json")
POLICY_TTL_S = float(os.environ.get("HOJAIGA_POPUP_POLICY_TTL_S", "120"))
EXPECT_TTL_S = float(os.environ.get("HOJAIGA_POPUP_EXPECT_TTL_S", "20"))
# One identity per process for the plain set_policy() API, and a lock so the read-modify-write of the
# claim file stays consistent between this process's own threads (PAR1 drives two apps at once).
_PROCESS_CLAIM = f"proc-{os.getpid()}-{uuid.uuid4().hex[:8]}"
_CLAIM_LOCK = threading.RLock()
HEARTBEAT_S = 20.0
_HEARTBEAT: Dict[str, float] = {}


def _open_kernel32():
    try:
        import ctypes
        return ctypes.WinDLL("kernel32", use_last_error=True)
    except Exception:
        return None


_K32 = _open_kernel32()
_STILL_ACTIVE = 259


def _writer_alive(pid) -> bool:
    """Does the process that published this flag still exist?

    Unknown is answered 'alive' (a machine we cannot read should not change behaviour by
    accident); a pid that is simply not there any more is answered 'dead', which is the whole
    point - and a flag with no pid at all (an older writer) is treated as stale too.
    """
    try:
        pid = int(pid or 0)
    except (TypeError, ValueError):
        return False
    if pid <= 0:
        return False
    if pid == os.getpid():
        return True
    if _K32 is None:
        return True
    import ctypes
    handle = _K32.OpenProcess(0x1000, False, pid)   # PROCESS_QUERY_LIMITED_INFORMATION
    if not handle:
        return ctypes.get_last_error() == 5          # access denied = it exists, it is not ours
    try:
        code = ctypes.c_ulong()
        if not _K32.GetExitCodeProcess(handle, ctypes.byref(code)):
            return True
        return code.value == _STILL_ACTIVE
    finally:
        _K32.CloseHandle(handle)


def _read() -> Dict[str, Any]:
    try:
        with open(_FLAG_PATH, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _write(data: Dict[str, Any]) -> None:
    try:
        with open(_FLAG_PATH, "w", encoding="utf-8") as fh:
            json.dump(data, fh)
    except Exception:
        pass


def set_policy(policy: str) -> None:
    """policy: 'probe' | 'task'. A process-level convenience wrapper over the claim set below: it
    claims (or releases) ONE probe for this process, identified by a token that is stable per process.
    It can no longer silence a probe that a DIFFERENT live process claimed - which is what a bare
    global 'task' write used to do (measured 2026-10-06, f6: an abandoned scan being cleaned up at
    garbage-collection time answered 'task' in the middle of a live scan, and four scan tests
    degraded together)."""
    if policy == "probe":
        claim(_PROCESS_CLAIM, "set_policy")
    else:
        unclaim(_PROCESS_CLAIM)


def _live_claims(d: Dict[str, Any], now: float) -> List[Dict[str, Any]]:
    """Claims whose writer process is still alive and whose clock is still honest."""
    out = []
    for c in d.get("claims") or []:
        try:
            if not c.get("token") or (now - float(c.get("ts", 0))) > POLICY_TTL_S:
                continue
            if not _writer_alive(c.get("pid")):
                continue
            out.append(c)
        except (TypeError, ValueError, AttributeError):
            continue
    return out


def _apply_claims(d: Dict[str, Any], claims: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Write the claim set and keep the readable 'policy' field HONEST about it: the flag's writer is
    whoever actually holds a claim (the freshest one), not whoever last touched the file. Get this wrong
    and a process that merely released its own claim leaves policy='probe' signed with its own live pid -
    which the legacy reader then honours forever (measured in h2: PM1's 'the killed claimant is not
    honoured' check caught exactly that)."""
    d["claims"] = claims
    if claims:
        freshest = max(claims, key=lambda c: float(c.get("ts", 0)))
        d["policy"] = "probe"
        d["pid"] = int(freshest.get("pid") or os.getpid())
        d["ts"] = float(freshest.get("ts", 0))
    else:
        d["policy"] = "task"
        d["pid"] = os.getpid()
        d["ts"] = time.time()
    return d


def claim(token: str, why: str = "") -> str:
    """'A scanner is exploring right now' - ours, until we unclaim or stop existing."""
    with _CLAIM_LOCK:
        d = _read()
        claims = _live_claims(d, time.time())
        now = time.time()
        for c in claims:
            if c.get("token") == token:
                c["ts"] = now                                   # refresh, do not duplicate
                c["why"] = why or c.get("why", "")
                break
        else:
            claims.append({"token": token, "pid": os.getpid(), "ts": now, "why": why})
        _write(_apply_claims(d, claims))
    return token


def unclaim(token: str) -> bool:
    """Drop OUR claim. Someone else's live claim survives this call - that is the point."""
    with _CLAIM_LOCK:
        d = _read()
        claims = _live_claims(d, time.time())
        kept = [c for c in claims if c.get("token") != token]
        removed = len(kept) != len(claims)
        _write(_apply_claims(d, kept))
    return removed


def heartbeat(token: str) -> None:
    """A long scan must not silently lose its probe protection to the TTL halfway through; refresh
    (throttled, so a per-control call is cheap) while the owner is alive."""
    now = time.time()
    if now - _HEARTBEAT.get(token, 0.0) < HEARTBEAT_S:
        return
    _HEARTBEAT[token] = now
    claim(token, "heartbeat")


def current_policy() -> str:
    now = time.time()
    d = _read()
    if _live_claims(d, now):
        return "probe"
    if d.get("policy") != "probe":
        return "task"
    if (now - float(d.get("ts", 0))) > POLICY_TTL_S:
        return "task"
    return "probe" if _writer_alive(d.get("pid")) else "task"


def expect_popup(*title_fragments: str) -> None:
    d = _read()
    exp = _live_expected(d.get("expect", []))
    exp += [{"frag": f.lower(), "ts": time.time(), "pid": os.getpid()}
            for f in title_fragments if f]
    d["expect"] = exp
    _write(d)


def _live_expected(entries: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """An expectation only means something while the step that wants the dialog is running."""
    out = []
    for e in entries or []:
        try:
            if not e.get("frag"):
                continue
            if (time.time() - float(e.get("ts", 0))) > EXPECT_TTL_S:
                continue
            if not _writer_alive(e.get("pid")):
                continue
            out.append(e)
        except (TypeError, ValueError, AttributeError):
            continue
    return out


def is_expected(title: str) -> bool:
    t = (title or "").lower()
    if not t:
        return False
    return any(e["frag"] in t for e in _live_expected(_read().get("expect", [])))


def clear_expected() -> None:
    d = _read()
    d["expect"] = []
    _write(d)


def expected_titles() -> List[str]:
    return [e["frag"] for e in _live_expected(_read().get("expect", []))]
