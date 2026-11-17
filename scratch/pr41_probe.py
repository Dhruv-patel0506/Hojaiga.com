import sys, json
sys.path.insert(0, r"d:\new_automation\All codes")
from core_organs import si_tests_professor as S
from core_organs.professor.knowledge import guide_card as GC, guide_finder as GF, manual_rag as MR, guide_steps as GS

cat = S._p2_catalog()
dbp = S._tmp("card_ix2") + ".db"
ix = MR.ManualIndex(dbp)
GF.GUIDE_DIR = S._tmp("guides_c2")
html = ("<html><body><h1>Atlas Guide</h1><h2>Place a marker</h2><ol><li>Click <b>Add Marker</b> on the toolbar.</li></ol>"
        "<h2>Zoom in</h2><ol><li>Choose <b>View</b> &gt; <b>Zoom In</b>.</li></ol><h2>Crop the picture</h2><ol><li>Adjust the <b>Cropping Ratio</b> in the Inspector.</li><li>Click <b>Apply Crop</b>.</li></ol>"
        "<h2>Quick marker</h2><p>Press <b>Ctrl</b>+<b>M</b> to add a marker quickly.</p><h2>Export</h2><ol><li>Choose <b>File</b> &gt; <b>Export</b> &gt; <b>PDF</b>.</li></ol></body></html>")
ix.ingest_text("fixture_like", "Atlas Guide", MR._html_to_text(html), "test:card", "html", embed=False)
card = GC.build_card("fixture_like", ix, cat)
seq = {s["goal"]: s for s in card["action_sequences"]}
for g, s in seq.items():
    print(repr(g), "grounded=", s["grounded"], "unmatched=", s.get("unmatched"))
    for st in s["steps"]:
        print("   ", st.get("how"), st.get("target"), st.get("verb"), st.get("note"))
ix.close()
