"""AR22: start screens -- a chooser is recognised, the SAFE way in is picked (blank / new / skip, never a recent file), a workbench is not mistaken for a chooser, and the handling is written to the RAG."""
from __future__ import annotations


def run_ar22(verdict):
    """AR22: a start screen is passed safely (blank / new / skip, never a recent file or 'open'), a full workbench is left alone, and the RAG learns the chooser"""
    from core_organs.harvest import start_screen as SS
    from si_tests_rag import _Env
    c = lambda n, t="ButtonControl": {"name": n, "type": t, "box": (0, 0, 80, 30)}
    office = [c("Recent"), c("Open"), c("Blank document"), c("Take a tour"), c("Sign in", "HyperlinkControl"), c("Report.docx", "ListItemControl"), c("Budget 2026.xlsx", "ListItemControl")]
    splash = [c("General"), c("2D Animation"), c("Open..."), c("Recent Files"), c("Quit")]
    only_decline = [c("Recent projects"), c("Maybe later"), c("Sign in"), c("Subscribe")]
    workbench = [c("Bold"), c("Italic"), c("Copy"), c("Paste"), c("Blank")] + [c("Tool %d" % i) for i in range(150)]
    plain = [c("Save"), c("Print"), c("Zoom in")]
    p1, p2, p3, p4, p5 = (SS.pick_start_control(x) for x in (office, splash, only_decline, workbench, plain))
    info = SS.describe(office, p1)
    with _Env(icons=True) as R:
        n = SS.register(R, "padx", "Word", info)
        procs = R.st.count("procedures")
    checks = {"office_start_screen_picks_the_blank_document": p1 is not None and p1["name"] == "Blank document",
              "a_splash_picks_a_default_template_not_open_or_recent": p2 is not None and p2["name"] == "General",
              "when_only_declines_exist_the_gentlest_is_pressed": p3 is not None and p3["name"] == "Maybe later",
              "a_workbench_is_not_a_chooser": p4 is None,
              "an_ordinary_screen_is_left_alone": p5 is None,
              "a_recent_file_is_never_pressed": all(x is None or "recent" not in x["name"].lower() and not x["name"].endswith((".docx", ".xlsx")) for x in (p1, p2, p3)),
              "the_chooser_is_described": info["chosen"] == "Blank document" and "Recent" in info["recent_entries"],
              "the_rag_learns_how_to_pass_it": n["procedures"] >= 1 and n["commands"] == 1 and procs >= 1}
    return verdict(checks, "picks=%s/%s/%s info=%s n=%s" % (p1 and p1["name"], p2 and p2["name"], p3 and p3["name"], info, n))
