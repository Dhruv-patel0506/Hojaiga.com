#!/usr/bin/env python3
"""
Ollama Local Tutor Integration
Uses Llama 3.1/3.2 for offline, free teaching with structured JSON output
"""

import requests
import json

# Ollama local endpoint
OLLAMA_URL = "http://localhost:11434/api/generate"

def ask_local_tutor(student_question, model="llama3.1"):
    """
    Ask the local Ollama model for teaching content

    Args:
        student_question: The topic or question to teach
        model: Model to use (llama3.1 or llama3.2)

    Returns:
        Dictionary with explanation and drawing_elements
    """
    # System prompt enforcing strict JSON output with teaching methodology
    system_instruction = (
        "You are a professor teaching on a lightboard. Your student knows nothing about this topic. "
        "You must explain concepts deeply and provide visual diagrams. "
        "TEACHING METHODOLOGY:\n"
        "1. Start with a clear definition and explanation of what the topic is\n"
        "2. Explain WHY this concept matters and its real-world importance\n"
        "3. Break down the concept into key components or principles\n"
        "4. Show mathematical formulas or relationships step-by-step\n"
        "5. Provide concrete examples and applications\n"
        "6. Include derivations or proofs when appropriate\n"
        "7. Summarize key takeaways\n\n"
        "You must answer ONLY in a valid JSON object matching this structure:\n"
        "{\n"
        '  "explanation": "Your deep step-by-step teaching text here",\n'
        '  "drawing_elements": [\n'
        '     {"type": "text", "content": "Title text", "color": "white"},\n'
        '     {"type": "math", "content": "formula in LaTeX", "color": "yellow"},\n'
        '     {"type": "shape", "shape": "circle", "w": 80, "color": "cyan"},\n'
        '     {"type": "path", "svgPath": "M 0 0 L 100 50", "color": "green"}\n'
        "  ]\n"
        "}\n\n"
        "Available types: text, math, shape, path\n"
        "Available shapes: circle, rect, line, ellipse\n"
        "Available colors: white, cyan, magenta, green, yellow, orange\n"
        "For math: use LaTeX syntax like \\frac{{a}}{{b}}, \\theta, \\sum, \\int\n"
        "For svgPath: use SVG path syntax like M 0 0 L 100 50\n"
        "IMPORTANT: Generate 15-25 drawing elements for a complete lesson.\n"
        "Do NOT include x, y coordinates - the frontend will position them automatically."
    )

    payload = {
        "model": model,
        "prompt": f"{system_instruction}\n\nStudent Question: {student_question}",
        "format": "json",  # Forces Ollama to output clean JSON
        "stream": False,
        "options": {
            "temperature": 0.7,
            "top_p": 0.9,
            "num_predict": 4000  # Allow longer responses
        }
    }

    try:
        print(f"[Ollama] Sending request to {model}...")
        response = requests.post(OLLAMA_URL, json=payload, timeout=120)
        response.raise_for_status()

        result = response.json()
        response_text = result.get("response", "{}")

        print(f"[Ollama] Response length: {len(response_text)} chars")

        # Parse the JSON response
        tutor_data = json.loads(response_text)

        # Validate structure
        if "explanation" not in tutor_data or "drawing_elements" not in tutor_data:
            print(f"[Ollama] Invalid response structure")
            return None

        print(f"[Ollama] Generated {len(tutor_data['drawing_elements'])} drawing elements")
        return tutor_data

    except requests.exceptions.RequestException as e:
        print(f"[Ollama] Connection error: {e}")
        return None
    except json.JSONDecodeError as e:
        print(f"[Ollama] JSON decode error: {e}")
        return None
    except Exception as e:
        print(f"[Ollama] Unexpected error: {e}")
        return None


def test_ollama_connection():
    """Test if Ollama is running and accessible"""
    try:
        response = requests.get("http://localhost:11434/api/tags", timeout=5)
        response.raise_for_status()
        models = response.json().get("models", [])
        print(f"[Ollama] Connected! Available models:")
        for model in models:
            print(f"  - {model.get('name', 'unknown')}")
        return True
    except Exception as e:
        print(f"[Ollama] Not available: {e}")
        return False


if __name__ == "__main__":
    print("=" * 60)
    print("Ollama Local Tutor Integration Test")
    print("=" * 60)

    # Test connection
    if not test_ollama_connection():
        print("\n[ERROR] Ollama is not running. Start it with: ollama serve")
        exit(1)

    # Test teaching
    print("\n[Test] Asking about gravitational force...")
    result = ask_local_tutor("Explain gravitational force with a diagram")

    if result:
        print("\n[Success] Got teaching response!")
        print(f"\nExplanation (first 200 chars):")
        print(result["explanation"][:200] + "...")
        print(f"\nDrawing elements: {len(result['drawing_elements'])}")
        print("\nFull response:")
        print(json.dumps(result, indent=2))
    else:
        print("\n[ERROR] Failed to get teaching response")
