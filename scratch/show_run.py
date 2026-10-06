"""Show one test's block from a suite run, plus the stderr lines that are not callback spam.

Inline `python -c "..."` keeps breaking on quotes through the PowerShell wrapper; a named script cannot.
"""
import io
import sys

NOISE = ("GetWindowRgn", "Traceback", "AttributeError", "ctypes", 'File "',
         "Exception ignored", "func = self", "return _FuncPtr")


def show(tag: str, test_id: str, tail: int) -> int:
    out = rf"D:\new_automation\_{tag}.out"
    err = rf"D:\new_automation\_{tag}.err"
    try:
        ls = io.open(out, encoding="utf-8", errors="replace").readlines()
    except Exception as exc:
        print(f"no {out}: {exc}")
        return 1
    hits = [n for n, l in enumerate(ls) if l.startswith(f"TEST {test_id} ")]
    if not hits:
        print(f"'TEST {test_id}' not in {out} ({len(ls)} lines)")
        print("".join(ls[-15:]))
        return 1
    start = hits[-1]
    block = ls[start:start + 40]
    print("".join(block))
    try:
        el = io.open(err, encoding="utf-8", errors="replace").readlines()
    except Exception as exc:
        print(f"no {err}: {exc}")
        return 0
    keep = [l.rstrip() for l in el if not any(k in l for k in NOISE)]
    print(f"--- {err}: {len(el)} lines, {len(keep)} after noise filter, last {tail} ---")
    print("\n".join(keep[-tail:]))
    return 0


if __name__ == "__main__":
    sys.exit(show(sys.argv[1], sys.argv[2], int(sys.argv[3]) if len(sys.argv) > 3 else 20))
