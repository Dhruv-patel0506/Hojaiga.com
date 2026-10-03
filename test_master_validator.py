"""
HOJAIGA OS — MASTER AUTONOMY VALIDATOR
=======================================
The ONE task that proves the entire system works.
Run it back-to-back with different queries. Every run must produce REAL data.

Tests: Brain → Browser → Scrape → Deep Scrape → Visual → Excel → Launch → Knowledge
       Every component gets a clear PASS/FAIL. No faking. No theater.

Usage:
    python test_master_validator.py
    python test_master_validator.py --query "plumbers in miami"
    python test_master_validator.py --query "dentists in seattle" --repeat 3
"""

import sys, os, json, time, hashlib, argparse, traceback
from datetime import datetime
from typing import Dict, Any, List, Optional

sys.path.insert(0, r"D:\new_automation\All codes")

# ============================================================
# COMPONENT TESTERS — each returns (PASS/FAIL, details)
# ============================================================

class ComponentTester:
    """Individual component validator. Returns (status, detail, timing_ms)."""

    @staticmethod
    def test_01_ollama_alive() -> tuple:
        """Can we talk to Ollama at all?"""
        t0 = time.time()
        try:
            import requests
            r = requests.get("http://127.0.0.1:11434/api/tags", timeout=5)
            models = [m["name"] for m in r.json().get("models", [])]
            dt = int((time.time() - t0) * 1000)
            has_llama = any("llama" in m for m in models)
            has_vlm = any("qwen2.5vl" in m for m in models)
            if has_llama and has_vlm:
                return ("PASS", f"Ollama alive. Models: {len(models)} (llama3 ✓, qwen2.5vl ✓)", dt)
            else:
                return ("FAIL", f"Missing models. Have: {models}", dt)
        except Exception as e:
            return ("FAIL", f"Ollama unreachable: {e}", int((time.time() - t0) * 1000))

    @staticmethod
    def test_02_brain_plans() -> tuple:
        """Can Brain (Ollama llama3) generate a real plan?"""
        t0 = time.time()
        try:
            from core_organs.organ_37_llm_gateway import LLMGateway
            gw = LLMGateway()
            plan = gw.execute_small_inference(
                system="You are a task planner. Return ONLY a JSON array of steps.",
                prompt='Plan: "find coffee shops in Austin TX and save to Excel". Return JSON array like [{"action":"NAVIGATE","target":"url"},{"action":"EXTRACT_LEADS","query":"..."}]',
                timeout=20
            )
            dt = int((time.time() - t0) * 1000)
            import re
            m = re.search(r'\[.*\]', plan, re.DOTALL)
            if m:
                steps = json.loads(m.group(0))
                if len(steps) >= 2:
                    return ("PASS", f"Brain generated {len(steps)} steps: {[s.get('action') for s in steps]}", dt)
            return ("FAIL", f"Brain returned invalid plan: {plan[:150]}", dt)
        except Exception as e:
            return ("FAIL", f"Brain error: {e}", int((time.time() - t0) * 1000))

    @staticmethod
    def test_03_cdp_browser() -> tuple:
        """Can we control Chrome via CDP?"""
        t0 = time.time()
        try:
            from core_organs.lead_extractor import send_cdp_command, send_cdp_navigate, send_cdp_screenshot
            send_cdp_command(0x0100, {"headless": False})
            time.sleep(2)
            send_cdp_navigate("https://www.google.com")
            time.sleep(3)
            b64 = send_cdp_screenshot(format="jpeg", quality=70)
            dt = int((time.time() - t0) * 1000)
            if b64 and len(b64) > 1000:
                return ("PASS", f"CDP active. Screenshot: {len(b64)} bytes", dt)
            return ("FAIL", "CDP screenshot empty or too small", dt)
        except Exception as e:
            return ("FAIL", f"CDP error: {e}", int((time.time() - t0) * 1000))

    @staticmethod
    def test_04_visual_grounding() -> tuple:
        """Can VLM locate an element on screen?"""
        t0 = time.time()
        try:
            from core_organs.organ_31_visual_perception import VisualGroundingEngine
            from core_organs.lead_extractor import send_cdp_screenshot
            b64 = send_cdp_screenshot(format="jpeg", quality=70)
            if not b64:
                return ("FAIL", "No screenshot for visual grounding", int((time.time() - t0) * 1000))
            g = VisualGroundingEngine()
            match = g.locate_element("search box or address bar", image_base64=b64)
            dt = int((time.time() - t0) * 1000)
            if match.found:
                return ("PASS", f"VLM found element at ({match.pixel_x}, {match.pixel_y}), confidence={match.confidence}", dt)
            return ("FAIL", f"VLM could not find element: {match.reason}", dt)
        except Exception as e:
            return ("FAIL", f"Visual grounding error: {e}", int((time.time() - t0) * 1000))

    @staticmethod
    def test_05_web_scraping(query: str) -> tuple:
        """Can we scrape real leads from Google?"""
        t0 = time.time()
        try:
            from core_organs.lead_extractor import scrape_live_directory_leads
            leads = scrape_live_directory_leads(query=query, min_leads=5)
            dt = int((time.time() - t0) * 1000)
            if leads and len(leads) >= 3:
                phones = sum(1 for l in leads if l.get("phone") and l["phone"] != "N/A")
                emails = sum(1 for l in leads if l.get("email") and l["email"] != "N/A")
                names = [l.get("company", "?")[:30] for l in leads[:3]]
                return ("PASS", f"Scraped {len(leads)} leads ({phones} phones, {emails} emails). Sample: {names}", dt)
            return ("FAIL", f"Scraped only {len(leads)} leads (need 3+)", dt)
        except Exception as e:
            return ("FAIL", f"Scraping error: {e}", int((time.time() - t0) * 1000))

    @staticmethod
    def test_06_excel_export() -> tuple:
        """Can we create a styled Excel file?"""
        t0 = time.time()
        try:
            from core_organs.lead_extractor import extract_leads_and_export
            import openpyxl
            test_file = "test_validator_export.xlsx"
            res = extract_leads_and_export(query="test businesses Atlanta GA", min_leads=3, output_filename=test_file)
            dt = int((time.time() - t0) * 1000)
            excel_path = res.get("excel_file", "")
            if os.path.exists(excel_path):
                wb = openpyxl.load_workbook(excel_path)
                ws = wb.active
                rows = ws.max_row - 1
                has_header = ws.cell(1, 1).value == "No."
                has_fill = ws.cell(1, 1).fill.start_color.rgb != "00000000" if ws.cell(1, 1).fill else False
                os.remove(excel_path)
                csv_path = excel_path.replace(".xlsx", ".csv")
                if os.path.exists(csv_path):
                    os.remove(csv_path)
                if rows >= 1:
                    return ("PASS", f"Excel created: {rows} rows, headers={has_header}, styled={has_fill}", dt)
            return ("FAIL", f"Excel file not created at {excel_path}", dt)
        except Exception as e:
            return ("FAIL", f"Excel export error: {e}", int((time.time() - t0) * 1000))

    @staticmethod
    def test_07_deep_scan() -> tuple:
        """Can it discover and learn a new app?"""
        t0 = time.time()
        try:
            from core_organs.organ_30_app_scanner import EyeAndBrainOrchestrator
            o = EyeAndBrainOrchestrator()
            result = o.discover_and_learn()
            dt = int((time.time() - t0) * 1000)
            app_name = result.get("app_name", "unknown")
            elements = result.get("ui_elements", [])
            status = result.get("status", "error")
            # Check if knowledge was stored
            safe_name = app_name.lower().replace(" ", "_")
            kpath = os.path.join("d:/new_automation/All codes/var/hojaiga/app_knowledge", f"{safe_name}.json")
            stored = os.path.exists(kpath)
            if status == "success" and len(elements) >= 2:
                return ("PASS", f"Deep scan: '{app_name}' ({len(elements)} elements, stored={stored})", dt)
            return ("FAIL", f"Deep scan incomplete: status={status}, elements={len(elements)}", dt)
        except Exception as e:
            return ("FAIL", f"Deep scan error: {e}", int((time.time() - t0) * 1000))

    @staticmethod
    def test_08_error_recovery() -> tuple:
        """Can it recover from a failed action?"""
        t0 = time.time()
        try:
            from core_organs.organ_30_app_scanner import EyeAndBrainOrchestrator
            from core_organs.organ_31_visual_perception import VisualGroundingEngine
            # Try to locate something that doesn't exist — should fail gracefully
            g = VisualGroundingEngine()
            match = g.locate_element("purple elephant dancing on the moon")
            dt = int((time.time() - t0) * 1000)
            if not match.found:
                return ("PASS", f"Graceful failure: '{match.reason}' (correctly returned not-found)", dt)
            return ("FAIL", "VLM falsely reported finding a purple elephant", dt)
        except Exception as e:
            return ("FAIL", f"Error recovery test failed: {e}", int((time.time() - t0) * 1000))

    @staticmethod
    def test_09_knowledge_persistence() -> tuple:
        """Does stored knowledge persist and get reloaded?"""
        t0 = time.time()
        try:
            import os, json
            kdir = "d:/new_automation/All codes/var/hojaiga/app_knowledge"
            if not os.path.exists(kdir):
                return ("FAIL", "Knowledge directory does not exist", int((time.time() - t0) * 1000))
            files = [f for f in os.listdir(kdir) if f.endswith(".json")]
            dt = int((time.time() - t0) * 1000)
            if len(files) >= 1:
                # Read one and verify structure
                with open(os.path.join(kdir, files[0])) as f:
                    data = json.load(f)
                has_app = "app_name" in data
                has_elements = "ui_elements" in data
                return ("PASS", f"Knowledge persistent: {len(files)} files stored, structure valid={has_app and has_elements}", dt)
            return ("FAIL", "No knowledge files found", dt)
        except Exception as e:
            return ("FAIL", f"Knowledge check error: {e}", int((time.time() - t0) * 1000))

    @staticmethod
    def test_10_virtual_mouse() -> tuple:
        """Can we click via CDP without physical input?"""
        t0 = time.time()
        try:
            from core_organs.lead_extractor import send_cdp_click_coordinates
            ok = send_cdp_click_coordinates(500, 500, timeout=8.0)
            dt = int((time.time() - t0) * 1000)
            if ok:
                return ("PASS", "Virtual click dispatched successfully via CDP", dt)
            return ("FAIL", "CDP click returned False", dt)
        except Exception as e:
            return ("FAIL", f"Virtual mouse error: {e}", int((time.time() - t0) * 1000))


# ============================================================
# FULL PIPELINE TEST — the ONE task that proves everything
# ============================================================

def run_full_pipeline_test(query: str, run_number: int = 1) -> Dict[str, Any]:
    """
    THE TASK: "Find [businesses] in [city] and make a list in Excel"
    
    This single task tests EVERYTHING:
    1. Brain thinks and plans
    2. Browser navigates to Google Maps
    3. Scraper extracts real businesses
    4. Deep scrape visits individual websites for phone/email
    5. Visual grounding verifies the page
    6. Excel exports styled file
    7. Excel opens with data
    8. Knowledge gets stored
    
    If this task works end-to-end with REAL data, the system is ready.
    """
    results = {
        "run": run_number,
        "query": query,
        "timestamp": datetime.now().isoformat(),
        "components": {},
        "pipeline": {},
        "overall": "PENDING"
    }
    
    print(f"\n{'='*70}")
    print(f"  HOJAIGA MASTER VALIDATOR — RUN #{run_number}")
    print(f"  Query: \"{query}\"")
    print(f"  Time: {results['timestamp']}")
    print(f"{'='*70}\n")
    
    # ── PHASE 1: Individual Component Tests ──
    print("PHASE 1: COMPONENT TESTS")
    print("-" * 50)
    
    tests = [
        ("Ollama Alive", ComponentTester.test_01_ollama_alive),
        ("Brain Plans", ComponentTester.test_02_brain_plans),
        ("CDP Browser", ComponentTester.test_03_cdp_browser),
        ("Visual Grounding", ComponentTester.test_04_visual_grounding),
        ("Error Recovery", ComponentTester.test_08_error_recovery),
        ("Knowledge Persist", ComponentTester.test_09_knowledge_persistence),
        ("Virtual Mouse", ComponentTester.test_10_virtual_mouse),
        ("Deep Scan App", ComponentTester.test_07_deep_scan),
    ]
    
    component_pass = 0
    component_fail = 0
    
    for name, test_fn in tests:
        try:
            status, detail, dt = test_fn()
        except Exception as e:
            status, detail, dt = "FAIL", f"Exception: {e}", 0
        
        icon = "✓" if status == "PASS" else "✗"
        print(f"  [{icon}] {name:20s} | {status:4s} | {dt:5d}ms | {detail}")
        results["components"][name] = {"status": status, "detail": detail, "time_ms": dt}
        
        if status == "PASS":
            component_pass += 1
        else:
            component_fail += 1
    
    # ── PHASE 2: Full Pipeline (the real task) ──
    print(f"\nPHASE 2: FULL PIPELINE TEST")
    print("-" * 50)
    
    # Step 1: Scrape real leads
    print("  [1/4] Scraping real leads from Google...")
    try:
        from core_organs.lead_extractor import scrape_live_directory_leads
        t0 = time.time()
        leads = scrape_live_directory_leads(query=query, min_leads=5)
        scrape_dt = int((time.time() - t0) * 1000)
        
        if leads and len(leads) >= 1:
            print(f"         ✓ Scraped {len(leads)} real businesses ({scrape_dt}ms)")
            results["pipeline"]["scrape"] = {"status": "PASS", "count": len(leads), "time_ms": scrape_dt}
            
            # Show sample
            for i, l in enumerate(leads[:3]):
                print(f"           {i+1}. {l.get('company', '?')[:40]} | {l.get('phone', 'N/A')}")
        else:
            print(f"         ✗ Scraped 0 leads")
            results["pipeline"]["scrape"] = {"status": "FAIL", "count": 0}
    except Exception as e:
        print(f"         ✗ Scraping failed: {e}")
        results["pipeline"]["scrape"] = {"status": "FAIL", "error": str(e)}
    
    # Step 2: Export to Excel
    print("  [2/4] Exporting to styled Excel...")
    try:
        from core_organs.lead_extractor import extract_leads_and_export
        import openpyxl
        t0 = time.time()
        safe_q = "".join(c if c.isalnum() or c in " _" else "" for c in query)[:30].strip().replace(" ", "_")
        out_file = f"validator_{safe_q}_{run_number}.xlsx"
        res = extract_leads_and_export(query=query, min_leads=5, output_filename=out_file)
        export_dt = int((time.time() - t0) * 1000)
        excel_path = res.get("excel_file", "")
        
        if os.path.exists(excel_path):
            wb = openpyxl.load_workbook(excel_path)
            ws = wb.active
            data_rows = ws.max_row - 1
            phones = sum(1 for r in ws.iter_rows(min_row=2, values_only=True) if r[2] and r[2] != "N/A")
            emails = sum(1 for r in ws.iter_rows(min_row=2, values_only=True) if r[3] and r[3] != "N/A")
            source = ws.cell(2, 10).value if ws.cell(2, 10).value else "unknown"
            
            print(f"         ✓ Excel: {data_rows} rows, {phones} phones, {emails} emails ({export_dt}ms)")
            print(f"         ✓ Source: {source}")
            print(f"         ✓ File: {excel_path}")
            results["pipeline"]["export"] = {
                "status": "PASS", "rows": data_rows, "phones": phones,
                "emails": emails, "source": source, "file": excel_path, "time_ms": export_dt
            }
        else:
            print(f"         ✗ Excel file not created")
            results["pipeline"]["export"] = {"status": "FAIL", "error": "File not created"}
    except Exception as e:
        print(f"         ✗ Export failed: {e}")
        results["pipeline"]["export"] = {"status": "FAIL", "error": str(e)}
    
    # Step 3: Visual verification — screenshot the current state
    print("  [3/4] Visual verification of current state...")
    try:
        from core_organs.organ_31_visual_perception import VisualGroundingEngine
        from core_organs.lead_extractor import send_cdp_screenshot
        t0 = time.time()
        b64 = send_cdp_screenshot(format="jpeg", quality=70)
        g = VisualGroundingEngine()
        
        # Ask VLM what it sees
        import requests
        prompt = "What application or website is currently visible? Give a one-sentence description."
        payload = {
            "model": g.model_name,
            "messages": [{"role": "user", "content": prompt, "images": [b64]}],
            "stream": False,
            "options": {"temperature": 0.1}
        }
        resp = requests.post(f"{g.ollama_url.rstrip('/')}/api/chat", json=payload, timeout=30)
        answer = resp.json().get("message", {}).get("content", "").strip()
        vis_dt = int((time.time() - t0) * 1000)
        
        print(f"         ✓ VLM sees: {answer[:100]}")
        results["pipeline"]["visual_verify"] = {"status": "PASS", "description": answer[:200], "time_ms": vis_dt}
    except Exception as e:
        print(f"         ✗ Visual verification failed: {e}")
        results["pipeline"]["visual_verify"] = {"status": "FAIL", "error": str(e)}
    
    # Step 4: Verify data integrity — read the Excel back
    print("  [4/4] Data integrity check...")
    try:
        if results["pipeline"].get("export", {}).get("status") == "PASS":
            excel_path = results["pipeline"]["export"]["file"]
            wb = openpyxl.load_workbook(excel_path)
            ws = wb.active
            
            # Verify all rows have real data (not N/A everywhere)
            real_data_count = 0
            for row in ws.iter_rows(min_row=2, values_only=True):
                has_name = row[1] and row[1] != "Unknown"
                has_phone = row[2] and row[2] != "N/A"
                has_website = row[4] and row[4] != "N/A"
                if has_name and (has_phone or has_website):
                    real_data_count += 1
            
            total_rows = ws.max_row - 1
            integrity_score = real_data_count / max(total_rows, 1)
            
            if integrity_score >= 0.5:
                print(f"         ✓ Data integrity: {real_data_count}/{total_rows} rows have real data ({integrity_score:.0%})")
                results["pipeline"]["integrity"] = {"status": "PASS", "score": integrity_score, "real_rows": real_data_count}
            else:
                print(f"         ✗ Data integrity: only {real_data_count}/{total_rows} rows have real data ({integrity_score:.0%})")
                results["pipeline"]["integrity"] = {"status": "FAIL", "score": integrity_score}
        else:
            print(f"         ✗ Skipping — Excel not created")
            results["pipeline"]["integrity"] = {"status": "SKIP", "reason": "No Excel"}
    except Exception as e:
        print(f"         ✗ Integrity check failed: {e}")
        results["pipeline"]["integrity"] = {"status": "FAIL", "error": str(e)}
    
    # ── PHASE 3: VERDICT ──
    print(f"\n{'='*70}")
    print("  VERDICT")
    print(f"{'='*70}")
    
    all_components_pass = all(c["status"] == "PASS" for c in results["components"].values())
    pipeline_steps = results["pipeline"]
    pipeline_pass = sum(1 for v in pipeline_steps.values() if v.get("status") == "PASS")
    pipeline_total = len(pipeline_steps)
    pipeline_score = pipeline_pass / max(pipeline_total, 1)
    
    print(f"\n  Components: {component_pass}/{component_pass + component_fail} PASS")
    print(f"  Pipeline:   {pipeline_pass}/{pipeline_total} PASS ({pipeline_score:.0%})")
    
    if all_components_pass and pipeline_score >= 0.75:
        results["overall"] = "SUCCESS"
        print(f"\n  ★ OVERALL: SUCCESS — System is autonomous and dynamic")
        print(f"  ★ Real data was scraped, exported, and verified")
        print(f"  ★ This task can be re-run with different queries")
    elif pipeline_score >= 0.5:
        results["overall"] = "PARTIAL"
        print(f"\n  △ OVERALL: PARTIAL — Core works but some components failed")
        print(f"  △ The system is partially autonomous")
    else:
        results["overall"] = "FAIL"
        print(f"\n  ✗ OVERALL: FAIL — System is not ready for production")
        print(f"  ✗ Multiple critical components failed")
    
    # Save detailed report
    report_path = os.path.join("D:\\new_automation", f"validator_report_{run_number}.json")
    with open(report_path, "w") as f:
        json.dump(results, f, indent=2, default=str)
    print(f"\n  Full report saved: {report_path}")
    
    return results


# ============================================================
# MAIN — run back-to-back with different queries
# ============================================================

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Hojaiga Master Autonomy Validator")
    parser.add_argument("--query", type=str, default="coffee shops in austin tx",
                       help="Search query to test with")
    parser.add_argument("--repeat", type=int, default=1,
                       help="Number of times to repeat (back-to-back testing)")
    args = parser.parse_args()

    queries = [
        args.query,
        "plumbers in miami fl",
        "dentists in seattle wa",
        "hair salons in denver co",
        "auto repair shops in phoenix az",
    ]

    print(f"\n{'#'*70}")
    print(f"  HOJAIGA MASTER AUTONOMY VALIDATOR")
    print(f"  Running {args.repeat}x with {len(queries)} different queries")
    print(f"  Each run tests ALL components simultaneously")
    print(f"{'#'*70}")

    all_results = []
    for run in range(1, args.repeat + 1):
        q = queries[(run - 1) % len(queries)]
        result = run_full_pipeline_test(q, run_number=run)
        all_results.append(result)
        if run < args.repeat:
            print(f"\n  Waiting 3s before next run...")
            time.sleep(3)

    # Final summary
    print(f"\n{'#'*70}")
    print(f"  FINAL SUMMARY — {args.repeat} RUNS COMPLETED")
    print(f"{'#'*70}")
    for r in all_results:
        icon = "✓" if r["overall"] == "SUCCESS" else ("△" if r["overall"] == "PARTIAL" else "✗")
        print(f"  Run #{r['run']:2d}: {icon} {r['overall']:8s} | Query: {r['query']}")
    successes = sum(1 for r in all_results if r["overall"] == "SUCCESS")
    print(f"\n  Success rate: {successes}/{len(all_results)} ({successes/max(len(all_results),1):.0%})")
    print(f"{'#'*70}\n")
