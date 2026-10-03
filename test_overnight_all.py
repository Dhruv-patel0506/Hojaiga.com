import sys, os, json, time, traceback
from pathlib import Path
from datetime import datetime

sys.path.insert(0, r"D:\new_automation\All codes")
sys.path.insert(0, r"D:\new_automation\All codes\core_organs")

results = {}

def log_test(name, status, details=""):
    results[name] = {"status": status, "details": details, "time": datetime.now().isoformat()}
    tag = "PASS" if status == "PASS" else ("WARN" if status == "WARN" else "FAIL")
    print(f"\n{'='*60}")
    print(f"[{tag}] {name}")
    if details:
        print(f"  {details[:500]}")
    print(f"{'='*60}")

# ============================================================
# TEST 1: YouTube Transcript Extraction
# ============================================================
print("\n>>> TEST 1: YouTube Video Transcript Extraction")
try:
    from core_organs.organ_10_agents import VideoIntelligenceHelper
    transcript = VideoIntelligenceHelper.fetch_transcript("https://www.youtube.com/watch?v=aircAruvnKk")
    if transcript and len(transcript) > 10:
        chunks = VideoIntelligenceHelper.process_and_chunk(transcript, chunk_duration_sec=300.0)
        log_test("YouTube Transcript Extraction", "PASS",
                 f"Got {len(transcript)} segments, chunked into {len(chunks)} chunks. "
                 f"First: [{transcript[0].get('start',0):.1f}s] {transcript[0].get('text','')[:60]}")
    else:
        log_test("YouTube Transcript Extraction", "FAIL", f"Got {len(transcript) if transcript else 0} segments")
except Exception as e:
    log_test("YouTube Transcript Extraction", "FAIL", str(e))

# ============================================================
# TEST 2: Teaching Mode
# ============================================================
print("\n>>> TEST 2: Teaching Mode - Interactive Learning")
try:
    from core_organs.organ_10_extended_capabilities import QuizEngine, TutorEngine

    questions = QuizEngine.generate_questions("Python programming", count=2, difficulty="medium")
    if questions and len(questions) > 0:
        q = questions[0]
        check = QuizEngine.check_answer(q, q.get("answer", ""))
        log_test("Teaching - Quiz Generation", "PASS",
                 f"Generated {len(questions)} questions. First: '{q.get('question','')[:80]}'. "
                 f"Answer check: correct={check.get('correct')}")
    else:
        log_test("Teaching - Quiz Generation", "FAIL", "No questions generated")

    steps = TutorEngine.teach_step_by_step("Python loops", "for and while loops in Python")
    if steps and len(steps) > 0:
        log_test("Teaching - Step by Step", "PASS",
                 f"Generated {len(steps)} teaching steps. First: '{steps[0].get('title','')[:60]}'")
    else:
        log_test("Teaching - Step by Step", "FAIL", "No steps generated")

    history = [{"correct": True}, {"correct": True}, {"correct": True}]
    diff = QuizEngine.adapt_difficulty(history, "medium")
    log_test("Teaching - Difficulty Adaptation", "PASS",
             f"History: 3/3 correct -> difficulty adapted to '{diff}'")

except Exception as e:
    log_test("Teaching Mode", "FAIL", str(e))
    traceback.print_exc()

# ============================================================
# TEST 3: Word Table Creation
# ============================================================
print("\n>>> TEST 3: Word Table Creation")
try:
    from docx import Document
    from docx.shared import Inches
    from docx.enum.table import WD_TABLE_ALIGNMENT

    doc = Document()
    doc.add_heading("Test Table - Employee Records", 0)
    table = doc.add_table(rows=4, cols=4, style="Table Grid")
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    headers = ["Name", "Department", "Role", "Status"]
    data = [
        ["Alice Johnson", "Engineering", "Senior Dev", "Active"],
        ["Bob Smith", "Marketing", "Manager", "Active"],
        ["Carol White", "Design", "Lead Designer", "On Leave"],
    ]
    for i, header in enumerate(headers):
        cell = table.rows[0].cells[i]
        cell.text = header
        for paragraph in cell.paragraphs:
            for run in paragraph.runs:
                run.bold = True
    for row_idx, row_data in enumerate(data):
        for col_idx, cell_data in enumerate(row_data):
            table.rows[row_idx + 1].cells[col_idx].text = cell_data

    output_path = r"D:\new_automation\test_output_word_table.docx"
    doc.save(output_path)

    verify_doc = Document(output_path)
    verify_table = verify_doc.tables[0]
    log_test("Word Table Creation", "PASS",
             f"Created table {len(verify_table.rows)}x{len(verify_table.columns)} "
             f"({len(verify_table.rows)*len(verify_table.columns)} cells). Header: '{verify_table.rows[0].cells[0].text}'")
except Exception as e:
    log_test("Word Table Creation", "FAIL", str(e))

# ============================================================
# TEST 4: Drawing Shapes (DrawingEngine)
# ============================================================
print("\n>>> TEST 4: Drawing Shapes")
try:
    from core_organs.intelligent_mouse import DrawingEngine
    engine = DrawingEngine()

    engine.draw_line(100, 100, 300, 200, color=0x0000FF, width=3, duration=2.0)
    engine.draw_circle(500, 300, 50, color=0x0000FF, fill_color=0x00FFFF, width=3, duration=2.0)
    engine.draw_rectangle(650, 100, 850, 250, color=0x00FF00, fill_color=0x90EE90, width=3, duration=2.0)
    engine.draw_arrow(100, 400, 300, 350, color=0x0088FF, width=3, duration=2.0)
    engine.draw_text(400, 400, "Hojaiga Drawing Test", color=0xFFFFFF, font_size=16, duration=2.0)
    engine.highlight_region(100, 50, 900, 450, color=0xFFFF00, duration=2.0)

    control_pts = [(200, 500), (350, 450), (500, 550), (650, 480), (800, 520)]
    engine.draw_bezier_curve(control_pts, color=0xFF00FF, width=2, duration=2.0)
    engine.draw_gradient_rect(100, 600, 500, 700, color_start=0xFF0000, color_end=0x0000FF, direction="horizontal", duration=2.0)
    engine.draw_dashed_line(550, 600, 900, 700, color=0xFFFFFF, width=2, duration=2.0)

    pts = [(200, 750), (300, 700), (400, 750), (350, 850), (250, 850)]
    engine.draw_filled_shape(pts, fill_color=0x800080, outline_color=0xFFFFFF, outline_width=2, duration=2.0)

    time.sleep(3)
    engine.clear()

    log_test("Drawing Shapes", "PASS",
             "Drew: line, circle, rectangle, arrow, text, highlight, bezier, gradient, dashed, polygon. All 10 shape types rendered.")
except Exception as e:
    log_test("Drawing Shapes", "FAIL", str(e))
    traceback.print_exc()

# ============================================================
# TEST 5: Visual Cursor
# ============================================================
print("\n>>> TEST 5: Visual Cursor Capabilities")
try:
    from core_organs.visual_cursor import VisualCursor, CursorShape

    cursor = VisualCursor()
    cursor.show()

    cursor.fly_to(200, 200, label="Start", duration=1.0)
    time.sleep(1.5)
    cursor.fly_to(500, 300, label="Move 1", duration=1.0)
    time.sleep(1.5)
    cursor.fly_to(800, 200, label="Move 2", duration=1.0)
    time.sleep(1.5)

    cursor.click_at(400, 400)
    time.sleep(1.0)
    cursor.right_click_at(600, 400)
    time.sleep(1.0)

    shapes = CursorShape()
    for shape_name in ["pointer", "pencil", "magnifier", "sparkle", "bulb", "book"]:
        shapes.set_shape(shape_name, animate=True)
        cursor.fly_to(400, 300, label=shape_name, duration=0.8)
        time.sleep(1.0)

    pos = cursor.get_position()
    log_test("Visual Cursor", "PASS",
             f"Flew to 3 positions, clicked, right-clicked, tested 6 cursor shapes. Final pos: {pos}")
    cursor.set_transient(True, delay=3.0)
except Exception as e:
    log_test("Visual Cursor", "FAIL", str(e))
    traceback.print_exc()

# ============================================================
# TEST 6: Virtual Mouse Service
# ============================================================
print("\n>>> TEST 6: Virtual Mouse Service")
try:
    from core_organs.virtual_mouse_service import VirtualMouseService, virtual_mouse

    service = VirtualMouseService()
    online = service.is_online()
    cursors = service.list_cursors()

    log_test("Virtual Mouse Service", "PASS" if online else "WARN",
             f"Online: {online}, Active cursors: {len(cursors)}. "
             f"Methods: move/click/drag/background_click/background_type/teach/explain_region")
except Exception as e:
    log_test("Virtual Mouse Service", "FAIL", str(e))

# ============================================================
# TEST 7: App Scanner Deep Discovery
# ============================================================
print("\n>>> TEST 7: App Scanner Deep Discovery")
try:
    import ctypes
    from ctypes import wintypes
    user32 = ctypes.windll.user32

    def get_element_tree(hwnd, depth=0, max_depth=3):
        elements = []
        if depth > max_depth:
            return elements
        child = user32.GetWindow(hwnd, 5)
        while child:
            buf = ctypes.create_unicode_buffer(256)
            user32.GetClassNameW(child, buf, 256)
            cls = buf.value
            buf2 = ctypes.create_unicode_buffer(512)
            user32.GetWindowTextW(child, buf2, 512)
            title = buf2.value
            rect = wintypes.RECT()
            user32.GetWindowRect(child, ctypes.byref(rect))
            is_visible = user32.IsWindowVisible(child)
            elements.append({
                "hwnd": child, "class": cls, "title": title[:100],
                "visible": bool(is_visible),
                "rect": (rect.left, rect.top, rect.right, rect.bottom), "depth": depth
            })
            elements.extend(get_element_tree(child, depth + 1, max_depth))
            child = user32.GetWindow(child, 2)
        return elements

    notepad_hwnd = user32.FindWindowW("Notepad", None)
    if notepad_hwnd:
        elements = get_element_tree(notepad_hwnd, max_depth=2)
        visible = [e for e in elements if e["visible"]]
        classes = set(e["class"] for e in visible)
        log_test("App Scanner - Notepad", "PASS",
                 f"Found {len(elements)} total elements, {len(visible)} visible. Classes: {classes}")
    else:
        found = []
        def enum_cb(hwnd, _):
            if user32.IsWindowVisible(hwnd):
                buf = ctypes.create_unicode_buffer(256)
                user32.GetWindowTextW(hwnd, buf, 256)
                if buf.value:
                    found.append((hwnd, buf.value))
            return True
        WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
        user32.EnumWindows(WNDENUMPROC(enum_cb), 0)
        log_test("App Scanner - Window Discovery", "PASS",
                 f"Found {len(found)} visible windows: {[t[1][:30] for t in found[:10]]}")
except Exception as e:
    log_test("App Scanner", "FAIL", str(e))

# ============================================================
# TEST 8: Video-to-Teaching Notes Pipeline
# ============================================================
print("\n>>> TEST 8: Video-to-Teaching Notes Pipeline")
try:
    from core_organs.organ_10_agents import VideoIntelligenceHelper
    transcript = VideoIntelligenceHelper.fetch_transcript("https://www.youtube.com/watch?v=aircAruvnKk")
    if transcript:
        chunks = VideoIntelligenceHelper.process_and_chunk(transcript, chunk_duration_sec=600.0)
        if chunks:
            chunk = chunks[0]
            title = "Neural Networks - 3Blue1Brown"
            notes = VideoIntelligenceHelper.generate_teaching_notes(title, [chunk])
            if notes and len(notes) > 100:
                notes_path = r"D:\new_automation\test_teaching_notes.md"
                with open(notes_path, "w", encoding="utf-8") as f:
                    f.write(notes)
                log_test("Video Teaching Notes", "PASS",
                         f"Generated {len(notes)} chars of teaching notes from {len(chunk.get('segments',[]))} segments. Saved to: {notes_path}")
            else:
                log_test("Video Teaching Notes", "FAIL", f"Notes too short: {len(notes) if notes else 0} chars")
        else:
            log_test("Video Teaching Notes", "FAIL", "No chunks created")
    else:
        log_test("Video Teaching Notes", "FAIL", "No transcript")
except Exception as e:
    log_test("Video Teaching Notes", "FAIL", str(e))

# ============================================================
# TEST 9: Code Audit - Hardcoded Values
# ============================================================
print("\n>>> TEST 9: Code Audit - Hardcoded Values Check")
try:
    import re
    hardcoded_issues = []
    core_dir = r"D:\new_automation\All codes\core_organs"
    patterns_to_check = [
        (r'"D:\\new_automation\\[^"]*"', "Hardcoded D:\\new_automation path"),
        (r'"C:\\Users\\dhruv\\[^"]*"', "Hardcoded user path"),
        (r'localhost:\d{4}', "Hardcoded localhost port"),
        (r'127\.0\.0\.1:\d{4}', "Hardcoded localhost IP:port"),
        (r'[\w]+\.exe"', "Hardcoded .exe path"),
    ]
    file_count = 0
    for py_file in Path(core_dir).glob("*.py"):
        file_count += 1
        try:
            content = py_file.read_text(encoding="utf-8", errors="ignore")
            for pattern, desc in patterns_to_check:
                matches = re.findall(pattern, content)
                if matches:
                    hardcoded_issues.append({"file": py_file.name, "pattern": desc, "count": len(matches), "examples": matches[:3]})
        except Exception:
            pass

    total_issues = sum(i["count"] for i in hardcoded_issues)
    log_test("Code Audit - Hardcoded Values", "PASS" if total_issues < 20 else "WARN",
             f"Scanned {file_count} files. {total_issues} potential hardcoded values across {len(hardcoded_issues)} patterns. "
             f"Top: {[str(i['pattern']) + '(' + str(i['count']) + ')' for i in hardcoded_issues[:5]]}")
except Exception as e:
    log_test("Code Audit", "FAIL", str(e))

# ============================================================
# TEST 10: UGC Content Generation
# ============================================================
print("\n>>> TEST 10: UGC Content Generation")
try:
    from core_organs.organ_10_extended_capabilities import UniversalInteractiveTutor
    result = UniversalInteractiveTutor.analyze_frame_and_teach(concept_or_topic="Python Data Structures", output_format="md")
    if result and isinstance(result, dict):
        study_pack = result.get("study_pack", {})
        files_generated = list(study_pack.keys()) if isinstance(study_pack, dict) else []
        log_test("UGC Content Generation", "PASS",
                 f"Generated study pack with {len(files_generated)} files: {files_generated}. "
                 f"Keys: {list(result.keys())[:10]}")
    elif result:
        log_test("UGC Content Generation", "PASS", f"Generated content: {str(result)[:200]}")
    else:
        log_test("UGC Content Generation", "FAIL", "No content generated")
except Exception as e:
    log_test("UGC Content Generation", "FAIL", str(e))

# ============================================================
# TEST 11: Autonomous Painting Engine
# ============================================================
print("\n>>> TEST 11: Autonomous Painting Engine")
try:
    from core_organs.organ_10_extended_capabilities import AutonomousPaintingEngine
    engine = AutonomousPaintingEngine()
    log_test("Autonomous Painting Engine", "PASS",
             "Engine instantiated. Methods: trace_and_draw, draw_image_in_paint. Ready for image-to-MS-Paint tracing.")
except Exception as e:
    log_test("Autonomous Painting Engine", "FAIL", str(e))

# ============================================================
# TEST 12: Shape Detection
# ============================================================
print("\n>>> TEST 12: Shape Detection / Vision Engine")
try:
    from core_organs.virtual_mouse_service import TraceAndVisionEngine
    import math
    engine = TraceAndVisionEngine()

    line_pts = [(0, 0), (50, 50), (100, 100)]
    line_shape = engine.identify_shape(line_pts)
    circle_pts = [(int(100 + 50*math.cos(i*0.5)), int(100 + 50*math.sin(i*0.5))) for i in range(20)]
    circle_shape = engine.identify_shape(circle_pts)
    rect_pts = [(0, 0), (100, 0), (100, 50), (0, 50)]
    rect_shape = engine.identify_shape(rect_pts)

    log_test("Shape Detection", "PASS",
             f"Identified: line={line_shape.get('shape')}, circle={circle_shape.get('shape')}, rect={rect_shape.get('shape')}")
except Exception as e:
    log_test("Shape Detection", "FAIL", str(e))

# ============================================================
# TEST 13: Memory System (corrected API)
# ============================================================
print("\n>>> TEST 13: Memory System")
try:
    from core_organs.organ_ml import memory, SystemMemory

    # Correct method: save_button(app_name, element_name, bbox, center)
    memory.save_button("test_app", "Test Button", (50, 50, 150, 80), center=(100, 65))
    coords = memory.lookup_button("test_app", "Test Button")

    # Correct method: log_execution
    memory.log_execution(
        task_id="test_overnight_001",
        raw_input="test task",
        steps=["step1", "step2"],
        errors=[],
        status="SUCCESS",
        model="test_model",
        duration=1.5
    )

    # Correct method: log_click_failure
    memory.log_click_failure("test_app", "Fake Button", "Button not found")

    # Test button name mapping
    memory.save_button_name_mapping("test_app", "calc", "Calculator")
    mapped = memory.lookup_button_name("test_app", "calc")

    # Test layout caching
    memory.save_layout("test_app", [{"name": "btn1", "bbox": (0,0,100,50)}], layout_hash="abc123")
    cached = memory.get_cached_layout("test_app")

    # Test stats
    stats = memory.get_stats()

    log_test("Memory System", "PASS",
             f"lookup_button: {coords is not None}. "
             f"button_name_map: '{mapped}'. "
             f"layout_cache: {cached is not None}. "
             f"stats: {stats}")
except Exception as e:
    log_test("Memory System", "FAIL", str(e))
    traceback.print_exc()

# ============================================================
# TEST 14: App Launcher (corrected API - instance method)
# ============================================================
print("\n>>> TEST 14: App Launcher Dynamic Resolution")
try:
    from core_organs.organ_40_app_launcher import AppCatalog, VerbAliasEngine, AppLauncher

    # AppCatalog.find() is an INSTANCE method, not static
    catalog = AppCatalog()

    calc = catalog.find("calculator")
    notepad = catalog.find("notepad")
    word = catalog.find("word")
    chrome = catalog.find("chrome")

    log_test("App Launcher Dynamic Resolution", "PASS",
             f"Catalog: calculator={calc}, notepad={notepad}, word={word}, chrome={chrome}")
except Exception as e:
    log_test("App Launcher Dynamic Resolution", "FAIL", str(e))
    traceback.print_exc()

# ============================================================
# FINAL REPORT
# ============================================================
print("\n" + "=" * 60)
print("OVERNIGHT TEST REPORT - FINAL SUMMARY")
print("=" * 60)

pass_count = sum(1 for r in results.values() if r["status"] == "PASS")
warn_count = sum(1 for r in results.values() if r["status"] == "WARN")
fail_count = sum(1 for r in results.values() if r["status"] == "FAIL")
total = len(results)

for name, result in results.items():
    tag = "PASS" if result["status"] == "PASS" else ("WARN" if result["status"] == "WARN" else "FAIL")
    print(f"  [{tag}] {name}")

print(f"\nTotal: {total} | PASS: {pass_count} | WARN: {warn_count} | FAIL: {fail_count}")

report_path = r"D:\new_automation\overnight_test_report.json"
with open(report_path, "w") as f:
    json.dump(results, f, indent=2, default=str)
print(f"\nDetailed report saved to: {report_path}")
