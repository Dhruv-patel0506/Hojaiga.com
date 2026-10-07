"""Build an item-[7]-only patch by dropping foreign hunks (io/shutil, run_pm1,
run_cef1, CEF1 registration) and truncating the appended block at the CEF1 marker.
Index-only via `git apply --recount --cached`; the working tree is never touched."""
import re, sys

RAW = r"d:\new_automation\_item7_raw.patch"
OUT = r"d:\new_automation\_item7_only.patch"

SI = "si_tests_behavior.py"
RUNNER = "run_system_intelligence_tests.py"

with open(RAW, encoding="utf-8") as fh:
    lines = fh.read().splitlines(keepends=True)

# split into file sections
sections = []
cur = None
for ln in lines:
    if ln.startswith("diff --git "):
        if cur is not None:
            sections.append(cur)
        cur = {"header": [ln], "body": []}
    else:
        cur["body"].append(ln)
if cur is not None:
    sections.append(cur)


def split_hunks(body):
    """Return (pre_hunk_lines, [ [hunk_lines] ])."""
    pre, hunks, h = [], [], None
    for ln in body:
        if ln.startswith("@@"):
            if h is not None:
                hunks.append(h)
            h = [ln]
        elif h is None:
            pre.append(ln)
        else:
            h.append(ln)
    if h is not None:
        hunks.append(h)
    return pre, hunks


def hunk_added_text(h):
    return "".join(l for l in h[1:] if l.startswith("+"))


out_sections = []
for sec in sections:
    fname = sec["header"][0]
    is_si = SI in fname
    is_runner = RUNNER in fname
    pre, hunks = split_hunks(sec["body"])
    kept = []
    for h in hunks:
        added = hunk_added_text(h)
        ctx = "".join(h[1:])
        if is_runner:
            # keep only RBG1 registration; drop CEF1
            if "test_cef1_behavior" in added or '("CEF1"' in added or "run_cef1" in added:
                continue
            if "test_rbg1_behavior" in added or '("RBG1"' in added:
                kept.append(h)
            continue
        if is_si:
            # drop the import block (io/shutil)
            if re.search(r"^\+import (io|shutil)\b", added, re.M) and "def " not in added:
                continue
            # drop run_pm1 foreign edits
            if "run_pm1" in "".join(h[:1]) or "policy='probe'" in added or "scanner is" in added.lower() \
                    or "def run_pm1" in ctx:
                continue
            # keep LiveApp args hunks
            if "self.args" in added or "args: Optional" in added or "Popen([self.exe] + self.args" in added:
                kept.append(h)
                continue
            # the big appended hunk (has run_rbg1): truncate at CEF1 marker
            if "def run_rbg1" in added:
                newh = [h[0]]
                for ln in h[1:]:
                    if ln.lstrip("+").startswith("#") and "CEF1: the Chromium" in ln:
                        break
                    newh.append(ln)
                # drop any trailing blank added lines
                while len(newh) > 1 and newh[-1].strip("+").strip() == "" and newh[-1].startswith("+"):
                    newh.pop()
                kept.append(newh)
                continue
            # anything else in si_tests is foreign -> drop
            continue
        # unknown file -> keep as-is (shouldn't happen)
        kept.append(h)
    if kept:
        out_sections.append((sec["header"], pre, kept))

with open(OUT, "w", encoding="utf-8", newline="") as fh:
    for header, pre, kept in out_sections:
        fh.write("".join(header))
        fh.write("".join(pre))
        for h in kept:
            body = h[1:]
            # ensure trailing newline on last body line
            if body and not body[-1].endswith("\n"):
                body = body[:-1] + [body[-1] + "\n"]
            fh.write(h[0].splitlines()[0] + "\n")
            fh.write("".join(body))

print("sections kept:", [h[0].strip() for h, _, _ in out_sections])
for header, pre, kept in out_sections:
    print(header[0].strip(), "->", len(kept), "hunks:", [k[0].splitlines()[0] for k in kept])
print("WROTE", OUT)
