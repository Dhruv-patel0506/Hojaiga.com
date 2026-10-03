import sys
import os
import time
import importlib.util
from PIL import Image, ImageDraw

# Add "All codes" to sys.path
sys.path.insert(0, r"D:\new_automation\All codes")

# Import gemini-code-2 module dynamically
spec = importlib.util.spec_from_file_location("gemini_code_2", r"D:\new_automation\All codes\gemini-code-2.py")
g2 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(g2)

print("SUCCESS: Successfully loaded gemini-code-2.py")

# 1. Test OpenCV Screen Tracer
print("\n--- Testing Capability 4: OpenCV Screen Tracing ---")
test_img = Image.new("RGB", (400, 300), color=(255, 255, 255))
draw = ImageDraw.Draw(test_img)
draw.polygon([(50, 50), (350, 50), (200, 250)], outline=(0, 0, 0), fill=(200, 200, 200))
draw.rectangle([60, 60, 140, 140], outline=(0, 0, 0), fill=(100, 100, 100))

contours = g2.OpenCVScreenTracer.trace_screen_region(test_img, [0, 0, 400, 300])
print(f"Extracted {len(contours)} contour paths via OpenCV.")
assert len(contours) > 0, "OpenCV should have extracted contours!"

# 2. Test Progressive Stroke Logic
print("\n--- Testing Capability 1: Progressive Stroke Animation ---")
from PyQt5.QtGui import QPainterPath, QImage, QPainter, QColor
from PyQt5.QtCore import QPointF
path = QPainterPath()
path.moveTo(10.0, 10.0)
path.lineTo(100.0, 10.0)
path.lineTo(100.0, 100.0)

stroke = g2.ProgressiveVectorPath(path=path, color="#4ecdc4", fill=None, width=2.0)
assert stroke.progress == 0.0, "Initial progress should be 0"
stroke.step(0.2)
assert stroke.progress == 0.2, "Progress should advance by 0.2"
pt = stroke.path.pointAtPercent(stroke.progress)
print(f"Progressive stroke stepped to {stroke.progress:.1f}, stylus tip at ({pt.x():.1f}, {pt.y():.1f})")

# 3. Test Socratic Evaluation & Remediation
print("\n--- Testing Capability 3: Socratic Mastery & Adaptive Remediation ---")
eval_correct = g2.DualIntelligenceSystem.evaluate_student_response(
    question="What is the Pythagorean theorem formula?",
    student_answer="It states that a squared plus b squared equals c squared for the hypotenuse.",
    expected_concept="Pythagorean theorem a^2 + b^2 = c^2"
)
print(f"Correct answer evaluation: {eval_correct}")
assert eval_correct["is_correct"] is True, "Expected correct answer to be evaluated as correct"
assert eval_correct["advance"] is True, "Expected to advance"

eval_incorrect = g2.DualIntelligenceSystem.evaluate_student_response(
    question="What is the Pythagorean theorem formula?",
    student_answer="Force equals mass times acceleration.",
    expected_concept="Pythagorean theorem a^2 + b^2 = c^2"
)
print(f"Incorrect answer evaluation: {eval_incorrect}")
assert eval_incorrect["is_correct"] is False, "Expected incorrect answer to be evaluated as false"
assert eval_incorrect["advance"] is False, "Expected remediation without advance"
assert "remediation_metaphor" in eval_incorrect, "Expected remediation metaphor"

# Create Qt Application early for QObjects
from PyQt5.QtWidgets import QApplication
app = QApplication.instance()
if not app:
    app = QApplication(sys.argv)

# 4. Test Lookahead Crawler Priority Queue
print("\n--- Testing Capability 2: Active Lookahead Crawler Queue ---")
bridge = g2.AIThreadBridge()
ai = g2.DualIntelligenceSystem(bridge=bridge)
ai.is_teaching = True  # Prevent crawler race during unit test
ai.buffer_lookahead_lesson("Pythagorean Theorem", {"topic": "Pythagorean Theorem", "layout": "petal_hub", "speech": "Next is geometry"})
ai.buffer_lookahead_lesson("Calculus Limits", {
    "title": "Calculus Limits",
    "layout": "derivation",
    "branches": [
        {"label": "Definition", "detail": "f(x) approaches L as x approaches c"},
        {"label": "Epsilon-Delta", "detail": "For every eps > 0 there exists delta > 0"}
    ],
    "equations_or_punchlines": ["lim_{x->c} f(x) = L"],
    "speech": "Limits describe behavior as we get arbitrarily close to a point."
})
print(f"Buffered lessons: {ai.lookahead_buffer.qsize()}")
next_lesson = ai.get_next_lookahead_lesson()
print(f"Dequeued priority lesson: {next_lesson[0]}")
assert next_lesson[0] == "Pythagorean Theorem"
next_lesson2 = ai.get_next_lookahead_lesson()
print(f"Dequeued second lesson: {next_lesson2[0]}")
assert next_lesson2[0] == "Calculus Limits"

# 5. Test Echo Cancellation Gate
print("\n--- Testing Capability 5: Acoustic Echo Cancellation ---")
listener = g2.EchoSuppressedVoiceListener(bridge=bridge)
listener.set_tts_active(True)
assert listener.tts_active is True, "TTS active state should be True"
assert listener.is_mic_suppressed() is True, "Mic should be suppressed during TTS"
listener.set_tts_active(False)
assert listener.is_mic_suppressed() is False, "Mic should be unmuted when TTS stops"
print("Echo cancellation gating verified.")

# 6. Test SketchnoteOverlay Rendering & Expressive Mascot
print("\n--- Testing Capability 6: Expressive Mascot & Progressive Overlay Render ---")
overlay = g2.SketchnoteOverlay(teaching_ai=ai)
overlay.resize(1280, 800)
overlay.w = 1280
overlay.h = 800

# Feed a comprehensive sketchnote payload with petal_hub, screen anchor, and glyphs
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

# Attach synthetic screen image for anchor tracing
ai._grab_screen = lambda: test_img

overlay.on_sketchnote_received(test_payload)
print(f"Overlay created {len(overlay.progressive_strokes)} progressive vector strokes.")
print(f"Overlay created {len(overlay.screen_anchors)} screen anchors.")

try:
    # Step animation multiple times to progress strokes and text
    for _ in range(30):
        overlay.on_anim_tick()

    print(f"Mascot mood: {overlay.mascot_mood}, mouth open: {overlay.mascot_mouth_open:.1f}, tilt: {overlay.mascot_tilt_deg:.1f} deg")

    # Render to QImage
    render_img = QImage(1280, 800, QImage.Format_ARGB32)
    render_img.fill(QColor(15, 17, 23))
    painter = QPainter(render_img)
    overlay.render_to_painter(painter)
    painter.end()

    out_path = r"D:\new_automation\gemini_code_2_proof.png"
    render_img.save(out_path)
    print(f"SUCCESS: Rendered complete proof image to {out_path}")
    print("ALL 6 CAPABILITIES VERIFIED PERFECTLY!")
    os._exit(0)
except Exception as e:
    import traceback
    traceback.print_exc()
    os._exit(1)
