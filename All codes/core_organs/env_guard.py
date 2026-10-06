r"""
env_guard.py -- fail loud when a VISION-CRITICAL dependency has drifted past its known
breaking boundary, instead of silently bricking OmniParser at the first vision call.

Why a boundary check and not a blind exact-pin check:
  * The pins in desktop_grounding.py's header are the versions VERIFIED on this host.
  * What actually BREAKS is a boundary, and only those boundaries are hard failures:
        - transformers  >= 5.x    -> Florence-2 (OmniParser) breaks (documented: works on 4.51.3)
        - pydantic-settings < 2.14.1 -> litellm (and therefore CrewAI) fails to import
  * Drift that stays inside the safe side of the boundary is only a WARNING (a newer 4.x
    transformers is fine), so the guard never nags on a working machine or breaks a
    non-vision path where an optional package is simply not installed.

Design rules:
  * Absent optional package -> recorded as "absent", NOT a failure (vision tier reports its
    own honest tiers_skipped elsewhere; we must not be the reason the organ won't import).
  * Only a package that IS present AND past the boundary raises EnvPinError (a loud,
    actionable message with the exact pip fix).
  * `versions` is injectable so the logic is unit-testable without uninstalling anything.
"""

from __future__ import annotations

import logging
import re
from typing import Callable, Dict, List, Optional, Tuple

logger = logging.getLogger("hojaiga.env_guard")

# package -> (readable_name, hard_boundary_check, exact_verified_pin, fix_hint)
# hard_boundary_check(version_tuple) -> True when INSTALLED version is UNSAFE.
_CRITICAL: Dict[str, Tuple[str, Callable[[Tuple[int, ...]], bool], str, str]] = {
    "transformers": (
        "transformers",
        lambda v: v[0] >= 5,                       # 5.x breaks Florence-2 in OmniParser
        "4.51.3",
        "pip install \"transformers==4.51.3\"",
    ),
    "pydantic-settings": (
        "pydantic-settings",
        lambda v: v < (2, 14, 1),                  # litellm needs >=2.14.1
        "2.15.0",
        "pip install \"pydantic-settings>=2.14.1\"",
    ),
    # tokenizers / timm are import-swept alongside transformers; only their presence is advisory.
    "tokenizers": ("tokenizers", lambda v: False, "0.21.4", "pip install \"tokenizers==0.21.4\""),
    "timm": ("timm", lambda v: False, "1.0.30", "pip install \"timm\""),
}


class EnvPinError(RuntimeError):
    """Raised when an INSTALLED dependency is past its known breaking boundary."""


def _parse(version: str) -> Tuple[int, ...]:
    nums = re.findall(r"\d+", version.split("+")[0])
    return tuple(int(n) for n in (nums[:3] + ["0", "0", "0"]))  # >=3 components, never IndexError


def _installed_versions() -> Dict[str, str]:
    from importlib import metadata as md
    out: Dict[str, str] = {}
    for pkg in _CRITICAL:
        try:
            out[pkg] = md.version(pkg)
        except Exception:
            out[pkg] = ""          # absent (or unreadable): treated as NOT a hard failure
    return out


def check_runtime_pins(versions: Optional[Dict[str, str]] = None, *, strict: bool = True) -> Dict[str, str]:
    """Validate vision-critical pins. Returns {pkg: status}. Raises EnvPinError (when strict)
    only if an INSTALLED package is past its hard boundary. Advisory drift -> a logged warning.

    `versions` may be injected (pkg -> installed string, "" = absent) for testing."""
    v = versions if versions is not None else _installed_versions()
    report: Dict[str, str] = {}
    fatal: List[str] = []
    for pkg, (name, unsafe, exact, fix) in _CRITICAL.items():
        inst = (v.get(pkg) or "").strip()
        if not inst:
            report[pkg] = "absent"
            continue
        parsed = _parse(inst)
        if bool(unsafe(parsed)):
            report[pkg] = f"UNSAFE ({inst})"
            fatal.append(f"  - {name} {inst} is past a known breaking boundary. {fix}")
        elif inst != exact:
            report[pkg] = f"drift-ok ({inst}, verified {exact})"
            logger.warning("[env_guard] %s %s differs from the verified pin %s (inside the safe "
                           "boundary) - vision may behave slightly differently.", name, inst, exact)
        else:
            report[pkg] = f"ok ({inst})"
    if fatal and strict:
        raise EnvPinError(
            "Hojaiga vision/OCR environment check FAILED - one or more installed dependencies is "
            "past a documented breaking boundary (OmniParser / CrewAI will misbehave):\n"
            + "\n".join(fatal)
            + "\nReinstall with the pinned versions (see desktop_grounding.py header) and restart."
        )
    return report


def preflight() -> Tuple[bool, str]:
    """Safe wrapper for startup scripts: never raises, returns (ok, message)."""
    try:
        rep = check_runtime_pins(strict=False)
    except Exception as exc:  # guard itself must never crash startup
        return True, f"env_guard skipped ({type(exc).__name__}: {exc})"
    fatal = [f"{k}={s}" for k, s in rep.items() if s.startswith("UNSAFE")]
    if fatal:
        return False, "env pin drift: " + ", ".join(fatal)
    return True, " ".join(f"{k}:{v}" for k, v in rep.items())


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    ok, msg = preflight()
    print(f"preflight ok={ok}\n{msg}")
    # self-test the fatal path deterministically without touching the real env
    fake = {"transformers": "5.0.0", "pydantic-settings": "2.15.0", "tokenizers": "", "timm": ""}
    try:
        check_runtime_pins(versions=fake, strict=True)
        print("SELF-TEST=FAIL (transformers 5.x should have raised)")
    except EnvPinError as e:
        print("SELF-TEST=PASS (5.x correctly rejected)")
