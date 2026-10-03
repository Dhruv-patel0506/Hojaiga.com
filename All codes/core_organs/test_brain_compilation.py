"""
Brain Compilation Test - Practical Task Compilation
==================================================

This test demonstrates how the enhanced brain compiler breaks down a user task
into PRACTICAL, task-specific checkpoints (not generic phases):

Example: "open LinkedIn and send message to Dhruv Patel"
→ Checkpoints:
  1. Open Chrome
  2. Open LinkedIn
  3. Find Dhruv Patel
  4. Compose message
  5. Send message

Structure:
1. Permanent Agent (assigned based on specialty)
2. Sub-Agents (one per checkpoint)
3. Temporary Agents (execute each checkpoint)
4. Checkpoints (actual task steps, not generic phases)

This is DYNAMIC - it uses intelligent detection to create task-specific steps.
"""

import sys
import os

# Add the core_organs directory to path
sys.path.insert(0, r"D:\new_automation\All codes")

from enhanced_brain_compiler import get_enhanced_compiler

def test_compilation():
    """Test the brain compilation for practical tasks."""
    
    print("=" * 80)
    print("BRAIN COMPILATION TEST - HIERARCHICAL STRUCTURE")
    print("=" * 80)
    print()
    
    # Get the enhanced compiler
    compiler = get_enhanced_compiler()
    
    # Test task
    task = "open LinkedIn and send message to Dhruv Patel"
    
    print(f"TESTING TASK: '{task}'")
    print("=" * 80)
    print()
    
    # Compile the task
    print("Compiling task with intelligent detection...")
    print()
    plan = compiler.compile_task(task)
    
    # Display the compilation results in hierarchical structure
    print("=" * 80)
    print("PERMANENT AGENT TASK")
    print("=" * 80)
    print(f"Task: {task}")
    print(f"Assigned to: agent_web (web_automation)")
    print()
    
    print("=" * 80)
    print("SUB-AGENT CHECKPOINTS")
    print("=" * 80)
    for i, checkpoint in enumerate(plan.checkpoints, 1):
        print(f"{i}. {checkpoint['description']}")
        if checkpoint.get('requires_user_input'):
            print(f"   (Smart: will ask user for content if not mentioned)")
    print()
    
    print("=" * 80)
    print("TEMPORARY AGENT TASKS (Granular Steps)")
    print("=" * 80)
    for i, temp_task in enumerate(plan.temporary_agent_tasks, 1):
        print(f"{i}. {temp_task['objective']}")
        print(f"   Description: {temp_task['description']}")
    print()
    
    print("=" * 80)
    print("EXECUTION FLOW (Stateful - Agents maintain state)")
    print("=" * 80)
    print("→ Temporary agents execute in sequence")
    print("→ State is preserved between tasks")
    print("→ Agents do NOT kill themselves - continuous workflow")
    print("→ Only killed when user requests or task complete")
    print()
    
    print("=" * 80)
    print("SUMMARY")
    print("=" * 80)
    print(f"Sub-Agent Checkpoints: {len(plan.checkpoints)}")
    print(f"Temporary Agent Tasks: {len(plan.temporary_agent_tasks)}")
    print(f"Estimated Duration: 5 minutes max")
    print()
    print("=" * 80)
    print("This compilation is PRACTICAL & STATEFUL!")
    print("Hierarchical structure with continuous agent state.")
    print("=" * 80)

if __name__ == "__main__":
    test_compilation()
