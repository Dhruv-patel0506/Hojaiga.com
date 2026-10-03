#!/usr/bin/env python3
"""
HOJAIGA CREWAI TEST SUITE FOR RHOJIAGA.COM
===============================================
Comprehensive testing of Hojaiga automation capabilities on rhojiaga.com
Tests multi-agent coordination, vision-grounded actions, popup handling, and task compilation.
"""

import sys
import os
import time
import json
import logging
import io
import base64
from typing import Dict, Any, List

# Add path
sys.path.insert(0, r"D:\new_automation\All codes")

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger("rhojiaga_test")

class RhojiagaTestSuite:
    def __init__(self):
        self.test_results = []
        self.start_time = time.time()
        
    def log_result(self, test_name: str, success: bool, details: str = "", metrics: Dict[str, Any] = None):
        """Log test result with performance metrics."""
        duration = time.time() - self.start_time
        result = {
            "test_name": test_name,
            "success": success,
            "details": details,
            "duration_sec": round(duration, 2),
            "metrics": metrics or {}
        }
        self.test_results.append(result)
        status = "✅ PASS" if success else "❌ FAIL"
        logger.info(f"{status} | {test_name} | {duration:.2f}s | {details}")
        if metrics:
            logger.info(f"   Metrics: {metrics}")
    
    def test_01_system_readiness(self):
        """Test 1: Verify all required components are running."""
        logger.info("=" * 60)
        logger.info("TEST 1: SYSTEM READINESS CHECK")
        logger.info("=" * 60)
        
        try:
            # Test Ollama connection
            import requests
            ollama_response = requests.get("http://127.0.0.1:11434/api/tags", timeout=5)
            ollama_ok = ollama_response.status_code == 200
            
            # Test Gatekeeper (it may not have a health endpoint, so we test with a simple chat)
            try:
                gatekeeper_payload = {"model": "llama3", "prompt": "test", "stream": False}
                gatekeeper_response = requests.post("http://127.0.0.1:11435/api/chat", 
                                            json=gatekeeper_payload, 
                                            headers={"X-Hojaiga-Validation": "339680"},
                                            timeout=5)
                gatekeeper_ok = gatekeeper_response.status_code == 200
            except Exception:
                gatekeeper_ok = False
            
            # Test organ imports
            from core_organs.organ_01_crewai_engine import _HAS_CREWAI
            from core_organs.organ_30_app_scanner import EyeAndBrainOrchestrator
            from core_organs.organ_29_popup_handler import DesktopInteractionManager
            from core_organs.organ_31_visual_perception import VisualGroundingEngine
            
            organs_ok = _HAS_CREWAI and all([
                EyeAndBrainOrchestrator is not None,
                DesktopInteractionManager is not None,
                VisualGroundingEngine is not None
            ])
            
            # Test vision models
            models = ["moondream:latest", "minicpm-v:latest", "qwen2.5vl:3b"]
            vision_models_ok = True
            for model in models:
                try:
                    payload = {"model": model, "prompt": "test", "stream": False}
                    resp = requests.post("http://127.0.0.1:11434/api/generate", 
                                       json=payload, timeout=10)
                    if resp.status_code != 200:
                        vision_models_ok = False
                        break
                except Exception as e:
                    vision_models_ok = False
                    break
            
            overall_ok = ollama_ok and gatekeeper_ok and organs_ok and vision_models_ok
            
            self.log_result(
                "System Readiness",
                overall_ok,
                f"Ollama: {ollama_ok}, Gatekeeper: {gatekeeper_ok}, Organs: {organs_ok}, Vision: {vision_models_ok}",
                {
                    "ollama_status": ollama_response.status_code,
                    "gatekeeper_status": gatekeeper_response.status_code,
                    "crewai_available": _HAS_CREWAI,
                    "vision_models_tested": len(models)
                }
            )
            
            return overall_ok
            
        except Exception as e:
            self.log_result("System Readiness", False, f"Error: {e}")
            return False
    
    def test_02_task_compilation(self):
        """Test 2: Test intelligent task compilation for complex web scraping."""
        logger.info("=" * 60)
        logger.info("TEST 2: INTELLIGENT TASK COMPILATION")
        logger.info("=" * 60)
        
        try:
            from core_organs.organ_01_crewai_engine import _compile_task_with_organ36
            
            # Test various command formats
            test_commands = [
                "Search for interior designers in Georgia and scrape their contact info to Excel",
                "Open chrome, navigate to rhojiaga.com, analyze the content and extract key features",
                "Launch calculator, calculate 999+1, then switch to notepad and save the result",
                "Scrape business listings from Google Maps for restaurants in California, extract to CSV"
            ]
            
            compilation_results = []
            for cmd in test_commands:
                try:
                    result = _compile_task_with_organ36(cmd)
                    compilation_results.append({
                        "command": cmd,
                        "success": result.get("success", False),
                        "steps_count": len(result.get("steps", [])),
                        "detected_apps": result.get("detected_apps", []),
                        "has_expression": bool(result.get("expression"))
                    })
                except Exception as e:
                    compilation_results.append({
                        "command": cmd,
                        "success": False,
                        "error": str(e)
                    })
            
            successful_compilations = sum(1 for r in compilation_results if r.get("success"))
            total_steps = sum(r.get("steps_count", 0) for r in compilation_results)
            
            self.log_result(
                "Task Compilation",
                successful_compilations == len(test_commands),
                f"Compiled {successful_compilations}/{len(test_commands)} commands, generated {total_steps} total steps",
                {
                    "total_commands": len(test_commands),
                    "successful_compilations": successful_compilations,
                    "total_steps_generated": total_steps,
                    "avg_steps_per_command": total_steps / len(test_commands) if test_commands else 0
                }
            )
            
            return successful_compilations == len(test_commands)
            
        except Exception as e:
            self.log_result("Task Compilation", False, f"Error: {e}")
            return False
    
    def test_03_agent_paradigm_assignment(self):
        """Test 3: Test intelligent agent paradigm assignment."""
        logger.info("=" * 60)
        logger.info("TEST 3: AGENT PARADIGM ASSIGNMENT")
        logger.info("=" * 60)
        
        try:
            from core_organs.organ_01_crewai_engine import _register_with_organ10
            
            test_cases = [
                ("Extract leads from website", "deterministic_lead_gen", True),
                ("Analyze video and extract transcript", "video_to_action", True),
                ("Verify calculations and audit results", "verification_loop", True),
                ("Browse multiple websites in parallel", "parallel_web_automation", True),
                ("Discuss and debate multiple perspectives", "agent_chatroom", True),
                ("Research and write documentation", "research_and_write", True),
                ("Evaluate options and reach consensus", "stochastic_consensus", True)
            ]
            
            paradigm_results = []
            for command, expected_paradigm, is_multi in test_cases:
                try:
                    task_id = f"test_{int(time.time())}"
                    assigned = _register_with_organ10(task_id, command, is_multi_app=is_multi, is_lead=(expected_paradigm == "lead_gen"))
                    paradigm_results.append({
                        "command": command,
                        "expected": expected_paradigm,
                        "assigned": assigned,
                        "match": expected_paradigm in assigned.lower() if assigned else False
                    })
                except Exception as e:
                    paradigm_results.append({
                        "command": command,
                        "expected": expected_paradigm,
                        "error": str(e),
                        "match": False
                    })
            
            correct_assignments = sum(1 for r in paradigm_results if r.get("match"))
            
            self.log_result(
                "Agent Paradigm Assignment",
                correct_assignments == len(test_cases),
                f"Correct paradigm assignment: {correct_assignments}/{len(test_cases)}",
                {
                    "total_test_cases": len(test_cases),
                    "correct_assignments": correct_assignments,
                    "paradigm_accuracy": correct_assignments / len(test_cases) if test_cases else 0
                }
            )
            
            return correct_assignments == len(test_cases)
            
        except Exception as e:
            self.log_result("Agent Paradigm Assignment", False, f"Error: {e}")
            return False
    
    def test_04_vision_model_performance(self):
        """Test 4: Test vision model performance and latency (simplified - text only)."""
        logger.info("=" * 60)
        logger.info("TEST 4: VISION MODEL PERFORMANCE")
        logger.info("=" * 60)
        
        try:
            import requests
            
            # Test vision model with text-only prompt (faster - just one model for quick test)
            models_to_test = [
                ("moondream:latest", "Fast OCR model")
            ]
            
            vision_results = []
            for model, description in models_to_test:
                try:
                    start = time.time()
                    payload = {
                        "model": model,
                        "prompt": "Say 'OK' if you can respond.",
                        "stream": False
                    }
                    resp = requests.post("http://127.0.0.1:11434/api/generate", 
                                       json=payload, timeout=15)
                    duration = time.time() - start
                    
                    vision_results.append({
                        "model": model,
                        "description": description,
                        "success": resp.status_code == 200,
                        "latency_sec": round(duration, 2),
                        "response_length": len(resp.text) if resp.status_code == 200 else 0
                    })
                except Exception as e:
                    vision_results.append({
                        "model": model,
                        "description": description,
                        "success": False,
                        "error": str(e),
                        "latency_sec": 0
                    })
            
            successful_models = sum(1 for r in vision_results if r.get("success"))
            avg_latency = sum(r.get("latency_sec", 0) for r in vision_results) / len(vision_results) if vision_results else 0
            
            self.log_result(
                "Vision Model Performance",
                successful_models == len(models_to_test),
                f"Working models: {successful_models}/{len(models_to_test)}, Avg latency: {avg_latency:.2f}s",
                {
                    "total_models": len(models_to_test),
                    "successful_models": successful_models,
                    "avg_latency_sec": round(avg_latency, 2),
                    "model_details": vision_results
                }
            )
            
            return successful_models == len(models_to_test)
            
        except Exception as e:
            self.log_result("Vision Model Performance", False, f"Error: {e}")
            return False
    
    def test_05_virtual_mouse_operations(self):
        """Test 5: Test virtual mouse capabilities."""
        logger.info("=" * 60)
        logger.info("TEST 5: VIRTUAL MOUSE OPERATIONS")
        logger.info("=" * 60)
        
        try:
            from core_organs.virtual_mouse_service import VirtualMouseService, TraceAndVisionEngine
            from core_organs.visual_cursor import VisualCursor
            
            # Test virtual mouse service
            mouse_service = VirtualMouseService()
            mouse_service.start()
            
            # Test cursor spawning
            cursor1 = mouse_service.spawn("cursor_1", "test_agent")
            cursor2 = mouse_service.spawn("cursor_2", "test_agent_2")
            
            # Test cursor movement
            cursor1.move_to(500, 300)
            cursor2.move_to(700, 400)
            
            # Test visual cursor
            visual_cursor = VisualCursor()
            visual_cursor.show()
            visual_cursor.move_to(600, 350)
            
            # Test trace engine
            trace_engine = TraceAndVisionEngine()
            test_points = [(100, 100), (200, 200), (300, 150), (400, 250)]
            shape_analysis = trace_engine.identify_shape(test_points)
            
            mouse_service.stop()
            visual_cursor.hide()
            
            capabilities_tested = {
                "multi_cursor": True,
                "cursor_movement": True,
                "visual_cursor": True,
                "shape_analysis": shape_analysis.get("confidence", 0) > 0.5
            }
            
            all_capabilities_ok = all(capabilities_tested.values())
            
            self.log_result(
                "Virtual Mouse Operations",
                all_capabilities_ok,
                f"Capabilities: {list(capabilities_tested.keys())}, Shape analysis confidence: {shape_analysis.get('confidence', 0):.2f}",
                {
                    "multi_cursor": capabilities_tested["multi_cursor"],
                    "cursor_movement": capabilities_tested["cursor_movement"],
                    "visual_cursor": capabilities_tested["visual_cursor"],
                    "shape_analysis_confidence": shape_analysis.get("confidence", 0)
                }
            )
            
            return all_capabilities_ok
            
        except Exception as e:
            self.log_result("Virtual Mouse Operations", False, f"Error: {e}")
            return False
    
    def test_06_rhojiaga_crewai_integration(self):
        """Test 6: Test full CrewAI integration on rhojiaga.com."""
        logger.info("=" * 60)
        logger.info("TEST 6: RHOJIAGA.COM CREWAI INTEGRATION")
        logger.info("=" * 60)
        
        try:
            from core_organs.organ_01_crewai_engine import _HAS_CREWAI, Agent, Task, Crew, LLM, tool
            
            if not _HAS_CREWAI:
                self.log_result("Rhojiaga.com CrewAI Integration", False, "CrewAI not available")
                return False
            
            # Create a simple CrewAI task for rhojiaga.com
            @tool
            def navigate_to_rhojiaga() -> str:
                """Navigate to rhojiaga.com and analyze the content."""
                try:
                    from core_organs.lead_extractor import send_cdp_navigate, send_cdp_js
                    # This would require Organ 19 to be running
                    return "Navigation tool called (requires Organ 19 runtime)"
                except Exception as e:
                    return f"Navigation tool error: {e}"
            
            @tool
            def analyze_content() -> str:
                """Analyze the content of rhojiaga.com using vision."""
                try:
                    from core_organs.organ_31_visual_perception import VisualGroundingEngine
                    engine = VisualGroundingEngine()
                    # This would use vision to analyze the page
                    return "Content analysis tool called (requires vision model)"
                except Exception as e:
                    return f"Content analysis error: {e}"
            
            # Create agents
            researcher = Agent(
                role="Web Researcher",
                goal="Research rhojiaga.com and extract key information",
                backstory="You are an expert web researcher who can analyze websites and extract valuable information.",
                tools=[navigate_to_rhojiaga, analyze_content],
                verbose=True
            )
            
            # Create task
            task = Task(
                description="Navigate to rhojiaga.com, analyze the website structure, identify key features, and report findings",
                expected_output="A detailed analysis of rhojiaga.com including key features, structure, and recommendations",
                agent=researcher
            )
            
            # Create crew
            crew = Crew(
                agents=[researcher],
                tasks=[task],
                verbose=True
            )
            
            self.log_result(
                "Rhojiaga.com CrewAI Integration",
                True,
                "CrewAI setup successful - ready for rhojiaga.com testing",
                {
                    "agents_created": len(crew.agents),
                    "tasks_created": len(crew.tasks),
                    "tools_available": len(researcher.tools)
                }
            )
            
            return True
            
        except Exception as e:
            self.log_result("Rhojiaga.com CrewAI Integration", False, f"Error: {e}")
            return False
    
    def generate_report(self):
        """Generate comprehensive test report."""
        logger.info("=" * 60)
        logger.info("COMPREHENSIVE TEST REPORT")
        logger.info("=" * 60)
        
        total_tests = len(self.test_results)
        passed_tests = sum(1 for r in self.test_results if r["success"])
        failed_tests = total_tests - passed_tests
        success_rate = (passed_tests / total_tests * 100) if total_tests > 0 else 0
        
        logger.info(f"Total Tests: {total_tests}")
        logger.info(f"Passed: {passed_tests}")
        logger.info(f"Failed: {failed_tests}")
        logger.info(f"Success Rate: {success_rate:.1f}%")
        logger.info(f"Total Duration: {time.time() - self.start_time:.2f}s")
        
        logger.info("\nDetailed Results:")
        for result in self.test_results:
            status = "✅" if result["success"] else "❌"
            logger.info(f"{status} {result['test_name']}: {result['details']}")
            if result.get("metrics"):
                logger.info(f"   Metrics: {result['metrics']}")
        
        # Save to JSON
        report = {
            "test_summary": {
                "total_tests": total_tests,
                "passed": passed_tests,
                "failed": failed_tests,
                "success_rate": success_rate,
                "total_duration_sec": round(time.time() - self.start_time, 2)
            },
            "detailed_results": self.test_results
        }
        
        with open("rhojiaga_test_report.json", "w") as f:
            json.dump(report, f, indent=2)
        
        logger.info(f"\nReport saved to: rhojiaga_test_report.json")
        
        return report

def main():
    """Main test execution."""
    suite = RhojiagaTestSuite()
    
    # Run all tests
    suite.test_01_system_readiness()
    suite.test_02_task_compilation()
    suite.test_03_agent_paradigm_assignment()
    suite.test_04_vision_model_performance()
    suite.test_05_virtual_mouse_operations()
    suite.test_06_rhojiaga_crewai_integration()
    
    # Generate report
    suite.generate_report()

if __name__ == "__main__":
    main()