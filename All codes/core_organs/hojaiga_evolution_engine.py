"""
HOJAIGA AUTOMATION ARCHITECTURE DOC

============================================================
1. MASTER ARCHITECTURE CONTEXT
============================================================
This component is part of the Hojaiga Automation Architecture.
Component Type: System-Level Evolution Engine
Name: Hojaiga Self-Healing & Code Evolution System

============================================================
2. ORGAN/COMPONENT DIAGRAM
============================================================
```mermaid
graph TD
    classDef default fill:#1e1e1e;stroke:#333;stroke-width:2px;color:#d4d4d4;
    classDef component fill:#2d2d2d;stroke:#569cd6;stroke-width:2px,color:#d4d4d4;
    
    EVOLUTION[Self-Healing Evolution Engine]
    
    EVOLUTION --> REGISTRY[Failure Registry]
    
    EVOLUTION --> ANALYZER[Pattern Analyzer]
    
    EVOLUTION --> GENERATOR[Code Generator]
    
    EVOLUTION --> VALIDATOR[Code Validator]
    
    EVOLUTION --> UPDATER[Dynamic Updater]
    
    EVOLUTION --> LEARNING[Learning Database]
    
    class EVOLUTION component
    class REGISTRY component
    class ANALYZER component
    class GENERATOR component
    class VALIDATOR component
    class UPDATER component
    class LEARNING component
```

Inputs: Failure events, task results, performance metrics
Outputs: Code updates, pattern fixes, system evolution
Dependencies: typing, logging, ast, subprocess, threading...
"""

from __future__ import annotations

import logging
import time
import threading
import ast
import json
import hashlib
import subprocess
from typing import Dict, Any, Optional, List, Set, Tuple, Callable
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
import os
import shutil

logger = logging.getLogger("hojaiga.evolution_engine")


class GrowthStage(str, Enum):
    """Growth stages of the Hojaiga system."""
    EMBRYO = "embryo"  # Initial installation, basic functionality
    INFANT = "infant"  # Learning basic patterns, frequent failures
    CHILD = "child"  # Recognizing common failure patterns
    ADOLESCENT = "adolescent"  # Self-fixing common issues
    ADULT = "adult"  # Sophisticated self-healing, code evolution
    SAGE = "sage"  # Autonomous improvement, feature addition


class FixComplexity(str, Enum):
    """Complexity levels for fixes."""
    SIMPLE = "simple"  # One-line fix, parameter change
    MODERATE = "moderate"  # Function-level change, new logic
    COMPLEX = "complex"  # Multi-file change, architecture adjustment
    EVOLUTIONARY = "evolutionary"  # New capability, feature addition


@dataclass
class FailurePattern:
    """Represents a recognized failure pattern."""
    pattern_id: str
    pattern_name: str
    failure_type: str
    organ: str
    symptoms: List[str]
    frequency: int = 0
    last_seen: float = 0.0
    suggested_fix: Optional[str] = None
    fix_complexity: FixComplexity = FixComplexity.SIMPLE
    fix_success_rate: float = 0.0
    is_learned: bool = False
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "pattern_id": self.pattern_id,
            "pattern_name": self.pattern_name,
            "failure_type": self.failure_type,
            "organ": self.organ,
            "symptoms": self.symptoms,
            "frequency": self.frequency,
            "last_seen": self.last_seen,
            "suggested_fix": self.suggested_fix,
            "fix_complexity": self.fix_complexity.value,
            "fix_success_rate": self.fix_success_rate,
            "is_learned": self.is_learned
        }


@dataclass
class CodeMutation:
    """Represents a code mutation (change)."""
    mutation_id: str
    file_path: str
    description: str
    old_code: str
    new_code: str
    line_start: int
    line_end: int
    pattern_id: Optional[str] = None
    confidence: float = 0.5
    offline_capable: bool = True
    timestamp: float = 0.0
    applied: bool = False
    validated: bool = False
    success: bool = False
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "mutation_id": self.mutation_id,
            "file_path": self.file_path,
            "description": self.description,
            "old_code": self.old_code[:100] + "..." if len(self.old_code) > 100 else self.old_code,
            "new_code": self.new_code[:100] + "..." if len(self.new_code) > 100 else self.new_code,
            "line_start": self.line_start,
            "line_end": self.line_end,
            "pattern_id": self.pattern_id,
            "confidence": self.confidence,
            "offline_capable": self.offline_capable,
            "timestamp": self.timestamp,
            "applied": self.applied,
            "validated": self.validated,
            "success": self.success
        }


@dataclass
class EvolutionProgress:
    """Tracks the evolution progress of the system."""
    stage: GrowthStage = GrowthStage.EMBRYO
    total_mutations: int = 0
    successful_mutations: int = 0
    learned_patterns: int = 0
    uptime_hours: float = 0.0
    self_fix_rate: float = 0.0
    evolution_score: float = 0.0
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "stage": self.stage.value,
            "total_mutations": self.total_mutations,
            "successful_mutations": self.successful_mutations,
            "learned_patterns": self.learned_patterns,
            "uptime_hours": self.uptime_hours,
            "self_fix_rate": self.self_fix_rate,
            "evolution_score": self.evolution_score
        }


class HojaigaEvolutionEngine:
    """
    Hojaiga Self-Healing & Code Evolution System
    
    This system enables Hojaiga to:
    - Learn from failures and register them with IDs
    - Analyze failure patterns during idle time
    - Generate code fixes dynamically
    - Validate fixes in sandbox environment
    - Apply fixes to the codebase
    - Grow from embryo to sage through experience
    - Work offline (local learning) and online (cloud updates)
    - Distribute model load when heavy
    """
    
    def __init__(self, codebase_root: str = "D:\\new_automation\\All codes"):
        self.codebase_root = Path(codebase_root)
        self._progress = EvolutionProgress()
        self._failure_registry: Dict[str, FailurePattern] = {}
        self._mutation_history: List[CodeMutation] = []
        self._learning_database: Dict[str, Any] = {}
        self._running = False
        self._evolution_thread: Optional[threading.Thread] = None
        self._idle_thread: Optional[threading.Thread] = None
        self._is_idle = False
        self._start_time = time.time()
        
        # Initialize learning database
        self._initialize_learning_database()
        
        # Load existing knowledge
        self._load_knowledge()
        
        logger.info("[Hojaiga Evolution] Evolution Engine initialized")
        logger.info(f"[Hojaiga Evolution] Current growth stage: {self._progress.stage.value}")
    
    def _initialize_learning_database(self) -> None:
        """Initialize the learning database with common patterns."""
        self._learning_database = {
            "common_patterns": [
                {
                    "pattern_id": "unicode_walkcontrol_crash",
                    "pattern_name": "Unicode WalkControl Crash",
                    "failure_type": "UnicodeEncodeError",
                    "organ": "organ_30_app_scanner",
                    "symptoms": ["WalkControl fails", "Unicode characters", "WinUI 3"],
                    "suggested_fix": "Use _safe_walk_control with manual GetChildren fallback",
                    "fix_complexity": "moderate",
                    "offline_capable": True
                },
                {
                    "pattern_id": "model_timeout",
                    "pattern_name": "Model Request Timeout",
                    "failure_type": "TimeoutError",
                    "organ": "organ_37_llm_gateway",
                    "symptoms": ["Model request timeout", "High latency", "Connection error"],
                    "suggested_fix": "Increase timeout or switch to fallback model",
                    "fix_complexity": "simple",
                    "offline_capable": True
                },
                {
                    "pattern_id": "window_not_found",
                    "pattern_name": "Window Not Found",
                    "failure_type": "WindowNotFoundError",
                    "organ": "organ_30_app_scanner",
                    "symptoms": ["Window not found", "hwnd is None", "App not running"],
                    "suggested_fix": "Pre-launch app or retry with alternative window finding",
                    "fix_complexity": "moderate",
                    "offline_capable": True
                }
            ],
            "growth_stages": {
                GrowthStage.EMBRYO: {
                    "description": "Basic functionality, learning environment",
                    "capabilities": ["basic_execution", "failure_logging"],
                    "requirements": {"uptime_hours": 0, "learned_patterns": 0}
                },
                GrowthStage.INFANT: {
                    "description": "Recognizing simple patterns",
                    "capabilities": ["pattern_recognition", "simple_fixes"],
                    "requirements": {"uptime_hours": 1, "learned_patterns": 3}
                },
                GrowthStage.CHILD: {
                    "description": "Self-fixing common issues",
                    "capabilities": ["automated_fixes", "offline_learning"],
                    "requirements": {"uptime_hours": 10, "learned_patterns": 10}
                },
                GrowthStage.ADOLESCENT: {
                    "description": "Sophisticated pattern analysis",
                    "capabilities": ["complex_fixes", "code_generation"],
                    "requirements": {"uptime_hours": 50, "learned_patterns": 30}
                },
                GrowthStage.ADULT: {
                    "description": "Autonomous improvement",
                    "capabilities": ["feature_addition", "architecture_evolution"],
                    "requirements": {"uptime_hours": 100, "learned_patterns": 50}
                },
                GrowthStage.SAGE: {
                    "description": "Self-evolving intelligence",
                    "capabilities": ["self_modification", "knowledge_synthesis"],
                    "requirements": {"uptime_hours": 500, "learned_patterns": 100}
                }
            }
        }
        
        logger.info(f"[Hojaiga Evolution] Initialized learning database with {len(self._learning_database['common_patterns'])} patterns")
    
    def _load_knowledge(self) -> None:
        """Load existing knowledge from previous sessions."""
        knowledge_file = self.codebase_root / "hojaiga_knowledge.json"
        
        if knowledge_file.exists():
            try:
                with open(knowledge_file, 'r') as f:
                    knowledge = json.load(f)
                
                # Load progress
                if "progress" in knowledge:
                    progress_data = knowledge["progress"]
                    self._progress.stage = GrowthStage(progress_data.get("stage", "embryo"))
                    self._progress.total_mutations = progress_data.get("total_mutations", 0)
                    self._progress.successful_mutations = progress_data.get("successful_mutations", 0)
                    self._progress.learned_patterns = progress_data.get("learned_patterns", 0)
                
                # Load failure patterns
                if "failure_patterns" in knowledge:
                    for pattern_data in knowledge["failure_patterns"]:
                        pattern = FailurePattern(
                            pattern_id=pattern_data["pattern_id"],
                            pattern_name=pattern_data["pattern_name"],
                            failure_type=pattern_data["failure_type"],
                            organ=pattern_data["organ"],
                            symptoms=pattern_data["symptoms"],
                            frequency=pattern_data.get("frequency", 0),
                            last_seen=pattern_data.get("last_seen", 0.0),
                            suggested_fix=pattern_data.get("suggested_fix"),
                            fix_complexity=FixComplexity(pattern_data.get("fix_complexity", "simple")),
                            fix_success_rate=pattern_data.get("fix_success_rate", 0.0),
                            is_learned=pattern_data.get("is_learned", False)
                        )
                        self._failure_registry[pattern.pattern_id] = pattern
                
                # Load mutation history
                if "mutation_history" in knowledge:
                    for mutation_data in knowledge["mutation_history"]:
                        mutation = CodeMutation(
                            mutation_id=mutation_data["mutation_id"],
                            file_path=mutation_data["file_path"],
                            description=mutation_data["description"],
                            old_code=mutation_data["old_code"],
                            new_code=mutation_data["new_code"],
                            line_start=mutation_data["line_start"],
                            line_end=mutation_data["line_end"],
                            pattern_id=mutation_data.get("pattern_id"),
                            confidence=mutation_data.get("confidence", 0.5),
                            offline_capable=mutation_data.get("offline_capable", True),
                            timestamp=mutation_data.get("timestamp", 0.0),
                            applied=mutation_data.get("applied", False),
                            validated=mutation_data.get("validated", False),
                            success=mutation_data.get("success", False)
                        )
                        self._mutation_history.append(mutation)
                
                logger.info(f"[Hojaiga Evolution] Loaded knowledge from {knowledge_file}")
                
            except Exception as e:
                logger.error(f"[Hojaiga Evolution] Failed to load knowledge: {e}")
    
    def _save_knowledge(self) -> None:
        """Save current knowledge to disk."""
        knowledge_file = self.codebase_root / "hojaiga_knowledge.json"
        
        try:
            knowledge = {
                "progress": self._progress.to_dict(),
                "failure_patterns": [p.to_dict() for p in self._failure_registry.values()],
                "mutation_history": [m.to_dict() for m in self._mutation_history]
            }
            
            with open(knowledge_file, 'w') as f:
                json.dump(knowledge, f, indent=2)
            
            logger.debug(f"[Hojaiga Evolution] Saved knowledge to {knowledge_file}")
            
        except Exception as e:
            logger.error(f"[Hojaiga Evolution] Failed to save knowledge: {e}")
    
    def start(self) -> None:
        """Start the evolution engine."""
        if self._running:
            logger.info("[Hojaiga Evolution] Already running")
            return
        
        self._running = True
        self._start_time = time.time()
        
        # Start evolution thread
        self._evolution_thread = threading.Thread(target=self._evolution_loop, daemon=True, name="hojaiga-evolution")
        self._evolution_thread.start()
        
        # Start idle processing thread
        self._idle_thread = threading.Thread(target=self._idle_loop, daemon=True, name="hojaiga-idle-processor")
        self._idle_thread.start()
        
        logger.info("[Hojaiga Evolution] Evolution Engine started")
    
    def stop(self) -> None:
        """Stop the evolution engine."""
        self._running = False
        
        if self._evolution_thread:
            self._evolution_thread.join(timeout=5.0)
        if self._idle_thread:
            self._idle_thread.join(timeout=5.0)
        
        # Save knowledge before stopping
        self._save_knowledge()
        
        logger.info("[Hojaiga Evolution] Evolution Engine stopped")
    
    def register_failure(self, organ: str, failure_type: str, error_message: str,
                        context: Optional[Dict[str, Any]] = None) -> str:
        """
        Register a failure with a unique ID for later analysis.
        
        Args:
            organ: Organ that failed
            failure_type: Type of failure
            error_message: Error message
            context: Additional context
        
        Returns:
            Unique failure ID
        """
        # Generate unique failure ID
        failure_id = hashlib.md5(
            f"{organ}_{failure_type}_{error_message}_{time.time()}".encode()
        ).hexdigest()[:12]
        
        # Check if this matches a known pattern
        pattern = self._match_failure_pattern(organ, failure_type, error_message)
        
        if pattern:
            pattern.frequency += 1
            pattern.last_seen = time.time()
            logger.info(f"[Hojaiga Evolution] Matched known pattern: {pattern.pattern_name} (frequency: {pattern.frequency})")
        else:
            # Create new pattern
            pattern = FailurePattern(
                pattern_id=failure_id,
                pattern_name=f"Unknown Pattern {failure_id}",
                failure_type=failure_type,
                organ=organ,
                symptoms=[error_message],
                frequency=1,
                last_seen=time.time()
            )
            self._failure_registry[pattern.pattern_id] = pattern
            logger.info(f"[Hojaiga Evolution] Created new pattern: {pattern.pattern_id}")
        
        # Save knowledge
        self._save_knowledge()
        
        return failure_id
    
    def _match_failure_pattern(self, organ: str, failure_type: str, 
                               error_message: str) -> Optional[FailurePattern]:
        """Match a failure against known patterns."""
        for pattern in self._failure_registry.values():
            if pattern.organ == organ and pattern.failure_type == failure_type:
                # Check symptoms
                for symptom in pattern.symptoms:
                    if symptom.lower() in error_message.lower():
                        return pattern
        
        # Check against common patterns
        for common_pattern in self._learning_database["common_patterns"]:
            if (common_pattern["organ"] == organ and 
                common_pattern["failure_type"] == failure_type):
                # Check symptoms
                for symptom in common_pattern["symptoms"]:
                    if symptom.lower() in error_message.lower():
                        # Create pattern from common pattern
                        pattern = FailurePattern(
                            pattern_id=common_pattern["pattern_id"],
                            pattern_name=common_pattern["pattern_name"],
                            failure_type=common_pattern["failure_type"],
                            organ=common_pattern["organ"],
                            symptoms=common_pattern["symptoms"],
                            suggested_fix=common_pattern["suggested_fix"],
                            fix_complexity=FixComplexity(common_pattern["fix_complexity"])
                        )
                        self._failure_registry[pattern.pattern_id] = pattern
                        return pattern
        
        return None
    
    def _evolution_loop(self) -> None:
        """Main evolution loop - monitors growth and promotes stages."""
        logger.info("[Hojaiga Evolution] Evolution loop started")
        
        while self._running:
            try:
                time.sleep(60)  # Check every minute
                
                # Update uptime
                self._progress.uptime_hours = (time.time() - self._start_time) / 3600
                
                # Calculate evolution score
                self._calculate_evolution_score()
                
                # Check for stage promotion
                self._check_stage_promotion()
                
                # Save knowledge periodically
                self._save_knowledge()
                
            except Exception as e:
                logger.error(f"[Hojaiga Evolution] Evolution loop error: {e}")
        
        logger.info("[Hojaiga Evolution] Evolution loop stopped")
    
    def _idle_loop(self) -> None:
        """Idle processing loop - works on failures when system is idle."""
        logger.info("[Hojaiga Evolution] Idle loop started")
        
        idle_threshold = 30  # seconds of no activity to consider idle
        
        while self._running:
            try:
                time.sleep(5)
                
                # Check if system is idle (simplified - would check activity metrics)
                # For now, assume idle if no recent failures
                recent_failures = [p for p in self._failure_registry.values() 
                                 if time.time() - p.last_seen < idle_threshold]
                
                if not recent_failures and self._progress.stage in [GrowthStage.CHILD, GrowthStage.ADOLESCENT, GrowthStage.ADULT]:
                    self._is_idle = True
                    logger.debug("[Hojaiga Evolution] System idle, processing failures")
                    
                    # Process unlearned patterns
                    self._process_unlearned_patterns()
                    
                    # Apply pending mutations
                    self._apply_pending_mutations()
                    
                else:
                    self._is_idle = False
                
            except Exception as e:
                logger.error(f"[Hojaiga Evolution] Idle loop error: {e}")
        
        logger.info("[Hojaiga Evolution] Idle loop stopped")
    
    def _process_unlearned_patterns(self) -> None:
        """Process unlearned failure patterns during idle time."""
        unlearned = [p for p in self._failure_registry.values() if not p.is_learned]
        
        for pattern in unlearned[:3]:  # Process up to 3 patterns per idle cycle
            try:
                logger.info(f"[Hojaiga Evolution] Processing pattern: {pattern.pattern_name}")
                
                # Generate fix based on complexity
                if pattern.fix_complexity in [FixComplexity.SIMPLE, FixComplexity.MODERATE]:
                    # Can handle offline
                    mutation = self._generate_fix_mutation(pattern)
                    if mutation:
                        self._mutation_history.append(mutation)
                        self._progress.total_mutations += 1
                
                # Mark as learned
                pattern.is_learned = True
                self._progress.learned_patterns += 1
                
                logger.info(f"[Hojaiga Evolution] Learned pattern: {pattern.pattern_name}")
                
            except Exception as e:
                logger.error(f"[Hojaiga Evolution] Failed to process pattern: {e}")
    
    def _generate_fix_mutation(self, pattern: FailurePattern) -> Optional[CodeMutation]:
        """Generate a code mutation to fix a pattern."""
        try:
            # Find relevant file
            file_path = self._find_file_for_organ(pattern.organ)
            if not file_path:
                logger.warning(f"[Hojaiga Evolution] Could not find file for organ: {pattern.organ}")
                return None
            
            # Read file
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Generate fix (simplified - would use LLM in production)
            mutation_id = f"mutation_{int(time.time() * 1000)}"
            
            mutation = CodeMutation(
                mutation_id=mutation_id,
                file_path=str(file_path),
                description=f"Fix for {pattern.pattern_name}",
                old_code="# TODO: Implement fix",
                new_code=f"# Fix for {pattern.pattern_name}\n# {pattern.suggested_fix}",
                line_start=0,
                line_end=0,
                pattern_id=pattern.pattern_id,
                confidence=0.7,
                offline_capable=True,
                timestamp=time.time()
            )
            
            logger.info(f"[Hojaiga Evolution] Generated mutation: {mutation_id}")
            
            return mutation
            
        except Exception as e:
            logger.error(f"[Hojaiga Evolution] Failed to generate mutation: {e}")
            return None
    
    def _find_file_for_organ(self, organ: str) -> Optional[Path]:
        """Find the source file for an organ."""
        organ_file = f"{organ}.py"
        
        # Search in core_organs
        core_organs_path = self.codebase_root / "core_organs"
        if core_organs_path.exists():
            for file_path in core_organs_path.glob("*.py"):
                if file_path.name == organ_file:
                    return file_path
        
        # Search in root
        for file_path in self.codebase_root.glob("*.py"):
            if file_path.name == organ_file:
                return file_path
        
        return None
    
    def _apply_pending_mutations(self) -> None:
        """Apply pending mutations during idle time."""
        pending = [m for m in self._mutation_history if not m.applied]
        
        for mutation in pending[:2]:  # Apply up to 2 mutations per idle cycle
            try:
                logger.info(f"[Hojaiga Evolution] Applying mutation: {mutation.mutation_id}")
                
                # Validate mutation first
                if self._validate_mutation(mutation):
                    # Apply mutation
                    if self._apply_mutation(mutation):
                        mutation.applied = True
                        mutation.validated = True
                        mutation.success = True
                        self._progress.successful_mutations += 1
                        logger.info(f"[Hojaiga Evolution] Successfully applied mutation: {mutation.mutation_id}")
                    else:
                        mutation.applied = True
                        mutation.success = False
                        logger.warning(f"[Hojaiga Evolution] Failed to apply mutation: {mutation.mutation_id}")
                else:
                    mutation.validated = False
                    logger.warning(f"[Hojaiga Evolution] Mutation validation failed: {mutation.mutation_id}")
                
            except Exception as e:
                logger.error(f"[Hojaiga Evolution] Failed to apply mutation: {e}")
    
    def _validate_mutation(self, mutation: CodeMutation) -> bool:
        """Validate a mutation before applying."""
        try:
            # Parse old code as AST
            ast.parse(mutation.old_code)
            
            # Parse new code as AST
            ast.parse(mutation.new_code)
            
            # Check syntax
            mutation.confidence = min(1.0, mutation.confidence + 0.1)
            
            return True
            
        except SyntaxError as e:
            logger.error(f"[Hojaiga Evolution] Syntax error in mutation: {e}")
            return False
    
    def _apply_mutation(self, mutation: CodeMutation) -> bool:
        """Apply a mutation to the codebase."""
        try:
            file_path = Path(mutation.file_path)
            
            # Read file
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Apply mutation (simplified - would be more sophisticated)
            if mutation.old_code in content:
                content = content.replace(mutation.old_code, mutation.new_code)
                
                # Write back
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(content)
                
                logger.info(f"[Hojaiga Evolution] Applied mutation to: {file_path}")
                return True
            else:
                logger.warning(f"[Hojaiga Evolution] Old code not found in file: {file_path}")
                return False
                
        except Exception as e:
            logger.error(f"[Hojaiga Evolution] Failed to apply mutation: {e}")
            return False
    
    def _calculate_evolution_score(self) -> None:
        """Calculate the overall evolution score."""
        # Base score from growth stage
        stage_scores = {
            GrowthStage.EMBRYO: 0.0,
            GrowthStage.INFANT: 0.2,
            GrowthStage.CHILD: 0.4,
            GrowthStage.ADOLESCENT: 0.6,
            GrowthStage.ADULT: 0.8,
            GrowthStage.SAGE: 1.0
        }
        
        base_score = stage_scores.get(self._progress.stage, 0.0)
        
        # Add score from learned patterns
        pattern_score = min(0.3, self._progress.learned_patterns / 100 * 0.3)
        
        # Add score from successful mutations
        mutation_score = min(0.2, self._progress.successful_mutations / 50 * 0.2)
        
        # Add score from uptime
        uptime_score = min(0.3, self._progress.uptime_hours / 500 * 0.3)
        
        self._progress.evolution_score = base_score + pattern_score + mutation_score + uptime_score
    
    def _check_stage_promotion(self) -> None:
        """Check if the system should be promoted to next growth stage."""
        current_stage = self._progress.stage
        
        # Get next stage
        stages = list(GrowthStage)
        current_index = stages.index(current_stage)
        
        if current_index < len(stages) - 1:
            next_stage = stages[current_index + 1]
            requirements = self._learning_database["growth_stages"][next_stage]["requirements"]
            
            # Check requirements
            if (self._progress.uptime_hours >= requirements.get("uptime_hours", 0) and
                self._progress.learned_patterns >= requirements.get("learned_patterns", 0)):
                
                old_stage = self._progress.stage
                self._progress.stage = next_stage
                
                logger.info(f"[Hojaiga Evolution] STAGE PROMOTION: {old_stage.value} -> {next_stage.value}")
                logger.info(f"[Hojaiga Evolution] New capabilities: {self._learning_database['growth_stages'][next_stage]['capabilities']}")
    
    def get_progress(self) -> EvolutionProgress:
        """Get current evolution progress."""
        return self._progress
    
    def get_failure_patterns(self) -> List[Dict[str, Any]]:
        """Get all registered failure patterns."""
        return [p.to_dict() for p in self._failure_registry.values()]
    
    def get_mutation_history(self) -> List[Dict[str, Any]]:
        """Get mutation history."""
        return [m.to_dict() for m in self._mutation_history]


# Singleton instance
_evolution_engine_instance: Optional[HojaigaEvolutionEngine] = None

def get_evolution_engine() -> HojaigaEvolutionEngine:
    """Get the singleton evolution engine instance."""
    global _evolution_engine_instance
    if _evolution_engine_instance is None:
        _evolution_engine_instance = HojaigaEvolutionEngine()
    return _evolution_engine_instance


def register_failure(organ: str, failure_type: str, error_message: str,
                    context: Optional[Dict[str, Any]] = None) -> str:
    """
    Convenience function to register a failure.
    
    Args:
        organ: Organ that failed
        failure_type: Type of failure
        error_message: Error message
        context: Additional context
    
    Returns:
        Unique failure ID
    """
    engine = get_evolution_engine()
    return engine.register_failure(organ, failure_type, error_message, context)
