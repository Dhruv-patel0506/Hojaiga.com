#!/usr/bin/env python3
"""
Direct test of Ollama integration without WebSocket
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from ollama_tutor_integration import ask_local_tutor

print("=" * 60)
print("Direct Ollama Test")
print("=" * 60)

# Test with the user's topic
topic = "laws of thermodynamics"
print(f"\n[Topic] {topic}")
print("[Processing] Generating teaching content...")

result = ask_local_tutor(topic)

if result:
    print("\n" + "=" * 60)
    print("SUCCESS!")
    print("=" * 60)
    print(f"\nExplanation ({len(result['explanation'])} chars):")
    # Handle unicode encoding
    try:
        print(result['explanation'])
    except UnicodeEncodeError:
        print(result['explanation'].encode('utf-8', errors='replace').decode('cp1252'))
    print(f"\nDrawing Elements ({len(result['drawing_elements'])}):")
    for i, element in enumerate(result['drawing_elements'], 1):
        print(f"  {i}. {element}")
else:
    print("\n[ERROR] Failed to generate teaching")
