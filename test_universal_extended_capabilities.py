"""
test_universal_extended_capabilities.py
============================================================
Automated Test Suite for Hojaiga OS - Organ 10 Extended Capabilities:
1. AutonomousPaintingEngine: Ultra-High Resolution AI Photo Tracing
2. OmniFileEngine: Universal World File Format Operations & Unified Actions
3. UniversalInteractiveTutor: Multimodal Domain-Agnostic Pedagogy across Subjects
============================================================
"""

import os
import sys
import json
import time
import shutil
import numpy as np
from pathlib import Path

# Add paths
_this_dir = Path(__file__).parent.resolve()
sys.path.insert(0, str(_this_dir / "All codes"))

from core_organs.organ_10_extended_capabilities import (
    AutonomousPaintingEngine,
    OmniFileEngine,
    UniversalInteractiveTutor,
    CodeSynthesisEngine,
    FileSearchEngine,
    PersistentKnowledgeEngine,
    DatabaseOperationsEngine
)

TEST_DIR = _this_dir / "test_extended_output"


def setup_test_environment():
    if TEST_DIR.exists():
        shutil.rmtree(TEST_DIR)
    TEST_DIR.mkdir(parents=True, exist_ok=True)
    print(f"[TEST SETUP] Clean test workspace initialized at: {TEST_DIR}")


def test_omni_file_engine():
    print("\n" + "="*70)
    print("TEST 1: UNIVERSAL OMNI-FORMAT FILE ENGINE (WORLD FORMATS)")
    print("="*70)

    # 1. Document Format: .docx
    docx_path = str(TEST_DIR / "sample_briefing.docx")
    w_res = OmniFileEngine.execute(docx_path, "write", content="# Executive Briefing\n## Overview\nAutonomous agent online.\n- Zero API costs\n- Universal file support")
    assert w_res["status"] == "success", f"Docx write failed: {w_res}"
    print("  [PASS] .docx write operation")

    app_res = OmniFileEngine.execute(docx_path, "append", content="## Appendix\nUnderwritten telemetry record.")
    assert app_res["status"] == "success", f"Docx append failed: {app_res}"
    print("  [PASS] .docx append (underwrite) operation")

    r_res = OmniFileEngine.execute(docx_path, "read")
    assert "Executive Briefing" in r_res["content"], f"Docx read missing heading: {r_res}"
    assert "Underwritten telemetry" in r_res["content"], f"Docx read missing append: {r_res}"
    print(f"  [PASS] .docx read operation ({r_res['paragraphs_count']} paragraphs extracted)")

    p_res = OmniFileEngine.execute(docx_path, "patch", search_target="Zero API costs", replace_text="100% Free Local Execution")
    assert p_res["status"] == "success" and p_res["replacements"] > 0, f"Docx patch failed: {p_res}"
    print("  [PASS] .docx patch / search_replace operation")

    # 2. Tabular Format: .xlsx
    xlsx_path = str(TEST_DIR / "financial_ledger.xlsx")
    records = [
        {"Transaction_ID": "TX-101", "Category": "Hardware", "Amount": 1450.00, "Currency": "USD"},
        {"Transaction_ID": "TX-102", "Category": "Software", "Amount": 320.50, "Currency": "USD"},
        {"Transaction_ID": "TX-103", "Category": "Cloud Free", "Amount": 0.00, "Currency": "USD"}
    ]
    xl_w = OmniFileEngine.execute(xlsx_path, "write", data_rows=records, sheet_name="Ledger2026")
    assert xl_w["status"] == "success" and xl_w["rows_written"] == 3, f"Excel write failed: {xl_w}"
    print("  [PASS] .xlsx write operation")

    new_record = [{"Transaction_ID": "TX-104", "Category": "Consulting", "Amount": 750.00, "Currency": "USD"}]
    xl_app = OmniFileEngine.execute(xlsx_path, "append", data_rows=new_record, sheet_name="Ledger2026")
    assert xl_app["status"] == "success", f"Excel append failed: {xl_app}"
    print("  [PASS] .xlsx append operation")

    xl_r = OmniFileEngine.execute(xlsx_path, "read", sheet_name="Ledger2026")
    assert xl_r["status"] == "success" and xl_r["total_rows"] == 4, f"Excel read mismatch: {xl_r}"
    print(f"  [PASS] .xlsx read operation ({xl_r['total_rows']} rows verified)")

    # 3. Big Data / Tabular Format: .parquet
    parquet_path = str(TEST_DIR / "analytics_telemetry.parquet")
    pq_data = [
        {"session_id": "s_001", "latency_ms": 12.4, "fps": 60, "agent": "A1"},
        {"session_id": "s_002", "latency_ms": 14.8, "fps": 59, "agent": "A2"},
        {"session_id": "s_003", "latency_ms": 11.2, "fps": 60, "agent": "A1"}
    ]
    pq_w = OmniFileEngine.execute(parquet_path, "write", data_rows=pq_data)
    assert pq_w["status"] == "success", f"Parquet write failed: {pq_w}"
    print("  [PASS] .parquet write operation")

    pq_r = OmniFileEngine.execute(parquet_path, "read")
    assert pq_r["status"] == "success" and pq_r["total_rows"] == 3, f"Parquet read failed: {pq_r}"
    print(f"  [PASS] .parquet read operation ({len(pq_r['columns'])} columns, {pq_r['total_rows']} records)")

    # 4. Presentation Format: .pptx
    pptx_path = str(TEST_DIR / "keynote_presentation.pptx")
    ppt_w = OmniFileEngine.execute(pptx_path, "write", content="Hojaiga OS: Autonomous Workstation\nEngineered for 100% Zero-Cost Local Intelligence")
    assert ppt_w["status"] == "success", f"PPTX write failed: {ppt_w}"
    print("  [PASS] .pptx write operation")

    ppt_app = OmniFileEngine.execute(pptx_path, "append", content="Architecture Deep-Dive\nMulti-Organ Event Bus & Virtual Mouse Service")
    assert ppt_app["status"] == "success", f"PPTX append failed: {ppt_app}"
    print("  [PASS] .pptx append (new slide) operation")

    ppt_r = OmniFileEngine.execute(pptx_path, "read")
    assert ppt_r["status"] == "success" and ppt_r["slides_count"] >= 2, f"PPTX read failed: {ppt_r}"
    print(f"  [PASS] .pptx read operation ({ppt_r['slides_count']} slides verified)")

    # 5. Serialization Formats: .json, .yaml, .xml
    json_path = str(TEST_DIR / "config_manifest.json")
    conf_obj = {"system": "Hojaiga", "version": "2.0.0", "organs": [10, 30, 33], "flags": {"active": True}}
    OmniFileEngine.execute(json_path, "write", content=conf_obj)
    json_r = OmniFileEngine.execute(json_path, "read")
    assert json_r["data"]["system"] == "Hojaiga", "JSON read failed"
    print("  [PASS] .json write & read operations")

    yaml_path = str(TEST_DIR / "deployment.yaml")
    yaml_obj = {"service": "hojaiga-agent", "replicas": 1, "environment": "production"}
    OmniFileEngine.execute(yaml_path, "write", content=yaml_obj)
    yaml_r = OmniFileEngine.execute(yaml_path, "read")
    assert yaml_r["data"]["service"] == "hojaiga-agent", "YAML read failed"
    print("  [PASS] .yaml write & read operations")

    # 6. Archive Compression & Extraction: .zip
    zip_source_dir = TEST_DIR / "archive_test_folder"
    zip_source_dir.mkdir(parents=True, exist_ok=True)
    with open(zip_source_dir / "file1.txt", "w") as f:
        f.write("Archive test file 1")
    with open(zip_source_dir / "file2.txt", "w") as f:
        f.write("Archive test file 2")

    comp_res = OmniFileEngine.execute(str(zip_source_dir), "compress", format_target="zip")
    assert comp_res["status"] == "success", f"Zip compression failed: {comp_res}"
    print(f"  [PASS] .zip compression: {comp_res['archive']}")

    extr_res = OmniFileEngine.execute(comp_res["archive"], "extract")
    assert extr_res["status"] == "success", f"Zip extraction failed: {extr_res}"
    assert os.path.exists(os.path.join(extr_res["destination"], "file1.txt")), "Extracted file1 missing"
    print(f"  [PASS] .zip extraction verified to: {extr_res['destination']}")

    # 7. Metadata & Checksum
    meta_res = OmniFileEngine.execute(docx_path, "metadata")
    assert meta_res["status"] == "success" and "sha256" in meta_res, "Metadata failed"
    print(f"  [PASS] Metadata & SHA256 integrity inspection ({meta_res['sha256'][:16]}...)")

    # 8. Cross-Format Conversion: Markdown -> DOCX & PPTX
    md_path = str(TEST_DIR / "research_notes.md")
    with open(md_path, "w", encoding="utf-8") as f:
        f.write("# Autonomous Research Notes\n\nKey takeaways from computational topology experiment.\n- Point cloud clustering complete.")
    
    conv_docx = OmniFileEngine.execute(md_path, "convert", format_target="docx")
    assert conv_docx["status"] == "success" and os.path.exists(conv_docx["target_file"]), "MD->DOCX conversion failed"
    print(f"  [PASS] Cross-format conversion: .md -> .docx ({conv_docx['target_file']})")

    conv_pptx = OmniFileEngine.execute(md_path, "convert", format_target="pptx")
    assert conv_pptx["status"] == "success" and os.path.exists(conv_pptx["target_file"]), "MD->PPTX conversion failed"
    print(f"  [PASS] Cross-format conversion: .md -> .pptx ({conv_pptx['target_file']})")


def test_ultra_res_painting_engine():
    print("\n" + "="*70)
    print("TEST 2: ULTRA-HIGH RESOLUTION AI PHOTO TRACING SUITE")
    print("="*70)

    import cv2

    # Synthesize an intricate test image with multi-scale details:
    # Outer geometric silhouette, interior fine details, curved concentric contours, and subtle gradient shading
    img_w, img_h = 600, 600
    canvas = np.full((img_h, img_w, 3), 255, dtype=np.uint8)

    # 1. Outer structure: Polygon / portrait silhouette
    pts_outer = np.array([[300, 50], [500, 180], [520, 420], [300, 560], [80, 420], [100, 180]], np.int32)
    cv2.polylines(canvas, [pts_outer], isClosed=True, color=(20, 20, 20), thickness=3)

    # 2. Interior features: Concentric arcs, facial/anatomical curves
    cv2.ellipse(canvas, (300, 260), (140, 180), 0, 0, 360, (40, 40, 40), 2)
    cv2.circle(canvas, (240, 230), 25, (10, 10, 10), -1)  # eye 1
    cv2.circle(canvas, (360, 230), 25, (10, 10, 10), -1)  # eye 2
    cv2.ellipse(canvas, (300, 340), (60, 30), 0, 0, 180, (30, 30, 30), 3)  # mouth smile

    # 3. Fine texture: Hatching / shading lines
    for offset in range(-80, 90, 15):
        cv2.line(canvas, (200 + offset, 440), (250 + offset, 490), (100, 100, 100), 1)

    # 4. Intricate details: Micro spirals / geometric filigree
    for r in range(10, 80, 12):
        cv2.circle(canvas, (300, 140), r, (60, 60, 60), 1)

    test_photo_path = str(TEST_DIR / "complex_test_photo.png")
    cv2.imwrite(test_photo_path, canvas)
    print(f"  [CREATED] Intricate test image: {test_photo_path} (600x600)")

    # Execute Multi-Stage Ultra-Resolution Contour Extraction
    t0 = time.time()
    extraction = AutonomousPaintingEngine.extract_high_res_contours(
        image_path=test_photo_path,
        detail_level="ultra",
        max_canvas_dim=700,
        ai_guidance=False  # Heuristic vision parameters for fast offline automated test
    )
    t_elapsed = round(time.time() - t0, 3)

    assert extraction["status"] == "success", f"Extraction failed: {extraction}"
    layers = extraction["layers"]
    total_strokes = extraction["total_strokes"]
    total_points = extraction["total_points"]

    print(f"  [PASS] Multi-scale extraction completed in {t_elapsed}s:")
    print(f"         - Total Chained Strokes: {total_strokes}")
    print(f"         - Total High-Res Waypoints: {total_points}")
    print(f"         - Outer Silhouette Strokes: {len(layers['outer_silhouette'])}")
    print(f"         - Interior Anatomy Strokes: {len(layers['interior_anatomy'])}")
    print(f"         - Fine Texture Strokes: {len(layers['fine_textures'])}")
    print(f"         - Shading/Hatching Strokes: {len(layers['shading_hatching'])}")

    assert total_strokes > 5, "Expected multi-layered strokes extracted"
    assert total_points > 100, "Expected high-resolution point density"

    # Test Execution Pipeline in Non-Interactive Headless Mode
    draw_res = AutonomousPaintingEngine.trace_and_draw(
        image_path=test_photo_path,
        canvas_offset_x=250,
        canvas_offset_y=200,
        speed_delay=0.0,
        detail_level="ultra",
        visual_mode=False,  # Headless test
        launch_app=False
    )
    assert draw_res["status"] == "success", f"Painting execution failed: {draw_res}"
    print(f"  [PASS] AutonomousPaintingEngine pipeline executed successfully ({draw_res['executed_strokes']} strokes rendered)")

    # Test exact plan signature: draw_image_in_paint
    plan_draw_res = AutonomousPaintingEngine.draw_image_in_paint(
        source_image_path=test_photo_path,
        canvas_offset=(250, 200),
        delay=0.001,
        launch_app=False,
        visual_mode=False
    )
    assert plan_draw_res["status"] == "success", f"draw_image_in_paint failed: {plan_draw_res}"
    print(f"  [PASS] AutonomousPaintingEngine.draw_image_in_paint exact signature verified")


def test_universal_interactive_tutor():
    print("\n" + "="*70)
    print("TEST 3: UNIVERSAL INTERACTIVE TUTOR (ANY SUBJECT / DOMAIN)")
    print("="*70)

    test_domains = [
        ("Quantum Physics", "Schrodinger Wave Equation & Quantum Tunneling across Potential Barriers"),
        ("Electrical Engineering", "RLC High-Q Bandpass Resonant Circuit & Phase Bode Plot"),
        ("Macroeconomics & Finance", "IS-LM Equilibrium Shock and Keynesian Liquidity Trap Dynamics")
    ]

    for domain, topic in test_domains:
        print(f"\n  Testing Pedagogical Synthesis for [{domain}]: '{topic}'...")
        tutor_res = UniversalInteractiveTutor.analyze_frame_and_teach(
            concept_or_topic=topic,
            target_domain=domain
        )
        assert tutor_res["status"] == "success", f"Tutor failed on {domain}: {tutor_res}"
        study_pack = tutor_res["study_pack"]

        print(f"  [PASS] {domain} breakdown completed:")
        print(f"         - Markdown Notes: {study_pack['markdown']} (exists: {os.path.exists(study_pack['markdown'])})")
        print(f"         - Word Doc: {study_pack['word_docx']} (exists: {os.path.exists(study_pack['word_docx'])})")
        print(f"         - 16:9 Slide Deck: {study_pack['powerpoint_pptx']} (exists: {os.path.exists(study_pack['powerpoint_pptx'])})")
        print(f"         - Interactive HTML: {study_pack['interactive_html']} (exists: {os.path.exists(study_pack['interactive_html'])})")

        assert os.path.exists(study_pack["markdown"])
        assert os.path.exists(study_pack["word_docx"])
        assert os.path.exists(study_pack["powerpoint_pptx"])
        assert os.path.exists(study_pack["interactive_html"])

    # Test exact plan signature: analyze_paused_frame_and_teach
    tutor_plan_res = UniversalInteractiveTutor.analyze_paused_frame_and_teach(
        video_url_or_id="https://youtube.com/watch?v=sample123",
        user_question="Pythagoras theorem right-angle triangle a^2+b^2=c^2 geometric proof"
    )
    assert tutor_plan_res["status"] == "success", f"analyze_paused_frame_and_teach failed: {tutor_plan_res}"
    print(f"  [PASS] UniversalInteractiveTutor.analyze_paused_frame_and_teach exact signature verified")


def test_extended_capabilities_manager_facade():
    print("\n" + "="*70)
    print("TEST 4: EXTENDED CAPABILITIES MANAGER & UNIVERSAL AGENT CAPABILITIES")
    print("="*70)

    from core_organs.organ_10_extended_capabilities import ExtendedCapabilitiesManager
    from core_organs.organ_10_agents import UniversalAgentCapabilities

    # 1. Test Manager Knowledge Store & Query
    k_store = ExtendedCapabilitiesManager.execute("KNOWLEDGE_STORE", topic="Architecture Note", content="Organ 10 unified suite online.", tags="architecture")
    assert k_store["status"] == "success", f"Knowledge store failed: {k_store}"
    print(f"  [PASS] ExtendedCapabilitiesManager KNOWLEDGE_STORE: note id {k_store['note_id']}")

    k_query = ExtendedCapabilitiesManager.execute("KNOWLEDGE_QUERY", query="Architecture")
    assert len(k_query["notes"]) > 0, "Knowledge query returned empty"
    print(f"  [PASS] ExtendedCapabilitiesManager KNOWLEDGE_QUERY: {len(k_query['notes'])} notes found")

    # 2. Test Manager File Search
    f_search = ExtendedCapabilitiesManager.execute("FILE_SEARCH", root_dir=str(TEST_DIR), pattern="*.docx")
    assert f_search["status"] == "success" and f_search["total_found"] > 0, f"File search failed: {f_search}"
    print(f"  [PASS] ExtendedCapabilitiesManager FILE_SEARCH: {f_search['total_found']} .docx files located")

    # 3. Test UniversalAgentCapabilities interface on Organ 10
    uac_res = UniversalAgentCapabilities.execute("KNOWLEDGE_QUERY", query="Architecture")
    assert len(uac_res["notes"]) > 0, "UniversalAgentCapabilities query failed"
    print("  [PASS] UniversalAgentCapabilities facade on Organ 10 verified")


if __name__ == "__main__":
    setup_test_environment()
    test_omni_file_engine()
    test_ultra_res_painting_engine()
    test_universal_interactive_tutor()
    test_extended_capabilities_manager_facade()
    print("\n" + "="*70)
    print("ALL TEST SUITES PASSED FLAWLESSLY WITH 100% SUCCESS!")
    print("="*70)

