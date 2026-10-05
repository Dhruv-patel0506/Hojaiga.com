"""
HOJAIGA AUTOMATION ARCHITECTURE DOC

============================================================
1. MASTER ARCHITECTURE CONTEXT
============================================================
This component is part of the Hojaiga Automation Architecture.
Component Type: Organ 38 Enhancement
Name: Progressive Refinement Loop

============================================================
2. ORGAN/COMPONENT DIAGRAM
============================================================
```mermaid
graph TD
    classDef default fill:#1e1e1e,stroke:#333,stroke-width:2px,color:#d4d4d4;
    classDef component fill:#2d2d2d,stroke:#569cd6,stroke-width:2px,color:#d4d4d4;
    
    INITIAL[Initial Plan]
    
    INITIAL --> EXECUTE[Execute Step]
    
    EXECUTE --> MONITOR[Monitor Results]
    
    MONITOR --> ANALYZE[Analyze Feedback]
    
    ANALYZE --> DECISION{Needs Refinement?}
    
    DECISION -->|Yes| REFINE[Refine Plan]
    
    DECISION -->|No| COMPLETE[Task Complete]
    
    REFINE --> EXECUTE
    
    class EXECUTE component
    class MONITOR component
    class ANALYZE component
    class REFINE component
```

Inputs: Initial task plan, execution results
Outputs: Refined task plans based on feedback
Dependencies: typing, dataclasses, enum, logging...
"""

from __future__ import annotations

import logging
import json
import time
from typing import Dict, Any, Optional, List, Callable
from dataclasses import dataclass, field
from enum import Enum
import requests

logger = logging.getLogger("hojaiga.organ38.progressive_refinement")


class RefinementTrigger(str, Enum):
    """Types of triggers for plan refinement."""
    EXECUTION_FAILURE = "execution_failure"
    PERFORMANCE_ISSUE = "performance_issue"
    OBSTACLE_DETECTED = "obstacle_detected"
    BETTER_ALTERNATIVE = "better_alternative"
    USER_FEEDBACK = "user_feedback"


@dataclass
class ExecutionFeedback:
    """Feedback from task execution that may trigger refinement."""
    step_id: str
    status: str
    error_message: Optional[str] = None
    execution_time_sec: float = 0.0
    unexpected_outcome: Optional[str] = None
    metrics: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "step_id": self.step_id,
            "status": self.status,
            "error_message": self.error_message,
            "execution_time_sec": self.execution_time_sec,
            "unexpected_outcome": self.unexpected_outcome,
            "metrics": self.metrics
        }


@dataclass
class RefinementAction:
    """Action to take when refining the plan."""
    trigger: RefinementTrigger
    description: str
    suggested_changes: List[str]
    new_step_ids: List[str] = field(default_factory=list)
    confidence: float = 0.5


class ProgressiveRefinementEngine:
    """
    Progressive refinement engine that monitors task execution and
    dynamically refines plans based on feedback and new information.
    """
    
    def __init__(self, ollama_url: str = "http://127.0.0.1:11434/api/chat",
                 model: str = "llama3"):
        self.ollama_url = ollama_url
        self.model = model
        self.refinement_history: List[Dict[str, Any]] = []
        self.max_refinements = 5
        
    def should_refine(self, feedback: ExecutionFeedback, current_plan: Dict[str, Any]) -> bool:
        """
        Determine if the plan should be refined based on execution feedback.
        
        Args:
            feedback: Execution feedback from a step
            current_plan: Current task plan
        
        Returns:
            True if refinement is needed, False otherwise
        """
        # Check for obvious failure
        if feedback.status == "failed":
            logger.info(f"[Refinement Engine] Step {feedback.step_id} failed, triggering refinement")
            return True
        
        # Check for performance issues
        if feedback.execution_time_sec > 300:  # 5 minutes
            logger.info(f"[Refinement Engine] Step {feedback.step_id} took too long ({feedback.execution_time_sec}s), triggering refinement")
            return True
        
        # Check for unexpected outcomes
        if feedback.unexpected_outcome:
            logger.info(f"[Refinement Engine] Unexpected outcome in step {feedback.step_id}: {feedback.unexpected_outcome}")
            return True
        
        return False
    
    def generate_refinement(self, feedback: ExecutionFeedback, current_plan: Dict[str, Any],
                          context: Optional[Dict[str, Any]] = None) -> RefinementAction:
        """
        Generate a refinement action using LLM analysis.
        
        Args:
            feedback: Execution feedback
            current_plan: Current task plan
            context: Additional context
        
        Returns:
            RefinementAction with suggested changes
        """
        try:
            # Check refinement limit
            refinement_count = len([r for r in self.refinement_history if r["task_id"] == current_plan.get("task_id", "")])
            if refinement_count >= self.max_refinements:
                logger.warning(f"[Refinement Engine] Max refinements ({self.max_refinements}) reached, stopping refinement")
                return RefinementAction(
                    trigger=RefinementTrigger.EXECUTION_FAILURE,
                    description="Maximum refinements reached",
                    suggested_changes=["Proceed with current plan despite issues"],
                    confidence=0.3
                )
            
            # Build LLM prompt for refinement analysis
            prompt = self._build_refinement_prompt(feedback, current_plan, context)
            
            # Query LLM
            response = self._query_llm(prompt)
            
            # Parse response
            refinement = self._parse_refinement_response(response)
            
            # Log to history
            self.refinement_history.append({
                "task_id": current_plan.get("task_id", ""),
                "feedback": feedback.to_dict(),
                "refinement": refinement.to_dict(),
                "timestamp": time.time()
            })
            
            logger.info(f"[Refinement Engine] Generated refinement: {refinement.description}")
            
            return refinement
            
        except Exception as e:
            logger.error(f"[Refinement Engine] Refinement generation failed: {e}")
            return self._fallback_refinement(feedback)
    
    def _build_refinement_prompt(self, feedback: ExecutionFeedback, current_plan: Dict[str, Any],
                              context: Optional[Dict[str, Any]]) -> str:
        """Build the LLM prompt for refinement analysis."""
        
        context_str = ""
        if context:
            context_parts = []
            for key, value in context.items():
                context_parts.append(f"{key}: {value}")
            context_str = "\nContext:\n" + "\n".join(context_parts)
        
        prompt = f"""Analyze this execution feedback and suggest how to refine the task plan:

Current Plan:
{json.dumps(current_plan, indent=2)}

Execution Feedback:
Step: {feedback.step_id}
Status: {feedback.status}
Error: {feedback.error_message or 'None'}
Execution Time: {feedback.execution_time_sec}s
Unexpected Outcome: {feedback.unexpected_outcome or 'None'}
Metrics: {json.dumps(feedback.metrics, indent=2)}
{context_str}

Determine:
1. What went wrong (if anything)
2. How to fix it
3. What changes to make to the plan

Respond with JSON in this format:
{{
    "trigger": "execution_failure|performance_issue|obstacle_detected|better_alternative",
    "description": "brief description of the refinement needed",
    "suggested_changes": ["change 1", "change 2"],
    "confidence": 0.0-1.0
}}

Respond ONLY with valid JSON."""
        
        return prompt
    
    def _query_llm(self, prompt: str) -> str:
        """Query the local LLM for refinement analysis."""
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": "You are a task refinement expert. Always respond with valid JSON."},
                {"role": "user", "content": prompt}
            ],
            "stream": False,
            "options": {"temperature": 0.3}
        }
        
        response = requests.post(self.ollama_url, json=payload, timeout=30)
        response.raise_for_status()
        
        return response.json().get("message", {}).get("content", "")
    
    def _parse_refinement_response(self, response: str) -> RefinementAction:
        """Parse the LLM response into a refinement action."""
        try:
            import re
            json_match = re.search(r'\{.*\}', response, re.DOTALL)
            if not json_match:
                raise ValueError("No JSON found in LLM response")
            
            data = json.loads(json_match.group(0))
            
            trigger_str = data.get("trigger", "execution_failure").lower()
            try:
                trigger = RefinementTrigger(trigger_str)
            except ValueError:
                trigger = RefinementTrigger.EXECUTION_FAILURE
            
            return RefinementAction(
                trigger=trigger,
                description=data.get("description", "Refinement needed"),
                suggested_changes=data.get("suggested_changes", []),
                confidence=float(data.get("confidence", 0.5))
            )
            
        except Exception as e:
            logger.error(f"[Refinement Engine] Failed to parse response: {e}")
            raise
    
    def _fallback_refinement(self, feedback: ExecutionFeedback) -> RefinementAction:
        """Fallback refinement if LLM fails."""
        if feedback.status == "failed":
            return RefinementAction(
                trigger=RefinementTrigger.EXECUTION_FAILURE,
                description=f"Step {feedback.step_id} failed, retry with alternative approach",
                suggested_changes=[
                    f"Retry step {feedback.step_id}",
                    "Add error handling",
                    "Increase timeout"
                ],
                confidence=0.6
            )
        else:
            return RefinementAction(
                trigger=RefinementTrigger.PERFORMANCE_ISSUE,
                description=f"Step {feedback.step_id} has performance issues",
                suggested_changes=[
                    "Optimize step execution",
                    "Reduce complexity"
                ],
                confidence=0.5
            )
    
    def apply_refinement(self, current_plan: Dict[str, Any], refinement: RefinementAction) -> Dict[str, Any]:
        """
        Apply a refinement action to the current plan.
        
        Args:
            current_plan: Current task plan
            refinement: Refinement action to apply
        
        Returns:
            Refined task plan
        """
        refined_plan = current_plan.copy()
        
        # Add refinement metadata
        refined_plan["refinements"] = refined_plan.get("refinements", [])
        refined_plan["refinements"].append({
            "trigger": refinement.trigger.value,
            "description": refinement.description,
            "suggested_changes": refinement.suggested_changes,
            "confidence": refinement.confidence,
            "timestamp": time.time()
        })
        
        # Apply suggested changes (simplified implementation)
        if "retry" in " ".join(refinement.suggested_changes).lower():
            # Mark failed step for retry
            if "steps" in refined_plan:
                for step in refined_plan["steps"]:
                    if refinement.new_step_ids and step.get("id") == refinement.new_step_ids[0]:
                        step["status"] = "pending"
                        step["retry_count"] = step.get("retry_count", 0) + 1
        
        logger.info(f"[Refinement Engine] Applied refinement to plan")
        
        return refined_plan


# Singleton instance
_refinement_engine_instance: Optional[ProgressiveRefinementEngine] = None

def get_refinement_engine() -> ProgressiveRefinementEngine:
    """Get the singleton refinement engine instance."""
    global _refinement_engine_instance
    if _refinement_engine_instance is None:
        _refinement_engine_instance = ProgressiveRefinementEngine()
    return _refinement_engine_instance


def check_and_refine(feedback: ExecutionFeedback, current_plan: Dict[str, Any],
                     context: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
    """
    Convenience function to check if refinement is needed and apply it.
    
    Args:
        feedback: Execution feedback
        current_plan: Current task plan
        context: Optional additional context
    
    Returns:
        Refined plan if refinement was applied, None otherwise
    """
    engine = get_refinement_engine()
    
    if engine.should_refine(feedback, current_plan):
        refinement = engine.generate_refinement(feedback, current_plan, context)
        refined_plan = engine.apply_refinement(current_plan, refinement)
        return refined_plan
    
    return None
