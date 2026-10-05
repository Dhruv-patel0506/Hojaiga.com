import httpx
import json
from pydantic import BaseModel, Field
from typing import List, Optional

# --- CORE ENDPOINT MAPPINGS ---
LOCAL_SERVER_URL = "http://127.0.0.1:8000"
OLLAMA_API_URL = "http://127.0.0"


# --- SYSTEM PROMPT DEFENSES ---
SYSTEM_PROMPT = """
You are a Universal Socratic AI Tutor running on an infinite void drawing canvas workspace.
Your primary directive is to guide students step-by-step through programming logic and algorithmic design.

CRITICAL EXECUTION RULES:
1. Never output massive text blocks. Express logical layouts using structured drawing commands.
2. If explaining code execution flow, emit visual element actions to draw structural blocks (e.g., shapes representing variables or arrays).
3. Do not give out complete solutions instantly. Provide Socratic hints unless explicitly forced.
4. When student scripts are executed via the local sandbox tool, parse the output text and draw annotations on screen to guide their correction.
"""


# --- CLIENT WRAPPERS ---
def query_local_llm(prompt: str, system: str = SYSTEM_PROMPT, model: str = "qwen2.5-coder:7b") -> dict:
    """
    Sends structural instructions to your local Ollama instance and returns JSON data.
    """
    # Enforce JSON structured output formatting directly on the model request profile
    payload = {
        "model": model,
        "prompt": prompt,
        "system": system,
        "format": "json",
        "stream": False,
        "options": {
            "temperature": 0.2  # Force strict logical precision
        }
    }
    
    try:
        with httpx.Client(timeout=30.0) as client:
            response = client.post(OLLAMA_API_URL, json=payload)
            if response.status_code == 200:
                raw_text = response.json().get("response", "{}")
                return json.loads(raw_text)
            else:
                return {"error": f"Ollama instance returned status code: {response.status_code}"}
    except Exception as e:
        return {"error": f"Failed to connect to local Ollama framework: {str(e)}"}


def execute_sandbox_code(code_string: str) -> dict:
    """
    Forwards code scripts directly into your active background FastAPI server docker sandbox.
    """
    payload = {"student_code": code_string}
    try:
        with httpx.Client(timeout=15.0) as client:
            response = client.post(f"{LOCAL_SERVER_URL}/run-code", json=payload)
            return response.json()
    except Exception as e:
        return {"error": f"Could not route request to active backend server: {str(e)}"}


# --- TEST FLOW DISPATCHER ---
if __name__ == "__main__":
    print("🚀 Initializing Socratic Agent Matrix Testing Suite...")
    
    # Mock Problem: A student submits broken python logic that loops indefinitely or crashes
    sample_student_submission = """
def find_even_numbers(numbers):
    for n in numbers:
        if n % 2 == 0:
            print(f"Found even element: " + n) # Intentionally crashes: Cannot concatenate str and int
            
find_even_numbers([1, 2, 3, 4])
"""
    
    print("\n--- Phase 1: Dispatching Broken Student Script to Secure Docker Container ---")
    sandbox_result = execute_sandbox_code(sample_student_submission)
    print(f"📦 Sandbox Return Status: {json.dumps(sandbox_result, indent=2)}")
    
    # Step 2: Feed the container errors straight back to the local model to draft an interactive tutoring flow
    print("\n--- Phase 2: Analyzing Execution Logs with Socratic Logic Engine ---")
    analysis_prompt = f"""
    The student is working on writing a list filtering script.
    Here is the exact code script they ran:
    {sample_student_submission}
    
    When we compiled it inside our secure sandbox, the runtime engine returned this trace:
    {json.dumps(sandbox_result)}
    
    Generate your tutor response. You must output your answer strictly inside this structured JSON schema format:
    {{
        "verbal_hint": "Your short socratic text guiding their fix line by line",
        "should_update_canvas": true,
        "canvas_drawing_commands": [
            {{ "shape": "rectangle", "x": 120, "y": 250, "annotation_label": "Error Location: Line 5 Type Mismatch" }},
            {{ "shape": "arrow", "x": 120, "y": 300, "annotation_label": "Flow Vector" }}
        ]
    }}
    """
    
    tutor_action = query_local_llm(analysis_prompt)
    print(f"\n💡 Intelligent Canvas Response Generated Matrix:\n{json.dumps(tutor_action, indent=2)}")
