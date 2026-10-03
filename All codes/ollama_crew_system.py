#!/usr/bin/env python3
"""
Ollama-Powered Lightboard Crew System
Two-agent system: Professor (planner) + Draftsman (JSON generator)
Uses Llama 3.1 via Ollama for both agents
"""

import requests
import json
import sys
import os

# Ollama endpoint
OLLAMA_URL = "http://localhost:11434/api/generate"


class OllamaProfessor:
    """Agent 1: The Professor - Plans the lesson and visual layout"""

    def __init__(self, model="llama3.1"):
        self.model = model

    def plan_lesson(self, topic: str) -> str:
        """
        Generate a detailed lesson plan with visual blueprint

        Returns:
            Detailed script and visual blueprint
        """
        prompt = f"""You are a world-renowned professor teaching on a lightboard. You are explaining the topic: "{topic}"

IMPORTANT: Do NOT output JSON yet. First, think deeply about the visual representation.

TEACHING METHODOLOGY:
1. Write the script of what you will say (using LaTeX for math)
2. Design the diagram meticulously in your mind
3. For physics topics: Design complex scenes (e.g., Free Body Diagram with incline, friction, gravity vectors)
4. For math topics: Design precise graphs with axes, labels, key points
5. For biology topics: Design meaningful diagrams (not generic circles)
6. Provide precise spatial instructions for drawing

VISUAL DESIGN RULES:
- NEVER draw a simple circle for a complex topic
- Use meaningful visual metaphors (blocks, inclines, pulleys, etc.)
- Include labels, annotations, and coordinate references
- Design the layout (where each element should go)
- Specify colors for different elements (forces, labels, etc.)

SPATIAL INSTRUCTIONS EXAMPLE:
"Place the block in the center (x=500, y=300)"
"Draw an arrow pointing straight down for gravity (from x=500 to x=500, y=300 to y=400)"
"Label the mass 'm' in cyan color"
"Draw the incline line from (x=200, y=400) to (x=800, y=200)"

Your output should be:
1. Detailed teaching script with formulas
2. Meticulous visual blueprint describing exact shapes, positions, and colors
3. Step-by-step spatial instructions for the Draftsman

Write your complete lesson plan and visual blueprint:"""

        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": 0.7,
                "num_predict": 4000
            }
        }

        try:
            response = requests.post(OLLAMA_URL, json=payload, timeout=120)
            result = response.json()
            plan = result.get("response", "")
            print(f"[Professor] Generated plan: {len(plan)} chars")
            return plan
        except Exception as e:
            print(f"[Professor] Error: {e}")
            return None


class OllamaDraftsman:
    """Agent 2: The Draftsman - Converts plan to JSON coordinates"""

    def __init__(self, model="llama3.1"):
        self.model = model

    def generate_json_commands(self, plan: str) -> list:
        """
        Convert the visual blueprint into JSON drawing commands

        Args:
            plan: The Professor's lesson plan and visual blueprint

        Returns:
            List of JSON drawing commands
        """
        prompt = f"""You are a master draftsman. Your job is to convert the Professor's visual plan into strictly valid JSON drawing commands.

THE PROFESSOR'S PLAN:
{plan}

YOUR TASK:
Calculate the X and Y coordinates (assume a 1920x1080 canvas with scrolling).
Output the final result as a STRICTLY VALID JSON array of objects.

AVAILABLE COMMANDS:
- text: {{"type": "text", "content": "string", "color": "white|cyan|magenta|green|yellow|orange"}}
- math: {{"type": "math", "content": "LaTeX string", "color": "yellow"}}
- shape: {{"type": "shape", "shape": "circle|rect|line|ellipse", "w": int, "h": int, "color": "string"}}
- path: {{"type": "path", "svgPath": "M x y L x y...", "color": "string"}}

COORDINATE GUIDELINES:
- Start at x=50, y=50
- Vertical spacing: 60px for text/math, 100px for shapes
- Horizontal spacing: 200px between elements
- Use progressive y positioning to avoid overlap

IMPORTANT:
- Output ONLY the JSON array
- No markdown, no conversational text
- Make the JSON strictly valid
- Include 15-25 commands for a complete lesson

Generate the JSON array:"""

        payload = {
            "model": self.model,
            "prompt": prompt,
            "format": "json",  # Force JSON output
            "stream": False,
            "options": {
                "temperature": 0.5,  # Lower temperature for precise coordinates
                "num_predict": 3000
            }
        }

        try:
            response = requests.post(OLLAMA_URL, json=payload, timeout=120)
            result = response.json()
            response_text = result.get("response", "{}")

            # Parse JSON
            commands = json.loads(response_text)

            # Handle nested structure (LLaVA sometimes wraps in a dict)
            if isinstance(commands, dict):
                if "commands" in commands:
                    commands = commands["commands"]
                elif "drawing_elements" in commands:
                    commands = commands["drawing_elements"]
                else:
                    commands = [commands]

            # Ensure it's a list
            if not isinstance(commands, list):
                commands = [commands]

            print(f"[Draftsman] Generated {len(commands)} commands")
            return commands
        except Exception as e:
            print(f"[Draftsman] Error: {e}")
            return None


class LightboardCrew:
    """Two-agent system: Professor plans, Draftsman draws"""

    def __init__(self, model="llama3.1"):
        self.professor = OllamaProfessor(model)
        self.draftsman = OllamaDraftsman(model)

    def run_tutor_session(self, topic: str) -> list:
        """
        Run the complete two-agent tutoring session

        Args:
            topic: The topic to teach

        Returns:
            List of JSON drawing commands
        """
        print(f"[Crew] Starting tutoring session for: {topic}")
        print(f"[Crew] Agent 1: Professor (planning)")
        print(f"[Crew] Agent 2: Draftsman (JSON generation)")

        # Step 1: Professor plans the lesson
        print("\n[Step 1] Professor generating lesson plan...")
        plan = self.professor.plan_lesson(topic)

        if not plan:
            print("[Crew] Professor failed, aborting")
            return None

        print(f"[Crew] Professor plan complete")

        # Step 2: Draftsman converts to JSON
        print("\n[Step 2] Draftsman generating JSON commands...")
        commands = self.draftsman.generate_json_commands(plan)

        if not commands:
            print("[Crew] Draftsman failed, aborting")
            return None

        print(f"[Crew] Draftsman complete: {len(commands)} commands")
        print(f"[Crew] Session complete!")

        return commands


if __name__ == "__main__":
    print("=" * 60)
    print("Ollama Lightboard Crew System")
    print("=" * 60)

    crew = LightboardCrew(model="llama3.1")

    # Test with a physics topic
    topic = "Newton's Second Law using a Free Body Diagram"
    print(f"\n[Test] Running session for: {topic}\n")

    commands = crew.run_tutor_session(topic)

    if commands:
        print("\n" + "=" * 60)
        print("SUCCESS!")
        print("=" * 60)
        print(f"\nGenerated {len(commands)} commands:")
        for i, cmd in enumerate(commands, 1):
            print(f"  {i}. {cmd}")
    else:
        print("\n[ERROR] Session failed")
