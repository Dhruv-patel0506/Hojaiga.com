import sys
import os
import traceback
from PIL import Image, ImageDraw
from PyQt5.QtWidgets import QApplication
from PyQt5.QtGui import QImage, QPainter, QColor
sys.path.insert(0, r"D:\new_automation\All codes")
import importlib.util
spec = importlib.util.spec_from_file_location("gemini_code_2", r"D:\new_automation\All codes\gemini-code-2.py")
g2 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(g2)
app = QApplication.instance()
if not app:
    app = QApplication(sys.argv)
test_img = Image.new("RGB", (400, 300), color=(255, 255, 255))
draw = ImageDraw.Draw(test_img)
draw.polygon([(50, 50), (350, 50), (200, 250)], outline=(0, 0, 0), fill=(200, 200, 200))
draw.rectangle([60, 60, 140, 140], outline=(0, 0, 0), fill=(100, 100, 100))
bridge = g2.AIThreadBridge()
ai = g2.DualIntelligenceSystem(bridge=bridge)
ai._grab_screen = lambda: test_img
print("Instantiating overlay...")
overlay = g2.SketchnoteOverlay(teaching_ai=ai)
overlay = g2.SketchnoteOverlay(teaching_ai=ai)
overlay.resize(1280, 800)
overlay.w = 1280
overlay.h = 800
test_payload = {
    "topic": "Right Triangle & Pythagoras",
    "layout": "petal_hub",
    "palette": "electric_dark",
    "analogies": [
        {"title": "Leg A (Base)", "body": "Adjacent horizontal distance on the grid.", "color": "#00f0ff"},
        {"title": "Leg B (Height)", "body": "Perpendicular vertical rise.", "color": "#a855f7"},
        {"title": "Hypotenuse C", "body": "Direct diagonal Euclidean bridge.", "color": "#f59e0b"}
    ],


    "speech": "Notice how the two perpendicular legs span out to form the hypotenuse.",
    "screen_anchors": [
        {"box": [0.15, 0.2, 0.25, 0.2], "label": "OBSERVED TRIANGLE IN VIDEO"}
    ],
    "glyphs": ["lightbulb", "lightning_bolt"]
}
print("Calling on_sketchnote_received...")
try:
    overlay.on_sketchnote_received(test_payload)
    print("on_sketchnote_received succeeded!")
    print(f"Strokes: {len(overlay.progressive_strokes)}, Anchors: {len(overlay.screen_anchors)}")
except Exception as e:
    traceback.print_exc()
print("Stepping physics...")
try:
    for i in range(30):
        overlay.on_anim_tick()
    print("Physics stepped 30 times!")
except Exception as e:
    traceback.print_exc()
print("Rendering to QImage...")
try:
    render_img = QImage(1280, 800, QImage.Format_ARGB32)
    render_img.fill(QColor(15, 17, 23))
    painter = QPainter(render_img)
    overlay.render_to_painter(painter)
    painter.end()
    out_path = r"D:\new_automation\gemini_code_2_proof.png"
    render_img.save(out_path)
    print(f"Rendered image saved to {out_path}!")
except Exception as e:
    traceback.print_exc()
print("All done in debug script.")
os._exit(0)
