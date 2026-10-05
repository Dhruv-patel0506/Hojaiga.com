import sys, os, json, time
sys.path.insert(0, r"D:\new_automation\All codes")
sys.path.insert(0, r"D:\new_automation\All codes\core_organs")

print("=" * 70)
print("YOUTUBE TEACHING OVERLAY - LIVE TEST")
print("=" * 70)

from core_organs.youtube_teaching_overlay import YouTubeTeachingOverlay

overlay = YouTubeTeachingOverlay()

# Test with a 3Blue1Brown video about Pythagoras theorem
# (or any educational video with diagrams)
video_url = "https://www.youtube.com/watch?v=aircAruvnKk"  # 3Blue1Brown - Neural Networks
topic = "Neural networks and how neurons compute weighted sums"

print(f"\nVideo: {video_url}")
print(f"Topic: {topic}")

# ── Step 1: Open & Pause ──
print("\n>>> STEP 1: Opening and pausing video...")
success = overlay.open_and_pause(video_url)
print(f"  Open/pause: {'SUCCESS' if success else 'FAILED'}")
print(f"  Title: {overlay._video_title[:80] if overlay._video_title else 'N/A'}")

if not success:
    print("  Trying direct Chrome launch...")
    overlay._launch_chrome_for_video(video_url)
    time.sleep(8)
    success = True  # Continue anyway

# ── Step 2: Capture Frame ──
print("\n>>> STEP 2: Capturing video frame...")
frame = overlay.capture_frame()
if frame:
    print(f"  Frame captured: {len(frame)} chars base64")
    print(f"  Saved to: {overlay._frame_path}")
else:
    print("  Frame capture failed")

# ── Step 3: VLM Analysis ──
print("\n>>> STEP 3: Analyzing frame with VLM...")
analysis = overlay.analyze_frame(topic_hint=topic)
print(f"  Analysis length: {len(analysis)} chars")
print(f"  Shapes found: {len(overlay._shapes)}")
print(f"  Labels found: {len(overlay._labels)}")
if overlay._shapes:
    for i, s in enumerate(overlay._shapes[:5]):
        print(f"    Shape {i+1}: {s.get('type', '?')} - {s.get('label', '')}")
if overlay._labels:
    for i, l in enumerate(overlay._labels[:5]):
        print(f"    Label {i+1}: '{l.get('text', '')}' at {l.get('position', [0,0])}")

# ── Step 4: Extract Contours ──
print("\n>>> STEP 4: Extracting contours...")
contours = overlay.extract_contours()
print(f"  Contours extracted: {len(contours)}")

# ── Step 5: Trace on Overlay ──
print("\n>>> STEP 5: Drawing traced diagram on overlay...")
if contours:
    overlay.trace_on_overlay(contours[:5], animate=True, duration=10.0)  # Limit to 5 contours for speed
    print("  Drew traced contours on overlay")
else:
    print("  No contours to draw")

# ── Step 6: Add Labels ──
print("\n>>> STEP 6: Adding labels...")
if overlay._labels:
    count = overlay.add_labels(duration=15.0)
    print(f"  Drew {count} labels")
else:
    print("  No labels from VLM, drawing default labels")
    overlay.add_labels([
        {"text": "Neuron", "position": [400, 200], "size": "large"},
        {"text": "inputs: x1, x2, x3", "position": [200, 150], "size": "medium"},
        {"text": "weights: w1, w2, w3", "position": [200, 180], "size": "medium"},
        {"text": "activation: f(wx + b)", "position": [450, 250], "size": "medium"},
    ], duration=15.0)

# ── Step 7: Draw Our Own Diagram ──
print("\n>>> STEP 7: Drawing our own teaching diagram...")
overlay.add_own_diagram(
    diagram_type="right_triangle",
    labels={
        "A": "A", "B": "B", "C": "C",
        "ab": "a", "ac": "b", "bc": "c",
        "formula": "a² + b² = c² (Pythagoras)"
    },
    offset_x=850, offset_y=100, scale=0.7, duration=20.0
)
print("  Drew right triangle diagram")

# ── Step 8: Generate & Show Explanation ──
print("\n>>> STEP 8: Generating teaching explanation...")
explanation = overlay.explain(
    transcript="Neural networks compute weighted sums of inputs and apply activation functions...",
    topic=topic
)
print(f"  Explanation length: {len(explanation)} chars")
print(f"  First 200 chars: {explanation[:200]}...")

# Show explanation on screen
overlay.show_explanation_on_screen(explanation, x=50, y=450, duration=25.0)
print("  Displayed explanation on screen")

# ── Summary ──
print("\n" + "=" * 70)
print("TEST COMPLETE - All steps executed")
print("=" * 70)
print(f"  Video title: {overlay._video_title[:60]}")
print(f"  Frame saved: {overlay._frame_path}")
print(f"  Shapes detected: {len(overlay._shapes)}")
print(f"  Labels detected: {len(overlay._labels)}")
print(f"  Contours extracted: {len(contours)}")
print(f"  Explanation: {len(explanation)} chars")
print(f"  Overlay drawings: ACTIVE (visible on screen)")
print("\n  The overlay with traced diagram, labels, and explanation")
print("  is now visible on top of the paused YouTube video.")
print("  Press Ctrl+C or call overlay.stop() to clear.")

# Keep overlay visible for 30 seconds
print("\n  Keeping overlay visible for 30 seconds...")
time.sleep(30)

# Cleanup
overlay.stop()
print("\n  Overlay cleared. Done!")
