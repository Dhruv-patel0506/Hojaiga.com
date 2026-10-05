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

`expect_popup()` is the second half: a task step that WANTS a dialog (Save As after Ctrl+Shift+S,
a Settings window a learned transition says will open) registers its title so the handler leaves
it alone instead of "mitigating" the very thing the task is waiting for.
"""

from __future__ import annotations

import json
import os
import time
from typing import List

_FLAG_PATH = os.path.join(os.environ.get("TEMP", "."), "hojaiga_popup_mode.json")
POLICY_TTL_S = float(os.environ.get("HOJAIGA_POPUP_POLICY_TTL_S", "120"))
EXPECT_TTL_S = float(os.environ.get("HOJAIGA_POPUP_EXPECT_TTL_S", "20"))


def _read() -> dict:
    try:
        with open(_FLAG_PATH, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return {}


def _write(data: dict) -> None:
    try:
        with open(_FLAG_PATH, "w", encoding="utf-8") as fh:
            json.dump(data, fh)
    except Exception:
        pass


def set_policy(policy: str) -> None:
    """policy: 'probe' | 'task'. Refreshing the call refreshes the TTL."""
    d = _read()
    d.update(policy=policy, ts=time.time(), pid=os.getpid())
    _write(d)


def current_policy() -> str:
    d = _read()
    if d.get("policy") == "probe" and (time.time() - float(d.get("ts", 0))) <= POLICY_TTL_S:
        return "probe"
    return "task"


def expect_popup(*title_fragments: str) -> None:
    d = _read()
    exp = [e for e in d.get("expect", []) if (time.time() - float(e.get("ts", 0))) <= EXPECT_TTL_S]
    exp += [{"frag": f.lower(), "ts": time.time()} for f in title_fragments if f]
    d["expect"] = exp
    _write(d)


def is_expected(title: str) -> bool:
    t = (title or "").lower()
    if not t:
        return False
    return any(e.get("frag") and e["frag"] in t and (time.time() - float(e.get("ts", 0))) <= EXPECT_TTL_S
               for e in _read().get("expect", []))


def clear_expected() -> None:
    d = _read()
    d["expect"] = []
    _write(d)


def expected_titles() -> List[str]:
    return [e["frag"] for e in _read().get("expect", [])
            if (time.time() - float(e.get("ts", 0))) <= EXPECT_TTL_S]
