"""Build selective stage patches for the deep-knowledge commit: my hunks only, never the parallel
session's. organ_50: exclude the save_pixels explicit-column-list hunk (parallel). organ_63: keep
ONLY the two master() hunks (modal guard + converge honesty); drop _DIALOG_INTENT /
BUTTON_WINDOW_POLL_S / probe_invoke / opener-classification hunks (parallel session)."""
import re
import subprocess

def diff_of(rel):
    """git diff straight to bytes: PowerShell's '>' redirect writes UTF-16 and mangles ellipsis chars."""
    return subprocess.run(["git", "-C", r"d:\new_automation", "diff", "--", rel],
                          capture_output=True).stdout.decode("utf-8")

def hunks(txt):
    lines = txt.splitlines(keepends=True)
    head, hs, cur = [], [], None
    for ln in lines:
        if ln.startswith("@@"):
            if cur:
                hs.append("".join(cur))
            cur = [ln]
        elif cur is not None:
            cur.append(ln)
        else:
            head.append(ln)
    if cur:
        hs.append("".join(cur))
    return "".join(head), hs

out = []

# organ_50: every hunk whose body mentions save_pixels/bm_layout INSERT is the parallel one
head, hs = hunks(diff_of("All codes/core_organs/organ_50_layout_map.py"))
keep = [h for h in hs if "INSERT OR REPLACE INTO bm_layout" not in h]
print(f"organ_50: {len(hs)} hunks, keep {len(keep)}")
out.append(head + "".join(keep))

# organ_63: keep only hunks inside master() (identified by my guard/converge markers)
head, hs = hunks(diff_of("All codes/core_organs/organ_63_app_mastery.py"))
mine = ("startup-modal guard", "converged: nothing left open")
keep = [h for h in hs if any(m in h for m in mine)]
print(f"organ_63: {len(hs)} hunks, keep {len(keep)} -> {[h.splitlines()[0] for h in keep]}")
out.append(head + "".join(keep))

for name, patch in zip(("organ_50", "organ_63"), out):
    p = rf"d:\new_automation\scratch\_stage_{name}.patch"
    open(p, "w", encoding="utf-8", newline="\n").write(patch)
    print("wrote", p)
