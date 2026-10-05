#!/usr/bin/env python3
"""
Infinite Void WebSocket Server with Ollama Crew System
Two-agent system: Professor (planner) + Draftsman (JSON generator)
"""

import asyncio
import websockets
import json
import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from ollama_crew_system import LightboardCrew

class CrewDrawingGenerator:
    """Two-agent system: Professor plans, Draftsman generates JSON"""

    def __init__(self, model="llama3.1"):
        self.crew = LightboardCrew(model=model)
        print(f"[Crew] Initialized with model: {model}")
        print(f"[Crew] Agent 1: Professor (lesson planning)")
        print(f"[Crew] Agent 2: Draftsman (JSON coordinates)")

    def generate_lesson_commands(self, topic: str) -> list:
        """Generate drawing commands using two-agent crew system"""
        print(f"[Crew] Generating lesson for: {topic}")

        # Run the crew session
        commands = self.crew.run_tutor_session(topic)

        if commands:
            # Add camera reset
            final_commands = [{"action": "move_camera", "x": 500, "y": 0}]
            final_commands.extend(commands)
            print(f"[Crew] Generated {len(final_commands)} commands")
            return final_commands
        else:
            print(f"[Crew] Failed to generate")
            return [
                {"action": "move_camera", "x": 500, "y": 0},
                {"type": "text", "content": "Error: Crew system failed", "color": "red"},
                {"type": "text", "content": "Please ensure Ollama is running", "color": "white"},
            ]

async def handle_websocket(websocket):
    """Handle WebSocket connection"""
    print("[Server] Client connected")

    generator = CrewDrawingGenerator(model="llama3.1")

    try:
        async for message in websocket:
            data = json.loads(message)
            print(f"[Server] Received: {data}")

            if data.get("type") == "start_lesson":
                topic = data.get("topic", "")
                print(f"[Server] Starting lesson: {topic}")

                # Generate commands
                commands = generator.generate_lesson_commands(topic)

                # Stream commands
                for command in commands:
                    await websocket.send(json.dumps(command))
                    await asyncio.sleep(0.5)  # Progressive drawing

                # Send completion
                await websocket.send(json.dumps({"type": "lesson_complete"}))
                print(f"[Server] Lesson complete")

    except websockets.exceptions.ConnectionClosed:
        print("[Server] Client disconnected")
    except Exception as e:
        print(f"[Server] Error: {e}")


async def main():
    """Start WebSocket server"""
    print("[Server] Starting Ollama Crew Infinite Void server...")
    print("[Server] Two-agent system: Professor (planner) + Draftsman (JSON)")
    print("[Server] Model: Llama 3.1 via Ollama")
    print("[Server] WebSocket on ws://localhost:8765")

    async with websockets.serve(handle_websocket, "localhost", 8765):
        print("[Server] Server running. Press Ctrl+C to stop.")
        await asyncio.Future()  # Run forever


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n[Server] Stopping server...")
