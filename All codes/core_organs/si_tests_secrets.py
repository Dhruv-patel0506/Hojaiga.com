"""
si_tests_secrets.py -- fails when a credential-shaped string is found in first-party source files.

Run standalone:   python si_tests_secrets.py [root]        (exit 1 + file:line:rule list when anything is found)
From the suite:   si_tests_secrets.run_sec1(TestOutcome)

Reports file, line and rule name ONLY - a matched value is never printed, logged or returned.
An accepted false positive can be silenced with a trailing `# secrets-ok` (or `<!-- secrets-ok -->`) marker on that line.
"""

import math
import os
import re
import sys
from typing import Dict, Iterator, List, Optional, Tuple

DEFAULT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
SKIP_DIRS = {"hojaiga_env", ".venv", "venv", "models", "llama.cpp", "OmniParser", ".git", "node_modules", "__pycache__",
             "stable-diffusion-webui",   # third-party checkout
             "worktrees",                # .claude/.kilo git worktrees: copies of the tree itself
             "profiles"}                 # browser profile runtime state (var/hojaiga/**/profiles), gitignored
EXTS = {".py", ".json", ".jsonl", ".md", ".txt", ".env", ".ini", ".cfg", ".toml", ".yml", ".yaml", ".ps1", ".bat", ".sh"}
MAX_BYTES = 5 * 1024 * 1024
MARKER = "secrets-ok"

# (rule name, regex). Provider-shaped tokens match on shape alone.
_SHAPES: List[Tuple[str, "re.Pattern"]] = [
    ("github-token", re.compile(r"(?<![A-Za-z0-9_])gh[pousr]_[A-Za-z0-9]{30,}")),
    ("github-fine-grained-pat", re.compile(r"github_pat_[A-Za-z0-9_]{22,}")),
    ("openai/anthropic-style-sk", re.compile(r"(?<![A-Za-z0-9_-])sk-(?:ant-|proj-)?[A-Za-z0-9_-]{20,}")),
    ("aws-access-key-id", re.compile(r"(?<![A-Za-z0-9])AKIA[0-9A-Z]{16}(?![A-Za-z0-9])")),
    ("google-api-key", re.compile(r"(?<![A-Za-z0-9_-])AIza[0-9A-Za-z_-]{35}")),
    ("slack-token", re.compile(r"xox[baprso]-[A-Za-z0-9-]{10,}")),
    ("telegram-bot-token", re.compile(r"(?<![0-9])[0-9]{8,10}:AA[A-Za-z0-9_-]{33}(?![A-Za-z0-9_-])")),
    ("private-key-block", re.compile(r"-----BEGIN (?:RSA |EC |DSA |OPENSSH |PGP )?PRIVATE KEY")),
]
# Assignments to secret-ish names: only flagged when the value is long AND high-entropy AND not a placeholder.
_ASSIGN = re.compile(
    r"""(?ix)
    (?:api[_-]?key|secret|token|passwd|password|bearer|auth[_-]?key|access[_-]?key
       |discord|github|telegram|slack|openai|anthropic|stripe|twilio|sendgrid)
    ["']?\s*[:=]\s*["']([^"'\s]{20,})["']""")
_PLACEHOLDER = re.compile(r"(?i)your|example|placeholder|changeme|xxxx|\*{3,}|<[^>]+>|\{[^}]*\}|\$\{|%[A-Za-z_]+%|environ|getenv|dummy|fake|test")


# Known non-secrets that the generic assignment rule trips on: state-machine subject tokens, opcode names, checksum labels,
# redaction-test fixtures. Applied to the generic rule only - provider-shaped tokens are never excused by this.
_ALLOW_ASSIGN = re.compile(r"subject_token\s*=|GET_EXECUTION_TOKEN|checksum_token\s*=|hunter2|set_configuration\(")


def entropy(s: str) -> float:
    if not s:
        return 0.0
    n = len(s)
    return -sum((s.count(c) / n) * math.log2(s.count(c) / n) for c in set(s))


def scan_text(text: str) -> List[Tuple[int, str]]:
    """[(line_no, rule)] for one file's text. Never returns the matched value."""
    out: List[Tuple[int, str]] = []
    for i, line in enumerate(text.splitlines(), 1):
        if MARKER in line:
            continue
        hit: Optional[str] = None
        for rule, rx in _SHAPES:
            if rx.search(line) and not (rule == "openai/anthropic-style-sk" and "hunter2" in line):
                hit = rule
                break
        if hit is None and not _ALLOW_ASSIGN.search(line):
            for m in _ASSIGN.finditer(line):
                val = m.group(1)
                if not _PLACEHOLDER.search(val) and entropy(val) >= 3.5:
                    hit = "high-entropy-secret-assignment"
                    break
        if hit:
            out.append((i, hit))
    return out


def iter_files(root: str) -> Iterator[str]:
    for dp, dns, fns in os.walk(root):
        dns[:] = [d for d in dns if d not in SKIP_DIRS]
        for fn in fns:
            if os.path.splitext(fn)[1].lower() in EXTS or fn == ".env" or fn.startswith(".env."):
                p = os.path.join(dp, fn)
                try:
                    if os.path.getsize(p) <= MAX_BYTES:
                        yield p
                except OSError:
                    pass


def scan_tree(root: str = DEFAULT_ROOT) -> List[Tuple[str, int, str]]:
    found: List[Tuple[str, int, str]] = []
    for p in iter_files(root):
        try:
            with open(p, "r", encoding="utf-8", errors="ignore") as f:
                text = f.read()
        except OSError:
            continue
        for ln, rule in scan_text(text):
            found.append((os.path.relpath(p, root), ln, rule))
    return found


def _selftest() -> Dict[str, bool]:
    """Detector sanity with fakes assembled at runtime, so this file itself never holds a token-shaped literal."""
    a = "A1b2C3d4E5f6G7h8I9j0" * 2
    fakes = {
        "github-token": "ghp" + "_" + a[:36],
        "github-fine-grained-pat": "github" + "_pat_" + a,
        "openai/anthropic-style-sk": "sk" + "-" + a,
        "aws-access-key-id": "AK" + "IA" + "ABCDEFGHIJKLMNOP",
        "google-api-key": "AI" + "za" + a[:35],
        "slack-token": "xox" + "b-" + "1234567890-abcdefghij",
        "telegram-bot-token": "1234567890" + ":" + "AA" + a[:33],
    }
    res = {r: scan_text(f'x = "{v}"\n') == [(1, r)] for r, v in fakes.items()}
    res["assign-high-entropy"] = scan_text('"api_key": "' + a + '"\n') == [(1, "high-entropy-secret-assignment")]
    res["env-read-clean"] = scan_text('"github": os.environ.get("GITHUB_TOKEN", "")\n') == []
    res["placeholder-clean"] = scan_text('api_key = "your-api-key-goes-here-123"\n') == []
    res["marker-silences"] = scan_text('x = "' + fakes["github-token"] + '"  # secrets-ok\n') == []
    return res


def run_sec1(TestOutcome):
    """SEC1: no credential-shaped string (provider token shape, private key, high-entropy secret assignment) in first-party source"""
    st = _selftest()
    found = scan_tree(DEFAULT_ROOT)
    checks = dict(st)
    checks["no-secrets-in-tree"] = not found
    ev = "; ".join(f"{k}={'OK' if v else 'FAIL'}" for k, v in checks.items() if not v) or "all detector self-checks OK"
    if found:
        ev += " | " + ", ".join(f"{f}:{ln}:{r}" for f, ln, r in found[:20]) + (f" (+{len(found) - 20} more)" if len(found) > 20 else "")
    return TestOutcome(passed=all(checks.values()), evidence=ev, metrics={"findings": len(found)})


if __name__ == "__main__":
    root = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_ROOT
    bad = [k for k, v in _selftest().items() if not v]
    if bad:
        print("detector self-test FAILED:", ", ".join(bad))
        sys.exit(2)
    hits = scan_tree(root)
    for f, ln, rule in hits:
        print(f"{f}:{ln}:{rule}")
    print(f"{len(hits)} finding(s) under {root}")
    sys.exit(1 if hits else 0)
