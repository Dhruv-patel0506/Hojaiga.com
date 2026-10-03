"""
Agent Structure Definition for Hojaiga Multi-Agent Swarm

Defines the 7 permanent agents, their paradigms, and specialties.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Dict, Optional


class AgentTier(str, Enum):
    """Agent tier classification."""
    PERMANENT = "permanent"  # Always active, 7 total
    SUB = "sub"  # Created by permanent agents for categories
    TEMPORARY = "temporary"  # Workers that perform actual tasks


class AgentParadigm(str, Enum):
    """The 7 paradigms for permanent agents."""
    WEB_AUTOMATION = "web_automation"
    DESKTOP_AUTOMATION = "desktop_automation"
    DATA_PROCESSING = "data_processing"
    RESEARCH_AND_ANALYSIS = "research_and_analysis"
    COMMUNICATION = "communication"
    CONTENT_CREATION = "content_creation"
    SYSTEM_MANAGEMENT = "system_management"


@dataclass
class AgentSpecialty:
    """Specialty definition for an agent."""
    paradigm: AgentParadigm
    keywords: List[str]
    capabilities: List[str]
    description: str


@dataclass
class AgentCheckpoint:
    """Checkpoint for task execution."""
    checkpoint_id: str
    phase: str
    description: str
    required_capabilities: List[str]
    parent_agent_id: str
    sub_agents_required: int = 0
    temporary_agents_required: int = 0


@dataclass
class AgentSpec:
    """Specification for an agent."""
    agent_id: str
    tier: AgentTier
    paradigm: Optional[AgentParadigm] = None
    specialty: Optional[AgentSpecialty] = None
    parent_agent_id: Optional[str] = None
    task_id: Optional[str] = None
    assigned_checkpoint: Optional[str] = None
    is_idle: bool = True
    current_task: Optional[str] = None


# 7 Permanent Agents with their paradigms and specialties
PERMANENT_AGENTS = {
    "agent_web": AgentSpecialty(
        paradigm=AgentParadigm.WEB_AUTOMATION,
        keywords=["web", "browser", "chrome", "gmail", "website", "url", "http", "online", "internet"],
        capabilities=["CDP", "selenium", "web_scraping", "form_filling", "navigation"],
        description="Web browser automation - handles all web-based tasks"
    ),
    "agent_desktop": AgentSpecialty(
        paradigm=AgentParadigm.DESKTOP_AUTOMATION,
        keywords=["desktop", "app", "application", "notepad", "excel", "windows", "file"],
        capabilities=["DAP", "UIA", "window_management", "process_control", "file_operations"],
        description="Desktop application automation - handles all desktop app tasks"
    ),
    "agent_data": AgentSpecialty(
        paradigm=AgentParadigm.DATA_PROCESSING,
        keywords=["data", "excel", "csv", "database", "process", "transform", "analyze", "statistics"],
        capabilities=["pandas", "data_manipulation", "SQL", "ETL", "reporting"],
        description="Data processing - handles all data manipulation and analysis"
    ),
    "agent_research": AgentSpecialty(
        paradigm=AgentParadigm.RESEARCH_AND_ANALYSIS,
        keywords=["research", "search", "find", "investigate", "gather", "information", "learn"],
        capabilities=["web_research", "document_analysis", "information_extraction", "summarization"],
        description="Research and analysis - handles information gathering and analysis"
    ),
    "agent_comm": AgentSpecialty(
        paradigm=AgentParadigm.COMMUNICATION,
        keywords=["email", "slack", "discord", "message", "send", "notify", "communication"],
        capabilities=["email_automation", "messaging", "notifications", "API_integrations"],
        description="Communication - handles all messaging and communication tasks"
    ),
    "agent_content": AgentSpecialty(
        paradigm=AgentParadigm.CONTENT_CREATION,
        keywords=["write", "create", "generate", "document", "report", "content", "draft"],
        capabilities=["text_generation", "document_creation", "report_generation", "content_creation"],
        description="Content creation - handles all writing and content generation"
    ),
    "agent_system": AgentSpecialty(
        paradigm=AgentParadigm.SYSTEM_MANAGEMENT,
        keywords=["system", "manage", "monitor", "optimize", "configure", "setup", "install"],
        capabilities=["system_monitoring", "resource_management", "automation", "maintenance"],
        description="System management - handles system-level operations"
    ),
}


def detect_specialty(task_text: str) -> Optional[AgentSpecialty]:
    """Detect which permanent agent specialty is needed for a task."""
    task_lower = task_text.lower()
    
    scores = {}
    for agent_id, specialty in PERMANENT_AGENTS.items():
        score = 0
        for keyword in specialty.keywords:
            if keyword in task_lower:
                score += 1
        scores[agent_id] = score
    
    # Find agent with highest score
    if scores:
        best_agent = max(scores, key=scores.get)
        if scores[best_agent] > 0:
            return PERMANENT_AGENTS[best_agent]
    
    return None


def get_idle_permanent_agents() -> List[str]:
    """Get list of idle permanent agents."""
    # In production, this would check actual agent status
    # For now, return all as they can be dynamically distributed
    return list(PERMANENT_AGENTS.keys())


def distribute_task_to_agents(task_text: str, task_id: str) -> Dict[str, AgentSpec]:
    """
    Distribute task to idle permanent agents based on specialty detection.
    
    Returns: Dictionary of agent_id -> AgentSpec
    """
    specialty = detect_specialty(task_text)
    
    assigned_agents = {}
    
    # Primary agent based on specialty
    if specialty:
        primary_agent_id = None
        for agent_id, spec in PERMANENT_AGENTS.items():
            if spec.paradigm == specialty.paradigm:
                primary_agent_id = agent_id
                break
        
        if primary_agent_id:
            assigned_agents[primary_agent_id] = AgentSpec(
                agent_id=primary_agent_id,
                tier=AgentTier.PERMANENT,
                specialty=specialty,
                task_id=task_id,
                is_idle=False,
                current_task=task_text
            )
    
    # Distribute to other idle agents if task is complex
    # (This is a simplified version - in production would be more sophisticated)
    task_complexity = len(task_text.split())
    if task_complexity > 10:  # Complex task
        idle_agents = get_idle_permanent_agents()
        for agent_id in idle_agents:
            if agent_id not in assigned_agents:
                # Check if this agent's specialty is relevant
                spec = PERMANENT_AGENTS[agent_id]
                relevance = any(kw in task_text.lower() for kw in spec.keywords)
                
                if relevance:
                    assigned_agents[agent_id] = AgentSpec(
                        agent_id=agent_id,
                        tier=AgentTier.PERMANENT,
                        specialty=spec,
                        task_id=task_id,
                        is_idle=False,
                        current_task=task_text
                    )
    
    return assigned_agents


def generate_checkpoints(task_text: str, assigned_agents: Dict[str, AgentSpec]) -> List[AgentCheckpoint]:
    """
    Generate checkpoints for task execution.
    
    Checkpoints are created for each phase and assigned to appropriate agents.
    """
    checkpoints = []
    
    # Phase 1: Understanding and Planning
    checkpoints.append(AgentCheckpoint(
        checkpoint_id="checkpoint_1_understanding",
        phase="understanding",
        description="Understand task requirements and create execution plan",
        required_capabilities=["task_understanding", "planning"],
        parent_agent_id="agent_research" if "agent_research" in assigned_agents else list(assigned_agents.keys())[0],
        sub_agents_required=1,
        temporary_agents_required=0
    ))
    
    # Phase 2: Resource Preparation
    checkpoints.append(AgentCheckpoint(
        checkpoint_id="checkpoint_2_preparation",
        phase="preparation",
        description="Prepare resources (launch apps, load data, etc.)",
        required_capabilities=["app_launch", "data_loading"],
        parent_agent_id="agent_desktop" if "agent_desktop" in assigned_agents else list(assigned_agents.keys())[0],
        sub_agents_required=1,
        temporary_agents_required=2
    ))
    
    # Phase 3: Execution
    checkpoints.append(AgentCheckpoint(
        checkpoint_id="checkpoint_3_execution",
        phase="execution",
        description="Execute the main task actions",
        required_capabilities=["task_execution", "automation"],
        parent_agent_id=list(assigned_agents.keys())[0],
        sub_agents_required=2,
        temporary_agents_required=5
    ))
    
    # Phase 4: Verification
    checkpoints.append(AgentCheckpoint(
        checkpoint_id="checkpoint_4_verification",
        phase="verification",
        description="Verify task completion and results",
        required_capabilities=["verification", "validation"],
        parent_agent_id="agent_system" if "agent_system" in assigned_agents else list(assigned_agents.keys())[0],
        sub_agents_required=1,
        temporary_agents_required=1
    ))
    
    # Phase 5: Reporting
    checkpoints.append(AgentCheckpoint(
        checkpoint_id="checkpoint_5_reporting",
        phase="reporting",
        description="Generate detailed report of task execution",
        required_capabilities=["report_generation", "documentation"],
        parent_agent_id="agent_content" if "agent_content" in assigned_agents else list(assigned_agents.keys())[0],
        sub_agents_required=1,
        temporary_agents_required=0
    ))
    
    return checkpoints


if __name__ == "__main__":
    # Test the agent structure
    print("Testing Agent Structure")
    print("=" * 60)
    
    # Test specialty detection
    task = "open gmail and remove the spam emails"
    specialty = detect_specialty(task)
    print(f"\nTask: {task}")
    print(f"Detected Specialty: {specialty.paradigm if specialty else 'None'}")
    
    # Test agent distribution
    assigned = distribute_task_to_agents(task, "test_task_123")
    print(f"\nAssigned Agents: {len(assigned)}")
    for agent_id, spec in assigned.items():
        print(f"  - {agent_id}: {spec.specialty.paradigm if spec.specialty else 'No specialty'}")
    
    # Test checkpoint generation
    checkpoints = generate_checkpoints(task, assigned)
    print(f"\nGenerated Checkpoints: {len(checkpoints)}")
    for cp in checkpoints:
        print(f"  - {cp.checkpoint_id}: {cp.phase} ({cp.sub_agents_required} sub, {cp.temporary_agents_required} temp)")
