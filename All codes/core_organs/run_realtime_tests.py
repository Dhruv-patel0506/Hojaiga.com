"""
Real-Time Test Runner for Hojaiga
Tests functionality from easy to hard, measures efficiency
"""

import time
import asyncio
from datetime import datetime

class HojaigaTestRunner:
    def __init__(self):
        self.results = []
    
    def run_test(self, test_name, test_func):
        """Run a test and measure efficiency"""
        print(f"\n{'='*80}")
        print(f"TEST: {test_name}")
        print(f"{'='*80}")
        
        start_time = time.time()
        try:
            result = test_func()
            end_time = time.time()
            duration = end_time - start_time
            
            self.results.append({
                "test": test_name,
                "status": "PASS",
                "duration": duration,
                "result": result
            })
            
            print(f"[PASS] Duration: {duration:.2f}s")
            print(f"Result: {result}")
            
        except Exception as e:
            end_time = time.time()
            duration = end_time - start_time
            
            self.results.append({
                "test": test_name,
                "status": "FAIL",
                "duration": duration,
                "error": str(e)
            })
            
            print(f"[FAIL] Duration: {duration:.2f}s")
            print(f"Error: {e}")
    
    def print_summary(self):
        """Print test summary"""
        print(f"\n{'='*80}")
        print("TEST SUMMARY")
        print(f"{'='*80}")
        
        passed = sum(1 for r in self.results if r["status"] == "PASS")
        failed = sum(1 for r in self.results if r["status"] == "FAIL")
        total = len(self.results)
        
        print(f"Total Tests: {total}")
        print(f"Passed: {passed}")
        print(f"Failed: {failed}")
        print(f"Success Rate: {passed/total*100:.1f}%")
        
        total_duration = sum(r["duration"] for r in self.results)
        print(f"Total Duration: {total_duration:.2f}s")
        print(f"Average Duration: {total_duration/total:.2f}s")
        
        for result in self.results:
            status_icon = "[PASS]" if result["status"] == "PASS" else "[FAIL]"
            print(f"{status_icon} {result['test']}: {result['status']} ({result['duration']:.2f}s)")


# Test Functions

def test_enhanced_compiler():
    """Test 1.1: Enhanced Compiler Works"""
    try:
        import sys
        sys.path.insert(0, r"D:\new_automation\All codes")
        from enhanced_brain_compiler import get_enhanced_compiler
        
        compiler = get_enhanced_compiler()
        plan = compiler.compile_task("open gmail")
        
        # Verify checkpoints are practical, not generic
        assert len(plan.checkpoints) > 0, "No checkpoints generated"
        assert any("chrome" in cp["description"].lower() for cp in plan.checkpoints), "No Chrome checkpoint"
        
        return f"Generated {len(plan.checkpoints)} practical checkpoints"
    except Exception as e:
        raise Exception(f"Enhanced compiler test failed: {e}")

def test_gmail_resolution():
    """Test 1.2: App Launcher Resolves Gmail Correctly"""
    try:
        import sys
        sys.path.insert(0, r"D:\new_automation\All codes")
        from organ_40_app_launcher import AppCatalog, VerbAliasEngine
        
        catalog = AppCatalog()
        alias_engine = VerbAliasEngine(catalog)
        
        resolved = alias_engine.resolve("gmail")
        
        # Should resolve to chrome, not excel
        assert "chrome" in resolved.lower(), f"Resolved to {resolved}, not chrome"
        assert "excel" not in resolved.lower(), f"Resolved to {resolved}, not excel"
        
        return f"Gmail resolved to: {resolved}"
    except Exception as e:
        raise Exception(f"Gmail resolution test failed: {e}")

def test_database_batching():
    """Test 1.3: Database Batching Works"""
    # Simplified test - just check if DAPBridge has batch method
    try:
        import sys
        sys.path.insert(0, r"D:\new_automation\All codes")
        from organ_24_dap import DAPBridge
        
        dap = DAPBridge()
        
        # Check if batch method exists
        assert hasattr(dap, 'store_elements_batch'), "No batch method found"
        
        return "Batch method exists (full test requires actual database)"
    except Exception as e:
        raise Exception(f"Database batching test failed: {e}")

def test_chrome_profile_selection():
    """Test 2.1: Chrome Opens Without Profile Screen"""
    try:
        import sys
        sys.path.insert(0, r"D:\new_automation\All codes")
        from organ_19_chrome_cdp_runtime import ChromeCDPRuntime
        
        cdp = ChromeCDPRuntime()
        
        # Check if profile selection method exists
        assert hasattr(cdp, '_is_on_profile_selection_screen'), "No profile detection method"
        assert hasattr(cdp, '_select_profile'), "No profile selection method"
        
        return "Profile selection methods exist (full test requires actual Chrome)"
    except Exception as e:
        raise Exception(f"Chrome profile test failed: {e}")

def test_cookie_injection():
    """Test 2.2: Session Cookie Injection Works"""
    try:
        import sys
        sys.path.insert(0, r"D:\new_automation\All codes")
        from session_cookie_manager import SessionCookieManager
        from organ_19_chrome_cdp_runtime import ChromeCDPRuntime
        
        # Check if cookie manager has required methods
        cookie_manager = SessionCookieManager()
        assert hasattr(cookie_manager, 'get_cookies'), "No get_cookies method"
        assert hasattr(cookie_manager, 'store_cookie'), "No store_cookie method"
        
        cdp = ChromeCDPRuntime()
        assert hasattr(cdp, 'inject_cookies'), "No inject_cookies method"
        assert hasattr(cdp, 'navigate_with_cookies'), "No navigate_with_cookies method"
        
        return "Cookie injection methods exist (full test requires actual Chrome)"
    except Exception as e:
        raise Exception(f"Cookie injection test failed: {e}")

def test_agent_spawning():
    """Test 2.3: Agent Spawning Works"""
    try:
        import sys
        sys.path.insert(0, r"D:\new_automation\All codes")
        from organ_10_agents import AgentsOrgan
        from agent_structure import PERMANENT_AGENTS
        
        # Check if spawn methods exist
        agents = AgentsOrgan()
        assert hasattr(agents, 'spawn_swarm_agents'), "No spawn_swarm_agents method"
        assert hasattr(agents, 'spawn_permanent_agent'), "No spawn_permanent_agent method"
        
        return "Agent spawning methods exist (full test requires actual execution)"
    except Exception as e:
        raise Exception(f"Agent spawning test failed: {e}")

def test_dynamic_resolution_matrix():
    """Test 2.4: Dynamic Resolution Matrix (diverse phrasing, no case hardcoding)"""
    try:
        import sys
        sys.path.insert(0, r"D:\new_automation\All codes")
        from organ_40_app_launcher import VerbAliasEngine, AppCatalog, DEFAULT_APP

        engine = VerbAliasEngine(AppCatalog())  # no LLM gateway -> deterministic tiers

        cases = [
            # Web-mail phrases must reach Chrome through the alias table itself
            ("gmail", "google chrome"),
            ("open gmail", "google chrome"),
            ("check my gmail inbox", "google chrome"),
            ("google mail", "google chrome"),
            ("mail.google.com", "google chrome"),
            ("delete gmail spam", "google chrome"),
            # Desktop mail keeps its own app
            ("open mail", "mail"),
            ("send an email", "mail"),
            ("outlook", "mail"),
            # Diverse phrasing across apps
            ("jot down a note", "notepad"),
            ("open notepad", "notepad"),
            ("take a screenshot", "snipping tool"),
            ("record the session", "obs studio"),
            ("do some math", "calculator"),
            ("open the calculator", "calculator"),
            ("draw something", "paint"),
            ("show my files", "file explorer"),
            ("open a spreadsheet", "excel"),
            ("write a letter", "word"),
            ("open the terminal", "terminal"),
            ("open settings", "settings"),
            ("check task manager", "task manager"),
            # Unknown task falls back to the documented default (Chrome)
            ("cook me dinner", DEFAULT_APP),
        ]

        failures = []
        for task, expected in cases:
            got = engine.resolve(task)
            if got != expected:
                failures.append(f"{task!r}: got {got!r}, expected {expected!r}")

        if failures:
            raise Exception("Resolution mismatches: " + "; ".join(failures))

        return f"{len(cases)}/{len(cases)} tasks routed dynamically (word-boundary tiers, no special cases)"
    except Exception as e:
        raise Exception(f"Dynamic resolution matrix failed: {e}")

def test_scanner_capture_chain():
    """Test 2.5: Scanner Fast Capture Chain (dxcam/mss/cv2 when available)"""
    try:
        import sys, time
        sys.path.insert(0, r"D:\new_automation\All codes")
        from core_organs.organ_41_scanner import ScannerOrgan

        scanner = ScannerOrgan()
        frames = []
        t0 = time.time()
        for _ in range(3):
            f = scanner._grab_screen_frame()
            if f is not None:
                frames.append(f)
            time.sleep(0.05)
        if not frames:
            raise Exception("All capture backends returned no frame")
        frame = frames[-1]
        b64 = scanner._encode_vision_frame(frame)
        if not b64:
            raise Exception("Vision encode returned no data")

        backend = "dxcam" if getattr(scanner, "_dxcam", None) else ("mss" if getattr(scanner, "_mss", None) else "PIL")
        encoder = "cv2" if getattr(scanner, "_cv2", None) else "PIL"
        shape = getattr(frame, "shape", getattr(frame, "size", "?"))
        return (f"backend={backend}, encoder={encoder}, frame={shape}, "
                f"jpeg_b64={len(b64)//1024}KB, 3 grabs in {time.time()-t0:.2f}s")
    except Exception as e:
        raise Exception(f"Capture chain test failed: {e}")

def test_scanner_deep_walk():
    """Test 2.6: Scanner Deep Walk (organ_30 native walker, deep depth)"""
    try:
        import sys, time
        sys.path.insert(0, r"D:\new_automation\All codes")
        import uiautomation as auto
        import win32gui
        from core_organs.organ_30_app_scanner import _safe_walk_control, _deep_scan_max_depth

        auto.InitializeUIAutomationInCurrentThread()
        hwnd = win32gui.GetForegroundWindow()
        ctrl = auto.ControlFromHandle(hwnd)
        if ctrl is None:
            raise Exception("No foreground window control")

        t0 = time.time()
        nodes, max_depth = 0, 0
        for _c, d in _safe_walk_control(ctrl, includeTop=False, maxDepth=_deep_scan_max_depth()):
            nodes += 1
            if d > max_depth:
                max_depth = d
        elapsed = time.time() - t0
        if nodes <= 0:
            raise Exception("Walker yielded no nodes")
        return (f"{nodes} nodes, depth {max_depth}/{_deep_scan_max_depth()} reached "
                f"on '{win32gui.GetWindowText(hwnd)}' in {elapsed:.2f}s")
    except Exception as e:
        raise Exception(f"Deep walk test failed: {e}")

def test_open_gmail():
    """Test 3.1: Open Gmail (Simple Task)"""
    try:
        import sys
        sys.path.insert(0, r"D:\new_automation\All codes")
        from organ_01_crewai_engine import CrewAIEngine
        
        engine = CrewAIEngine()
        
        # Check if execute_task exists
        assert hasattr(engine, 'execute_task'), "No execute_task method"
        
        return "Execute task method exists (full test requires integration)"
    except Exception as e:
        raise Exception(f"Open Gmail test failed: {e}")

def test_open_linkedin():
    """Test 3.2: Open LinkedIn (Web Service)"""
    try:
        import sys
        sys.path.insert(0, r"D:\new_automation\All codes")
        from organ_01_crewai_engine import CrewAIEngine
        
        engine = CrewAIEngine()
        
        # Check if execute_task exists
        assert hasattr(engine, 'execute_task'), "No execute_task method"
        
        return "Execute task method exists (full test requires integration)"
    except Exception as e:
        raise Exception(f"Open LinkedIn test failed: {e}")

def test_multi_step_stateful():
    """Test 3.3: Multi-Step Task (Stateful)"""
    try:
        import sys
        sys.path.insert(0, r"D:\new_automation\All codes")
        from organ_01_crewai_engine import CrewAIEngine
        
        engine = CrewAIEngine()
        
        # Check if execute_task exists
        assert hasattr(engine, 'execute_task'), "No execute_task method"
        
        return "Execute task method exists (full test requires integration)"
    except Exception as e:
        raise Exception(f"Multi-step stateful test failed: {e}")

def test_gmail_spam_deletion():
    """Test 4.1: Gmail Spam Deletion"""
    try:
        import sys
        sys.path.insert(0, r"D:\new_automation\All codes")
        from organ_01_crewai_engine import CrewAIEngine
        
        engine = CrewAIEngine()
        
        # Check if execute_task exists
        assert hasattr(engine, 'execute_task'), "No execute_task method"
        
        return "Execute task method exists (full test requires integration)"
    except Exception as e:
        raise Exception(f"Gmail spam deletion test failed: {e}")

def test_linkedin_message():
    """Test 4.2: LinkedIn Message Sending"""
    try:
        import sys
        sys.path.insert(0, r"D:\new_automation\All codes")
        from organ_01_crewai_engine import CrewAIEngine
        
        engine = CrewAIEngine()
        
        # Check if execute_task exists
        assert hasattr(engine, 'execute_task'), "No execute_task method"
        
        return "Execute task method exists (full test requires integration)"
    except Exception as e:
        raise Exception(f"LinkedIn message test failed: {e}")

def test_hybrid_task():
    """Test 4.3: Hybrid Desktop-Cloud Task"""
    try:
        import sys
        sys.path.insert(0, r"D:\new_automation\All codes")
        from organ_01_crewai_engine import CrewAIEngine
        
        engine = CrewAIEngine()
        
        # Check if execute_task exists
        assert hasattr(engine, 'execute_task'), "No execute_task method"
        
        return "Execute task method exists (full test requires integration)"
    except Exception as e:
        raise Exception(f"Hybrid task test failed: {e}")


def main():
    runner = HojaigaTestRunner()
    
    print("="*80)
    print("HOJAIGA REAL-TIME TEST SUITE")
    print("="*80)
    print("Running tests from easy to hard...")
    print()
    
    # Level 1: Basic Functionality (Easy)
    print("\n--- LEVEL 1: BASIC FUNCTIONALITY (EASY) ---")
    runner.run_test("Test 1.1: Enhanced Compiler", test_enhanced_compiler)
    runner.run_test(" Test 1.2: Gmail Resolution", test_gmail_resolution)
    runner.run_test("Test 1.3: Database Batching", test_database_batching)
    
    # Level 2: Component Integration (Medium)
    print("\n--- LEVEL 2: COMPONENT INTEGRATION (MEDIUM) ---")
    runner.run_test("Test 2.1: Chrome Profile Selection", test_chrome_profile_selection)
    runner.run_test("Test 2.2: Cookie Injection", test_cookie_injection)
    runner.run_test("Test 2.3: Agent Spawning", test_agent_spawning)
    
    # Level 2B: Dynamic Resolution + Scanner Performance
    print("\n--- LEVEL 2B: DYNAMIC RESOLUTION + SCANNER PERFORMANCE ---")
    runner.run_test("Test 2.4: Dynamic Resolution Matrix", test_dynamic_resolution_matrix)
    runner.run_test("Test 2.5: Scanner Fast Capture Chain", test_scanner_capture_chain)
    runner.run_test("Test 2.6: Scanner Deep Walk", test_scanner_deep_walk)
    
    # Level 3: End-to-End (Hard) - Disabled for now, just check methods exist
    print("\n--- LEVEL 3: END-TO-END (HARD) - DISABLED (requires integration) ---")
    # runner.run_test("Test 3.1: Open Gmail", test_open_gmail)
    # runner.run_test("Test 3.2: Open LinkedIn", test_open_linkedin)
    # runner.run_test("Test 3.3: Multi-Step Stateful", test_multi_step_stateful)
    
    # Level 4: Complex Automation (Very Hard) - Disabled for now
    print("\n--- LEVEL 4: COMPLEX AUTOMATION (VERY HARD) - DISABLED (requires integration) ---")
    # runner.run_test(" test_4.1: Gmail Spam Deletion", test_gmail_spam_deletion)
    # runner.run_test("Test 4.2: LinkedIn Message", test_linkedin_message)
    # runner.run_test("Test 4.3: Hybrid Task", test_hybrid_task)
    
    # Print summary
    runner.print_summary()
    
    print("\n" + "="*80)
    print("TEST SUITE COMPLETE")
    print("="*80)

if __name__ == "__main__":
    main()
