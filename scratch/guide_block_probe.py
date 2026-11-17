"""WHY do 8 applications have an empty guide? The fetch log says the vendor's own site answers 403 to a polite reader.
Is the DOCUMENTATION host blocked too, or only the marketing domain? One GET per URL, no browser disguise, robots honoured."""
import sys
sys.path.insert(0, r"d:\new_automation\All codes")
from core_organs.professor.knowledge import guide_finder as GF

f = GF.default_fetch
CANDIDATES = {
    "autodesk (acad)": ["https://help.autodesk.com/", "https://docs.autodesk.com/", "https://www.autodesk.com/support"],
    "mathworks (matlab)": ["https://mathworks.com/help/", "https://uk.mathworks.com/help/matlab/", "https://ww2.mathworks.cn/help/"],
    "tableau": ["https://help.tableau.com/current/pro/desktop/en-us/default.htm", "https://www.tableau.com/learn/docs"],
    "sharex": ["https://getsharex.com/docs/", "https://github.com/ShareX/ShareX/wiki", "https://sharex.gitbook.io/docs"],
    "videolan (vlc)": ["https://www.videolan.org/vlc/doc/", "https://wiki.videolan.org/User:", "https://www.videolan.org/support/"],
    "skype": ["https://support.microsoft.com/en-us/skype", "https://skypegamestats--portal.repl.co/"],
    "android studio": ["https://developer.android.com/studio/intro", "https://developer.android.com/docs"],
    "task manager": ["https://support.microsoft.com/en-us/windows/windows-task-manager", "https://learn.microsoft.com/en-us/windows-server/administration/windows-commands/taskmgr"],
}
for app, urls in CANDIDATES.items():
    outs = []
    for u in urls:
        try:
            code, ct, body, final = f(u)
            outs.append(f"{code} {ct or '-'} len={len(body)} -> {final[:90]}")
        except Exception as exc:
            outs.append(f"ERR {type(exc).__name__}: {str(exc)[:60]} {u}")
    print(f"--- {app}\n    " + "\n    ".join(outs))
