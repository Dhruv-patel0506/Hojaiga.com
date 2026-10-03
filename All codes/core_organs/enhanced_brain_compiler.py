"""
Enhanced Brain Compiler - Practical Task Compilation

Compiles tasks into practical, task-specific checkpoints:
- No generic phases (Understanding, Preparation, etc.)
- Actual task steps (e.g., "Open Chrome", "Open LinkedIn", "Find Dhruv", "Send message")
- Smart distribution to permanent agents based on paradigm
- Sub-agents handle each checkpoint
- Temporary agents execute the actual work
"""

import json
import logging
import re
import sys
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field, asdict
from datetime import datetime
import uuid

if r"D:\new_automation\All codes" not in sys.path:
    sys.path.insert(0, r"D:\new_automation\All codes")

try:
    from core_organs.agent_structure import (
        AgentTier,
        AgentParadigm,
        AgentSpecialty,
        PERMANENT_AGENTS
    )
except ImportError:
    from agent_structure import (
        AgentTier,
        AgentParadigm,
        AgentSpecialty,
        PERMANENT_AGENTS
    )

logger = logging.getLogger("hojaiga.enhanced_brain_compiler")


@dataclass
class CompiledPlan:
    """Compiled task plan with practical agent structure."""
    task_id: str
    original_request: str
    compiled_at: str
    human_intent: str
    primary_specialty: str
    assigned_permanent_agents: Dict[str, Dict[str, Any]]
    checkpoints: List[Dict[str, Any]]  # Actual task steps, not generic phases
    sub_agent_instructions: List[Dict[str, Any]]
    temporary_agent_tasks: List[Dict[str, Any]]
    execution_graph: Dict[str, Any]
    estimated_duration: str
    parallelism_level: str


class EnhancedBrainCompiler:
    """
    Practical brain compiler that creates task-specific checkpoints.
    
    Example:
    "open LinkedIn and send message to Dhruv Patel"
    → Checkpoints:
      1. Open Chrome
      2. Open LinkedIn
      3. Find Dhruv Patel
      4. Compose message
      5. Send message
    """
    
    def __init__(self):
        self.permanent_agents_status = {
            agent_id: {"idle": True, "current_task": None}
            for agent_id in PERMANENT_AGENTS.keys()
        }
    
    def compile_task(self, task_text: str, context: Optional[Dict[str, Any]] = None) -> CompiledPlan:
        """
        Compile a task into practical, task-specific checkpoints.
        
        Args:
            task_text: The user's task request
            context: Additional context
        
        Returns:
            CompiledPlan with practical checkpoints
        """
        task_id = str(uuid.uuid4())
        context = context or {}
        
        # Step 1: Extract human intent
        human_intent = self._extract_human_intent(task_text)
        
        # Step 2: Detect specialty
        specialty = self._detect_specialty(task_text)
        primary_specialty = specialty
        
        # Step 3: Assign to permanent agent
        assigned_agent = self._assign_permanent_agent(specialty)
        
        # Step 4: Generate practical checkpoints (TASK-SPECIFIC, not generic)
        checkpoints = self._generate_practical_checkpoints(task_text, specialty)
        
        # Step 5: Create sub-agent instructions for each checkpoint
        sub_agent_instructions = self._create_sub_agent_instructions(checkpoints, assigned_agent)
        
        # Step 6: Create temporary agent tasks
        temporary_agent_tasks = self._create_temporary_agent_tasks(checkpoints)
        
        # Step 7: Build execution graph
        execution_graph = self._build_execution_graph(checkpoints)
        
        # Step 8: Estimate parallelism and duration
        parallelism_level = self._estimate_parallelism(checkpoints)
        estimated_duration = self._estimate_duration(checkpoints)
        
        compiled_plan = CompiledPlan(
            task_id=task_id,
            original_request=task_text,
            compiled_at=datetime.now().isoformat(),
            human_intent=human_intent,
            primary_specialty=primary_specialty,
            assigned_permanent_agents={
                assigned_agent: {
                    "tier": "permanent",
                    "paradigm": specialty,
                    "is_idle": False,
                    "current_task": task_id
                }
            },
            checkpoints=checkpoints,
            sub_agent_instructions=sub_agent_instructions,
            temporary_agent_tasks=temporary_agent_tasks,
            execution_graph=execution_graph,
            estimated_duration=estimated_duration,
            parallelism_level=parallelism_level
        )
        
        logger.info(f"[EnhancedCompiler] Compiled task '{task_text[:50]}...'")
        logger.info(f"  - Human intent: {human_intent}")
        logger.info(f"  - Specialty: {primary_specialty}")
        logger.info(f"  - Assigned agent: {assigned_agent}")
        logger.info(f"  - Practical checkpoints: {len(checkpoints)}")
        logger.info(f"  - Sub-agents: {len(sub_agent_instructions)}")
        logger.info(f"  - Temporary tasks: {len(temporary_agent_tasks)}")
        
        return compiled_plan
    
    def _extract_human_intent(self, task_text: str) -> str:
        """Extract the human intent from the task."""
        # Simplified - in production would use LLM
        task_lower = task_text.lower()
        
        if "open" in task_lower and "send" in task_lower:
            return "access platform and transmit message"
        elif "open" in task_lower:
            return "access and view"
        elif "send" in task_lower:
            return "transmit message"
        elif "delete" in task_lower or "remove" in task_lower:
            return "remove unwanted items"
        elif "find" in task_lower or "search" in task_lower:
            return "locate information"
        else:
            return "perform the requested task"
    
    def _detect_specialty(self, task_text: str) -> str:
        """Detect the specialty based on task content.

        Dynamic, data-driven routing: instead of checking one bucket first (the
        old bug -- a generic action verb like "open" sat in the web list, so
        "open excel" short-circuited to web_automation), we SCORE how many
        concrete signal keywords each specialty matches and take the strongest.
        Only *specific* signals (platform / app / data nouns) are listed -- the
        bare verb "open" is intentionally omitted because it is an action, not a
        destination. Ties are broken by a fixed, non-app-specific priority
        (desktop > data > web) so "open excel" resolves to the app launcher.
        """
        task_lower = task_text.lower()

        # Concrete web-destination signals (NO generic "open" action verb).
        web_keywords = ["gmail", "linkedin", "facebook", "twitter", "chrome",
                        "browser", "website", "web site", "url", "http", "www",
                        "send message", "webmail", "online", "web page", "browse"]

        # Desktop application / file-system signals.
        desktop_keywords = ["notepad", "excel", "word", "calculator", "file",
                            "folder", "directory", "paint", "obs", "vlc",
                            "photoshop", "terminal", "command prompt", "explorer",
                            "task manager", "screenshot", "snipping",
                            "blender", "3d", "maya", "cad", "gimp"]

        # Data-analysis / processing signals.
        data_keywords = ["analyze", "analyse", "process", "data", "spreadsheet",
                         "statistics", "dataset", "pivot", "aggregate", "compute",
                         "calculate", "sum", "average", "chart"]

        categories = {
            "web_automation": web_keywords,
            "desktop_automation": desktop_keywords,
            "data_processing": data_keywords,
        }
        # Deterministic tie-break priority (highest first) when scores match.
        priority = ["desktop_automation", "data_processing", "web_automation"]

        scores = {cat: sum(1 for kw in kws if kw in task_lower)
                  for cat, kws in categories.items()}
        best_score = max(scores.values())
        if best_score == 0:
            return "web_automation"  # Default -- no concrete desktop/data signal
        for cat in priority:
            if scores[cat] == best_score:
                return cat
        return "web_automation"
    
    def _assign_permanent_agent(self, specialty: str) -> str:
        """Assign task to appropriate permanent agent."""
        agent_mapping = {
            "web_automation": "agent_web",
            "desktop_automation": "agent_desktop",
            "data_processing": "agent_data",
            "research": "agent_research",
            "communication": "agent_comm",
            "content": "agent_content",
            "system": "agent_system"
        }
        return agent_mapping.get(specialty, "agent_web")
    
    def _generate_practical_checkpoints(self, task_text: str, specialty: str) -> List[Dict[str, Any]]:
        """
        Generate practical, task-specific checkpoints.
        
        This is the KEY - no generic phases, actual task steps.
        """
        task_lower = task_text.lower()
        checkpoints = []
        
        if specialty == "web_automation":
            # Web automation checkpoints
            if "linkedin" in task_lower and "send message" in task_lower:
                # LinkedIn message sending flow
                checkpoints.append({
                    "checkpoint_id": "cp_1_open_chrome",
                    "description": "Open Chrome browser",
                    "objective": "Launch Chrome browser",
                    "capabilities": ["launch_app"],
                    "assigned_agent": "agent_web",
                    "requires_user_input": False
                })
                checkpoints.append({
                    "checkpoint_id": "cp_2_navigate_linkedin",
                    "description": "Search LinkedIn and find recipient",
                    "objective": "Navigate to LinkedIn and locate the recipient",
                    "capabilities": ["navigate", "search", "click"],
                    "assigned_agent": "agent_web",
                    "requires_user_input": False
                })
                checkpoints.append({
                    "checkpoint_id": "cp_3_compose_message",
                    "description": "Compose message based on context",
                    "objective": "Write message content (ask user if not provided)",
                    "capabilities": ["type", "edit", "ask_user"],
                    "assigned_agent": "agent_web",
                    "requires_user_input": True  # Smart: ask user if content not mentioned
                })
                checkpoints.append({
                    "checkpoint_id": "cp_4_smart_content_generation",
                    "description": "Generate message body if needed",
                    "objective": "Use AI to generate/fill custom message fields",
                    "capabilities": ["navigate_new_tab", "search_ai", "copy_text"],
                    "assigned_agent": "agent_web",
                    "requires_user_input": False
                })
                checkpoints.append({
                    "checkpoint_id": "cp_5_send_message",
                    "description": "Paste message and send",
                    "objective": "Paste message, verify, and click send",
                    "capabilities": ["paste", "verify", "click"],
                    "assigned_agent": "agent_web",
                    "requires_user_input": False
                })
            
            elif "gmail" in task_lower:
                # Gmail flow
                checkpoints.append({
                    "checkpoint_id": "cp_1_open_chrome",
                    "description": "Open Chrome browser",
                    "objective": "Launch Chrome browser",
                    "capabilities": ["launch_app"],
                    "assigned_agent": "agent_web",
                    "requires_user_input": False
                })
                checkpoints.append({
                    "checkpoint_id": "cp_2_navigate_gmail",
                    "description": "Navigate to Gmail",
                    "objective": "Open Gmail website",
                    "capabilities": ["navigate", "type_url"],
                    "assigned_agent": "agent_web",
                    "requires_user_input": False
                })
        
        elif specialty == "desktop_automation":
            try:
                from core_organs.task_graph_compiler import compile_user_task
                graph = compile_user_task(task_text)
                for i, step in enumerate(graph.steps or []):
                    checkpoints.append({
                        "checkpoint_id": f"cp_{i+1}_{re.sub(r'[^a-z0-9]+', '_', step.goal.lower())[:28].strip('_')}",
                        "description": step.goal,
                        "objective": step.goal,
                        "capabilities": ["launch_app", "verify"] if step.kind in ("native", "verify", "launch")
                                        else ["click", "type", "verify"],
                        "assigned_agent": "agent_desktop",
                        "requires_user_input": False,
                    })
            except Exception:
                checkpoints = []
            if not checkpoints:
                checkpoints.append({
                    "checkpoint_id": "cp_1_open_desktop_app",
                    "description": "Open the requested desktop application",
                    "objective": "Launch the application named in the task",
                    "capabilities": ["launch_app"],
                    "assigned_agent": "agent_desktop",
                    "requires_user_input": False
                })
        
        # If no specific checkpoints, create generic ones
        if not checkpoints:
            checkpoints.append({
                "checkpoint_id": "cp_1_launch_app",
                "description": "Launch required application",
                "objective": "Open the application needed for the task",
                "capabilities": ["launch_app"],
                "assigned_agent": "agent_web",
                "requires_user_input": False
            })
            checkpoints.append({
                "checkpoint_id": "cp_2_perform_action",
                "description": "Perform main action",
                "objective": "Execute the main task action",
                "capabilities": ["click", "type"],
                "assigned_agent": "agent_web",
                "requires_user_input": False
            })
        
        return checkpoints
    
    def _create_sub_agent_instructions(self, checkpoints: List[Dict[str, Any]], 
                                       assigned_agent: str) -> List[Dict[str, Any]]:
        """Create sub-agent instructions for each checkpoint."""
        sub_agent_instructions = []
        
        for i, checkpoint in enumerate(checkpoints):
            sub_agent_id = f"sub_{assigned_agent}_{i}"
            
            instruction = {
                "sub_agent_id": sub_agent_id,
                "tier": "sub",
                "parent_agent_id": assigned_agent,
                "checkpoint_id": checkpoint["checkpoint_id"],
                "objective": checkpoint["objective"],
                "description": checkpoint["description"],
                "required_capabilities": checkpoint["capabilities"],
                "assigned_to_temporary": False
            }
            
            sub_agent_instructions.append(instruction)
        
        return sub_agent_instructions
    
    def _create_temporary_agent_tasks(self, checkpoints: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Create temporary agent tasks for actual execution.
        
        Breaks down each checkpoint into granular steps.
        """
        temporary_agent_tasks = []
        task_counter = 0
        
        for checkpoint in checkpoints:
            checkpoint_id = checkpoint["checkpoint_id"]
            description = checkpoint["description"]
            
            # Break down checkpoint into granular temporary tasks
            if "open chrome" in description.lower():
                temporary_agent_tasks.append({
                    "temp_agent_id": f"temp_{task_counter}",
                    "tier": "temporary",
                    "checkpoint_id": checkpoint_id,
                    "objective": "Open Chrome browser",
                    "description": "Launch Chrome application",
                    "no_overlap": True,
                    "status": "pending"
                })
                task_counter += 1
            
            elif "search linkedin" in description.lower() or "navigate to linkedin" in description.lower():
                temporary_agent_tasks.append({
                    "temp_agent_id": f"temp_{task_counter}",
                    "tier": "temporary",
                    "checkpoint_id": checkpoint_id,
                    "objective": "Type linkedin.com in address bar",
                    "description": "Navigate to LinkedIn",
                    "no_overlap": True,
                    "status": "pending"
                })
                task_counter += 1
                temporary_agent_tasks.append({
                    "temp_agent_id": f"temp_{task_counter}",
                    "tier": "temporary",
                    "checkpoint_id": checkpoint_id,
                    "objective": "Search for recipient name",
                    "description": "Type recipient name in search bar",
                    "no_overlap": True,
                    "status": "pending"
                })
                task_counter += 1
                temporary_agent_tasks.append({
                    "temp_agent_id": f"temp_{task_counter}",
                    "tier": "temporary",
                    "checkpoint_id": checkpoint_id,
                    "objective": "Click on recipient profile",
                    "description": "Select the recipient from search results",
                    "no_overlap": True,
                    "status": "pending"
                })
                task_counter += 1
                temporary_agent_tasks.append({
                    "temp_agent_id": f"temp_{task_counter}",
                    "tier": "temporary",
                    "checkpoint_id": checkpoint_id,
                    "objective": "Click send message button",
                    "description": "Open message compose window",
                    "no_overlap": True,
                    "status": "pending"
                })
                task_counter += 1
            
            elif "compose message" in description.lower():
                temporary_agent_tasks.append({
                    "temp_agent_id": f"temp_{task_counter}",
                    "tier": "temporary",
                    "checkpoint_id": checkpoint_id,
                    "objective": "Ask user for message content if not provided",
                    "description": "Smart: prompt user for message if missing",
                    "no_overlap": True,
                    "status": "pending"
                })
                task_counter += 1
            
            elif "generate message body" in description.lower():
                temporary_agent_tasks.append({
                    "temp_agent_id": f"temp_{task_counter}",
                    "tier": "temporary",
                    "checkpoint_id": checkpoint_id,
                    "objective": "Open new tab",
                    "description": "Open new browser tab for AI",
                    "no_overlap": True,
                    "status": "pending"
                })
                task_counter += 1
                temporary_agent_tasks.append({
                    "temp_agent_id": f"temp_{task_counter}",
                    "tier": "temporary",
                    "checkpoint_id": checkpoint_id,
                    "objective": "Navigate to AI (ChatGPT/Claude)",
                    "description": "Open AI assistant for message generation",
                    "no_overlap": True,
                    "status": "pending"
                })
                task_counter += 1
                temporary_agent_tasks.append({
                    "temp_agent_id": f"temp_{task_counter}",
                    "tier": "temporary",
                    "checkpoint_id": checkpoint_id,
                    "objective": "Generate message with custom prompt",
                    "description": "Use AI to create message body",
                    "no_overlap": True,
                    "status": "pending"
                })
                task_counter += 1
                temporary_agent_tasks.append({
                    "temp_agent_id": f"temp_{task_counter}",
                    "tier": "temporary",
                    "checkpoint_id": checkpoint_id,
                    "objective": "Copy generated message",
                    "description": "Copy message to clipboard",
                    "no_overlap": True,
                    "status": "pending"
                })
                task_counter += 1
            
            elif "paste message and send" in description.lower():
                temporary_agent_tasks.append({
                    "temp_agent_id": f"temp_{task_counter}",
                    "tier": "temporary",
                    "checkpoint_id": checkpoint_id,
                    "objective": "Switch back to LinkedIn tab",
                    "description": "Return to LinkedIn message window",
                    "no_overlap": True,
                    "status": "pending"
                })
                task_counter += 1
                temporary_agent_tasks.append({
                    "temp_agent_id": f"temp_{task_counter}",
                    "tier": "temporary",
                    "checkpoint_id": checkpoint_id,
                    "objective": "Paste message into message body",
                    "description": "Paste message content",
                    "no_overlap": True,
                    "status": "pending"
                })
                task_counter += 1
                temporary_agent_tasks.append({
                    "temp_agent_id": f"temp_{task_counter}",
                    "tier": "temporary",
                    "checkpoint_id": checkpoint_id,
                    "objective": "Verify message content",
                    "description": "Check message for custom field placeholders",
                    "no_overlap": True,
                    "status": "pending"
                })
                task_counter += 1
                temporary_agent_tasks.append({
                    "temp_agent_id": f"temp_{task_counter}",
                    "tier": "temporary",
                    "checkpoint_id": checkpoint_id,
                    "objective": "Fill any custom fields",
                    "description": "Smart: fill in missing custom fields",
                    "no_overlap": True,
                    "status": "pending"
                })
                task_counter += 1
                temporary_agent_tasks.append({
                    "temp_agent_id": f"temp_{task_counter}",
                    "tier": "temporary",
                    "checkpoint_id": checkpoint_id,
                    "objective": "Click send button",
                    "description": "Transmit the message",
                    "no_overlap": True,
                    "status": "pending"
                })
                task_counter += 1
            
            else:
                # Generic task
                temporary_agent_tasks.append({
                    "temp_agent_id": f"temp_{task_counter}",
                    "tier": "temporary",
                    "checkpoint_id": checkpoint_id,
                    "objective": checkpoint["objective"],
                    "description": checkpoint["description"],
                    "no_overlap": True,
                    "status": "pending"
                })
                task_counter += 1
        
        return temporary_agent_tasks
    
    def _build_execution_graph(self, checkpoints: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Build execution graph showing sequential dependencies."""
        graph = {
            "nodes": [cp["checkpoint_id"] for cp in checkpoints],
            "dependencies": []
        }
        
        # Sequential dependencies
        for i in range(len(checkpoints) - 1):
            graph["dependencies"].append({
                "from": checkpoints[i]["checkpoint_id"],
                "to": checkpoints[i+1]["checkpoint_id"],
                "type": "sequential"
            })
        
        return graph
    
    def _estimate_parallelism(self, checkpoints: List[Dict[str, Any]]) -> str:
        """Estimate parallelism level."""
        return "sequential"  # Most tasks are sequential
    
    def _estimate_duration(self, checkpoints: List[Dict[str, Any]]) -> str:
        """Estimate duration based on checkpoints."""
        minutes = len(checkpoints) * 2  # Rough estimate: 2 minutes per checkpoint
        return f"{minutes}-{minutes+5} minutes"


# Singleton instance
_compiler_instance = None

def get_enhanced_compiler() -> EnhancedBrainCompiler:
    """Get the singleton enhanced compiler instance."""
    global _compiler_instance
    if _compiler_instance is None:
        _compiler_instance = EnhancedBrainCompiler()
    return _compiler_instance
