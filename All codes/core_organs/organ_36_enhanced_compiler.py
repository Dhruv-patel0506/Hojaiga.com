"""
HOJAIGA AUTOMATION ARCHITECTURE DOC

============================================================
1. MASTER ARCHITECTURE CONTEXT
============================================================
This component is part of the Hojaiga Automation Architecture.
Component Type: Organ 36 Enhancement
Name: Enhanced Task Compiler with Checkpoint Generation

============================================================
2. ORGAN/COMPONENT DIAGRAM
============================================================
```mermaid
graph TD
    classDef default fill:#1e1e1e,stroke:#333,stroke-width:2px,color:#d4d4d4;
    classDef component fill:#2d2d2d,stroke:#569cd6,stroke-width:2px,color:#d4d4d4;
    
    INPUT[User Command]
    
    INPUT --> INTENT[Intent Analysis]
    
    INTENT --> CHECKPOINT[Checkpoint Generator]
    
    CHECKPOINT --> SUBCHECKPOINT[Sub-Checkpoint Generator]
    
    SUBCHECKPOINT --> OBJECTIVE[Objective Builder]
    
    OBJECTIVE --> VALIDATOR[Dependency Validator]
    
    VALIDATOR --> OUTPUT[Enhanced Task Plan]
    
    class INTENT component
    class CHECKPOINT component
    class SUBCHECKPOINT component
    class OBJECTIVE component
    class VALIDATOR component
```

Inputs: User commands in any format
Outputs: Enhanced task plans with checkpoints, sub-checkpoints, and objectives
Dependencies: typing, dataclasses, enum, logging...
"""

from __future__ import annotations

import logging
import json
import re
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field
from enum import Enum
import requests

logger = logging.getLogger("hojaiga.organ36.enhanced_compiler")


class TaskPhase(str, Enum):
    """Types of task phases in the enhanced compiler."""
    PREPARATION = "preparation"
    EXECUTION = "execution"
    VERIFICATION = "verification"
    CLEANUP = "cleanup"


@dataclass
class TaskObjective:
    """Represents a specific objective within a checkpoint."""
    id: str
    description: str
    success_criteria: List[str]
    priority: int = 1
    estimated_duration_sec: int = 60
    dependencies: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "description": self.description,
            "success_criteria": self.success_criteria,
            "priority": self.priority,
            "estimated_duration_sec": self.estimated_duration_sec,
            "dependencies": self.dependencies
        }


@dataclass
class SubCheckpoint:
    """Represents a sub-checkpoint with detailed objectives."""
    id: str
    name: str
    description: str
    phase: TaskPhase
    objectives: List[TaskObjective]
    parent_checkpoint: str
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "phase": self.phase.value,
            "objectives": [obj.to_dict() for obj in self.objectives],
            "parent_checkpoint": self.parent_checkpoint
        }


@dataclass
class Checkpoint:
    """Represents a major checkpoint in the task execution."""
    id: str
    name: str
    description: str
    phase: TaskPhase
    sub_checkpoints: List[SubCheckpoint]
    estimated_duration_sec: int = 300
    dependencies: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "phase": self.phase.value,
            "sub_checkpoints": [sc.to_dict() for sc in self.sub_checkpoints],
            "estimated_duration_sec": self.estimated_duration_sec,
            "dependencies": self.dependencies
        }


@dataclass
class EnhancedTaskPlan:
    """Complete enhanced task plan with checkpoints and objectives."""
    task_id: str
    original_command: str
    intent: str
    checkpoints: List[Checkpoint]
    total_estimated_duration_sec: int
    required_capabilities: List[str]
    success_criteria: List[str]
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "original_command": self.original_command,
            "intent": self.intent,
            "checkpoints": [cp.to_dict() for cp in self.checkpoints],
            "total_estimated_duration_sec": self.total_estimated_duration_sec,
            "required_capabilities": self.required_capabilities,
            "success_criteria": self.success_criteria
        }


class EnhancedTaskCompiler:
    """
    Enhanced task compiler that generates detailed checkpoint-based task plans
    with objectives, sub-objectives, and success criteria using LLM.
    """
    
    def __init__(self, ollama_url: str = "http://127.0.0.1:11434/api/chat",
                 model: str = "llama3"):
        self.ollama_url = ollama_url
        self.model = model
        self.compilation_cache: Dict[str, EnhancedTaskPlan] = {}
    
    def compile_task(self, command: str, context: Optional[Dict[str, Any]] = None) -> EnhancedTaskPlan:
        """
        Compile a user command into an enhanced task plan with checkpoints.
        
        Args:
            command: Natural language task command
            context: Additional context (app names, constraints, etc.)
        
        Returns:
            EnhancedTaskPlan with detailed checkpoints and objectives
        """
        try:
            # Check cache
            cache_key = self._generate_cache_key(command, context)
            if cache_key in self.compilation_cache:
                logger.info(f"[Enhanced Compiler] Cache hit for command: '{command[:50]}...'")
                return self.compilation_cache[cache_key]
            
            # Step 1: Analyze intent
            intent = self._analyze_intent(command, context)
            
            # Step 2: Generate checkpoints
            checkpoints = self._generate_checkpoints(command, intent, context)
            
            # Step 3: Generate sub-checkpoints and objectives
            for checkpoint in checkpoints:
                checkpoint.sub_checkpoints = self._generate_sub_checkpoints(
                    command, intent, checkpoint, context
                )
            
            # Step 4: Calculate total duration
            total_duration = sum(cp.estimated_duration_sec for cp in checkpoints)
            
            # Step 5: Identify required capabilities
            capabilities = self._identify_capabilities(command, checkpoints)
            
            # Step 6: Define success criteria
            success_criteria = self._define_success_criteria(command, intent)
            
            # Create task plan
            task_plan = EnhancedTaskPlan(
                task_id=self._generate_task_id(),
                original_command=command,
                intent=intent,
                checkpoints=checkpoints,
                total_estimated_duration_sec=total_duration,
                required_capabilities=capabilities,
                success_criteria=success_criteria
            )
            
            # Cache result
            self.compilation_cache[cache_key] = task_plan
            
            logger.info(f"[Enhanced Compiler] Compiled task into {len(checkpoints)} checkpoints with "
                       f"{sum(len(cp.sub_checkpoints) for cp in checkpoints)} sub-checkpoints")
            
            return task_plan
            
        except Exception as e:
            logger.error(f"[Enhanced Compiler] Compilation failed: {e}")
            return self._fallback_compilation(command)
    
    def _analyze_intent(self, command: str, context: Optional[Dict[str, Any]]) -> str:
        """Use LLM to analyze the primary intent of the command."""
        try:
            context_str = ""
            if context:
                context_parts = []
                for key, value in context.items():
                    context_parts.append(f"{key}: {value}")
                context_str = "\nContext:\n" + "\n".join(context_parts)
            
            prompt = f"""Analyze the primary intent of this task command:

Command: {command}
{context_str}

Respond with a single sentence describing the primary intent (what the user wants to accomplish)."""
            
            payload = {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": "You are a precise task analyzer. Respond concisely."},
                    {"role": "user", "content": prompt}
                ],
                "stream": False,
                "options": {"temperature": 0.3}
            }
            
            response = requests.post(self.ollama_url, json=payload, timeout=30)
            response.raise_for_status()
            
            intent = response.json().get("message", {}).get("content", "")
            
            # Clean up the response
            intent = intent.strip().strip('"').strip("'")
            
            return intent if intent else "Execute task"
            
        except Exception as e:
            logger.error(f"[Enhanced Compiler] Intent analysis failed: {e}")
            return f"Execute: {command}"
    
    def _generate_checkpoints(self, command: str, intent: str, 
                             context: Optional[Dict[str, Any]]) -> List[Checkpoint]:
        """Use LLM to generate major checkpoints for the task."""
        try:
            prompt = f"""Break down this task into 3-5 major checkpoints:

Command: {command}
Intent: {intent}

Each checkpoint should represent a significant phase of the task.
Include:
- Preparation phase (setup, environment)
- Execution phase (main work)
- Verification phase (validation)
- Cleanup phase (cleanup)

Respond with JSON in this format:
{{
    "checkpoints": [
        {{
            "name": "checkpoint name",
            "description": "what happens in this checkpoint",
            "phase": "preparation|execution|verification|cleanup",
            "estimated_duration_sec": 60
        }}
    ]
}}

Respond ONLY with valid JSON."""
            
            payload = {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": "You are a task planner. Always respond with valid JSON."},
                    {"role": "user", "content": prompt}
                ],
                "stream": False,
                "options": {"temperature": 0.3}
            }
            
            response = requests.post(self.ollama_url, json=payload, timeout=30)
            response.raise_for_status()
            
            response_text = response.json().get("message", {}).get("content", "")
            
            # Parse JSON
            import re
            json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
            if not json_match:
                raise ValueError("No JSON found in LLM response")
            
            data = json.loads(json_match.group(0))
            checkpoints_data = data.get("checkpoints", [])
            
            checkpoints = []
            for i, cp_data in enumerate(checkpoints_data):
                phase_str = cp_data.get("phase", "execution").lower()
                try:
                    phase = TaskPhase(phase_str)
                except ValueError:
                    phase = TaskPhase.EXECUTION
                
                checkpoint = Checkpoint(
                    id=f"checkpoint_{i+1}",
                    name=cp_data.get("name", f"Checkpoint {i+1}"),
                    description=cp_data.get("description", ""),
                    phase=phase,
                    sub_checkpoints=[],
                    estimated_duration_sec=cp_data.get("estimated_duration_sec", 60)
                )
                checkpoints.append(checkpoint)
            
            return checkpoints
            
        except Exception as e:
            logger.error(f"[Enhanced Compiler] Checkpoint generation failed: {e}")
            return self._fallback_checkpoints(command)
    
    def _generate_sub_checkpoints(self, command: str, intent: str, 
                                  checkpoint: Checkpoint,
                                  context: Optional[Dict[str, Any]]) -> List[SubCheckpoint]:
        """Generate sub-checkpoints and objectives for a major checkpoint."""
        try:
            prompt = f"""Break down this checkpoint into 2-4 sub-checkpoints with specific objectives:

Checkpoint: {checkpoint.name}
Description: {checkpoint.description}
Phase: {checkpoint.phase.value}

Each sub-checkpoint should have:
- A specific action
- Clear success criteria
- Estimated duration

Respond with JSON in this format:
{{
    "sub_checkpoints": [
        {{
            "name": "sub-checkpoint name",
            "description": "what this does",
            "objectives": ["objective 1", "objective 2"],
            "estimated_duration_sec": 30
        }}
    ]
}}

Respond ONLY with valid JSON."""
            
            payload = {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": "You are a detailed task planner. Always respond with valid JSON."},
                    {"role": "user", "content": prompt}
                ],
                "stream": False,
                "options": {"temperature": 0.3}
            }
            
            response = requests.post(self.ollama_url, json=payload, timeout=30)
            response.raise_for_status()
            
            response_text = response.json().get("message", {}).get("content", "")
            
            # Parse JSON
            import re
            json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
            if not json_match:
                raise ValueError("No JSON found in LLM response")
            
            data = json.loads(json_match.group(0))
            sub_checkpoints_data = data.get("sub_checkpoints", [])
            
            sub_checkpoints = []
            for i, sc_data in enumerate(sub_checkpoints_data):
                # Create objectives
                objectives = []
                for j, obj_desc in enumerate(sc_data.get("objectives", [])):
                    objective = TaskObjective(
                        id=f"obj_{i+1}_{j+1}",
                        description=obj_desc,
                        success_criteria=[f"Complete: {obj_desc}"],
                        priority=1,
                        estimated_duration_sec=sc_data.get("estimated_duration_sec", 30) // len(sc_data.get("objectives", [1]))
                    )
                    objectives.append(objective)
                
                sub_checkpoint = SubCheckpoint(
                    id=f"sub_checkpoint_{checkpoint.id}_{i+1}",
                    name=sc_data.get("name", f"Sub-checkpoint {i+1}"),
                    description=sc_data.get("description", ""),
                    phase=checkpoint.phase,
                    objectives=objectives,
                    parent_checkpoint=checkpoint.id
                )
                sub_checkpoints.append(sub_checkpoint)
            
            return sub_checkpoints
            
        except Exception as e:
            logger.error(f"[Enhanced Compiler] Sub-checkpoint generation failed: {e}")
            return []
    
    def _identify_capabilities(self, command: str, checkpoints: List[Checkpoint]) -> List[str]:
        """Identify required capabilities based on command and checkpoints."""
        capabilities = []
        
        command_lower = command.lower()
        
        # Detect capabilities from command
        if any(k in command_lower for k in ["browser", "web", "chrome", "navigate", "url"]):
            capabilities.append("WEB_AUTOMATION")
        if any(k in command_lower for k in ["app", "desktop", "notepad", "calculator", "excel"]):
            capabilities.append("DESKTOP_AUTOMATION")
        if any(k in command_lower for k in ["scrape", "extract", "data", "leads"]):
            capabilities.append("DATA_EXTRACTION")
        if any(k in command_lower for k in ["vision", "see", "look", "screen"]):
            capabilities.append("VISION_PERCEPTION")
        if any(k in command_lower for k in ["mouse", "click", "draw"]):
            capabilities.append("VIRTUAL_MOUSE")
        
        # Add capabilities from checkpoints
        for checkpoint in checkpoints:
            if checkpoint.phase == TaskPhase.VERIFICATION:
                if "VERIFICATION" not in capabilities:
                    capabilities.append("VERIFICATION")
        
        return capabilities if capabilities else ["GENERAL_AUTOMATION"]
    
    def _define_success_criteria(self, command: str, intent: str) -> List[str]:
        """Define high-level success criteria for the task."""
        criteria = [
            f"Intent achieved: {intent}",
            "No errors or exceptions",
            "All checkpoints completed successfully"
        ]
        
        return criteria
    
    def _generate_cache_key(self, command: str, context: Optional[Dict[str, Any]]) -> str:
        """Generate a cache key for the command."""
        import hashlib
        key_str = command.lower()
        if context:
            key_str += json.dumps(context, sort_keys=True)
        return hashlib.md5(key_str.encode()).hexdigest()
    
    def _generate_task_id(self) -> str:
        """Generate a unique task ID."""
        import uuid
        return f"task_{uuid.uuid4().hex[:12]}"
    
    def _fallback_checkpoints(self, command: str) -> List[Checkpoint]:
        """Fallback checkpoint generation if LLM fails."""
        return [
            Checkpoint(
                id="checkpoint_1",
                name="Preparation",
                description="Prepare environment and resources",
                phase=TaskPhase.PREPARATION,
                sub_checkpoints=[],
                estimated_duration_sec=30
            ),
            Checkpoint(
                id="checkpoint_2",
                name="Execution",
                description=f"Execute: {command}",
                phase=TaskPhase.EXECUTION,
                sub_checkpoints=[],
                estimated_duration_sec=120
            ),
            Checkpoint(
                id="checkpoint_3",
                name="Verification",
                description="Verify task completion",
                phase=TaskPhase.VERIFICATION,
                sub_checkpoints=[],
                estimated_duration_sec=30
            )
        ]
    
    def _fallback_compilation(self, command: str) -> EnhancedTaskPlan:
        """Fallback compilation if full LLM pipeline fails."""
        checkpoints = self._fallback_checkpoints(command)
        
        return EnhancedTaskPlan(
            task_id=self._generate_task_id(),
            original_command=command,
            intent=f"Execute: {command}",
            checkpoints=checkpoints,
            total_estimated_duration_sec=sum(cp.estimated_duration_sec for cp in checkpoints),
            required_capabilities=["GENERAL_AUTOMATION"],
            success_criteria=["Task completed", "No errors"]
        )


# Singleton instance
_compiler_instance: Optional[EnhancedTaskCompiler] = None

def get_enhanced_compiler() -> EnhancedTaskCompiler:
    """Get the singleton enhanced compiler instance."""
    global _compiler_instance
    if _compiler_instance is None:
        _compiler_instance = EnhancedTaskCompiler()
    return _compiler_instance


def compile_enhanced_task(command: str, context: Optional[Dict[str, Any]] = None) -> EnhancedTaskPlan:
    """
    Convenience function to compile a task with enhanced checkpoint generation.
    
    Args:
        command: Natural language task command
        context: Optional additional context
    
    Returns:
        EnhancedTaskPlan with detailed checkpoints
    """
    compiler = get_enhanced_compiler()
    return compiler.compile_task(command, context)
