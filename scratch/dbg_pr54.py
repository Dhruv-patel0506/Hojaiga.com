import sys
sys.path[:0] = ["D:/new_automation", "D:/new_automation/All codes", "D:/new_automation/All codes/core_organs"]
import tempfile, os, uuid
from core_organs.professor.knowledge import manual_rag as MR, guide_card as GC, guide_steps as GS
ix = MR.ManualIndex(os.path.join(tempfile.gettempdir(), "dbg_" + uuid.uuid4().hex[:6] + ".db"))
ix.ingest_text("demo", "Demo guide", "# Demo Guide\n## Make text bold\n1. Click **Bold**.\n2. Click **Italic**.\n"
               "## Open Demo from the Start menu\n1. Click the **Start** button.\n2. Type Demo.\n3. Press Enter.\n"
               "## Rewrite text with AI\nSign in with your Microsoft account to use credits.\n1. Click **Rewrite**.\n"
               "## Draw a line\n1. Click **Pencil**.\n2. Click and drag on the canvas.\n"
               "## Zoom in\n1. Click **Zoom in**.\n## Zoom the view in\n1. Click **Zoom in**.\n"
               "## Print your work\n1. Click **Print**.\n## Tune the colours\n1. Click **Colour wheel**.\n", "test:demo", "md", embed=False)
for r in ix.db.execute("SELECT cite, substr(text,1,60) FROM chunks"): print(r)
for p in GC.procedures("demo", ix): print(p["goal"], len(p["steps"]))
print([ (s.action, s.target) for s in GS.parse_steps("1. Click **Start** button.\n2. Type Demo.")])
