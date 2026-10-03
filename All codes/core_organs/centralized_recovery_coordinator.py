"""
HOJAIGA AUTOMATION ARCHITECTURE DOC

============================================================
1. MASTER ARCHITECTURE CONTEXT
============================================================
This component is part of the Hojaiga Automation Architecture.
Component Type: System-Level Coordinator
Name: Centralized Recovery Coordinator

============================================================
2. ORGAN/COMPONENT DIAGRAM
============================================================
```mermaid
graph TD
    classDef default fill:#1e1e1e;stroke:#333;stroke-width:2px;color:#d4d4d4;
    classDef component fill:#2d2d2d;stroke:#569cd6;stroke-width:2px,color:#d4d4d4;
    
    COORDINATOR[Recovery Coordinator]
    
    COORDINATOR --> LOCK[Recovery Lock Manager]
    
    COORDINATOR --> STRATEGY[Recovery Strategy Engine]
    
    COORDINATOR --> HISTORY[Recovery History]
    
    COORDINATOR --> NOTIFY[Event Notifier]
    
    class COORDINATOR component
    class LOCK component
    class STRATEGY component
    class HISTORY component
    class NOTIFY component
```

Inputs: Failure events from organs
Outputs: Coordinated recovery actions, conflict prevention
Dependencies: typing, logging, threading, enum...
"""

from __future__ import annotations

import logging
import time
import threading
from typing import Dict, Any, Optional, List, Set, Callable
from dataclasses import dataclass, field
from enum import Enum
import json

logger = logging.getLogger("hojaiga.recovery_coordinator")


class RecoveryStrategy(str, Enum):
    """Recovery strategies for different failure types."""
    RETRY_IMMEDIATE = "retry_immediate"
    RETRY_WITH_BACKOFF = "retry_with_backoff"
    FALLBACK_ALTERNATIVE = "fallback_alternative"
    SKIP_AND_CONTINUE = "skip_and_continue"
    ESCALATE_TO_HUMAN = "escalate_to_human"
    NO_RECOVERY = "no_recovery"


class FailureSeverity(str, Enum):
    """Severity levels for failures."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class FailureEvent:
    """Represents a failure event from an organ."""
    organ: str
    task_id: str
    failure_type: str
    severity: FailureSeverity
    error_message: str
    timestamp: float
    context: Dict[str, Any] = field(default_factory=dict)
    retry_count: int = 0
    max_retries: int = 3
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "organ": self.organ,
            "task_id": self.task_id,
            "failure_type": self.failure_type,
            "severity": self.severity.value,
            "error_message": self.error_message,
            "timestamp": self.timestamp,
            "context": self.context,
            "retry_count": self.retry_count,
            "max_retries": self.max_retries
        }


@dataclass
class RecoveryAction:
    """Represents a recovery action to be taken."""
    action_id: str
    strategy: RecoveryStrategy
    organ: str
    task_id: str
    description: str
    parameters: Dict[str, Any] = field(default_factory=dict)
    timestamp: float = 0.0
    executed: bool = False
    success: bool = False
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "action_id": self.action_id,
            "strategy": self.strategy.value,
            "organ": self.organ,
            "task_id": self.task_id,
            "description": self.description,
            "parameters": self.parameters,
            "timestamp": self.timestamp,
            "executed": self.executed,
            "success": self.success
        }


class CentralizedRecoveryCoordinator:
    """
    Centralized recovery coordinator that:
    - Coordinates recovery across all organs
    - Prevents conflicting retry mechanisms
    - Implements intelligent recovery strategies
    - Tracks recovery history and success rates
    - Provides escalation paths for critical failures
    """
    
    def __init__(self):
        self._active_recoveries: Dict[str, RecoveryAction] = {}
        self._recovery_locks: Dict[str, threading.Lock] = {}
        self._lock = threading.Lock()
        self._failure_history: List[FailureEvent] = []
        self._recovery_history: List[RecoveryAction] = []
        self._max_history = 1000
        self._recovery_handlers: Dict[str, Callable] = {}
        self._running = False
        self._monitor_thread: Optional[threading.Thread] = None
        
        # Register default recovery handlers
        self._register_default_handlers()
        
        logger.info("[Recovery Coordinator] Initialized")
    
    def _register_default_handlers(self) -> None:
        """Register default recovery handlers for common organs."""
        self._recovery_handlers = {
            "organ_01_crewai_engine": self._handle_crewai_recovery,
            "organ_19_chrome_cdp_runtime": self._handle_cdp_recovery,
            "organ_30_app_scanner": self._handle_app_scanner_recovery,
            "organ_31_visual_perception": self._handle_vision_recovery,
            "organ_37_llm_gateway": self._handle_llm_gateway_recovery,
            "organ_38_task_orchestrator": self._handle_orchestrator_recovery
        }
        
        logger.info(f"[Recovery Coordinator] Registered {len(self._recovery_handlers)} default handlers")
    
    def start(self) -> None:
        """Start the recovery coordinator daemon."""
        if self._running:
            logger.info("[Recovery Coordinator] Already running")
            return
        
        self._running = True
        self._monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True, name="recovery-coordinator")
        self._monitor_thread.start()
        logger.info("[Recovery Coordinator] Daemon started")
    
    def stop(self) -> None:
        """Stop the recovery coordinator daemon."""
        self._running = False
        if self._monitor_thread:
            self._monitor_thread.join(timeout=5.0)
        logger.info("[Recovery Coordinator] Daemon stopped")
    
    def report_failure(self, failure: FailureEvent) -> RecoveryAction:
        """
        Report a failure and request recovery.
        
        Args:
            failure: Failure event details
        
        Returns:
            Recovery action to be taken
        """
        # Record failure
        self._record_failure(failure)
        
        # Check if recovery is already in progress for this task
        recovery_key = f"{failure.organ}_{failure.task_id}"
        
        with self._lock:
            if recovery_key in self._active_recoveries:
                existing = self._active_recoveries[recovery_key]
                logger.info(f"[Recovery Coordinator] Recovery already in progress: {recovery_key}")
                return existing
            
            # Acquire recovery lock
            if recovery_key not in self._recovery_locks:
                self._recovery_locks[recovery_key] = threading.Lock()
        
        # Determine recovery strategy
        strategy = self._determine_strategy(failure)
        
        # Create recovery action
        action = RecoveryAction(
            action_id=f"recovery_{int(time.time() * 1000)}",
            strategy=strategy,
            organ=failure.organ,
            task_id=failure.task_id,
            description=self._get_strategy_description(strategy, failure),
            parameters={"retry_count": failure.retry_count + 1},
            timestamp=time.time()
        )
        
        # Register as active recovery
        with self._lock:
            self._active_recoveries[recovery_key] = action
        
        logger.info(f"[Recovery Coordinator] Created recovery action: {action.action_id} for {recovery_key}")
        
        # Execute recovery
        self._execute_recovery(action, failure)
        
        return action
    
    def _determine_strategy(self, failure: FailureEvent) -> RecoveryStrategy:
        """Determine the appropriate recovery strategy based on failure type and severity."""
        # Check retry limit
        if failure.retry_count >= failure.max_retries:
            return RecoveryStrategy.ESCALATE_TO_HUMAN
        
        # Determine based on severity
        if failure.severity == FailureSeverity.CRITICAL:
            return RecoveryStrategy.ESCALATE_TO_HUMAN
        elif failure.severity == FailureSeverity.HIGH:
            return RecoveryStrategy.FALLBACK_ALTERNATIVE
        elif failure.severity == FailureSeverity.MEDIUM:
            return RecoveryStrategy.RETRY_WITH_BACKOFF
        else:  # LOW
            return RecoveryStrategy.RETRY_IMMEDIATE
    
    def _get_strategy_description(self, strategy: RecoveryStrategy, failure: FailureEvent) -> str:
        """Get a human-readable description of the recovery strategy."""
        descriptions = {
            RecoveryStrategy.RETRY_IMMEDIATE: f"Immediate retry for {failure.organ}",
            RecoveryStrategy.RETRY_WITH_BACKOFF: f"Retry with exponential backoff for {failure.organ}",
            RecoveryStrategy.FALLBACK_ALTERNATIVE: f"Use fallback alternative for {failure.organ}",
            RecoveryStrategy.SKIP_AND_CONTINUE: f"Skip failure and continue for {failure.organ}",
            RecoveryStrategy.ESCALATE_TO_HUMAN: f"Escalate to human intervention for {failure.organ}",
            RecoveryStrategy.NO_RECOVERY: f"No recovery strategy for {failure.organ}"
        }
        return descriptions.get(strategy, "Unknown strategy")
    
    def _execute_recovery(self, action: RecoveryAction, failure: FailureEvent) -> bool:
        """Execute a recovery action."""
        recovery_key = f"{action.organ}_{action.task_id}"
        
        # Acquire lock to prevent concurrent recoveries
        with self._recovery_locks.get(recovery_key, threading.Lock()):
            try:
                logger.info(f"[Recovery Coordinator] Executing recovery: {action.action_id}")
                
                # Get handler for this organ
                handler = self._recovery_handlers.get(action.organ)
                
                if handler:
                    success = handler(action, failure)
                else:
                    # Default handler
                    success = self._handle_default_recovery(action, failure)
                
                action.executed = True
                action.success = success
                
                # Record recovery
                self._record_recovery(action)
                
                # Remove from active recoveries
                with self._lock:
                    if recovery_key in self._active_recoveries:
                        del self._active_recoveries[recovery_key]
                
                if success:
                    logger.info(f"[Recovery Coordinator] Recovery successful: {action.action_id}")
                else:
                    logger.warning(f"[Recovery Coordinator] Recovery failed: {action.action_id}")
                
                return success
                
            except Exception as e:
                logger.error(f"[Recovery Coordinator] Recovery execution error: {e}")
                action.executed = True
                action.success = False
                self._record_recovery(action)
                return False
    
    def _handle_default_recovery(self, action: RecoveryAction, failure: FailureEvent) -> bool:
        """Default recovery handler for unknown organs."""
        if action.strategy == RecoveryStrategy.RETRY_IMMEDIATE:
            # Simple retry
            time.sleep(0.5)
            return True
        elif action.strategy == RecoveryStrategy.RETRY_WITH_BACKOFF:
            # Exponential backoff
            delay = min(2 ** failure.retry_count, 30)
            time.sleep(delay)
            return True
        else:
            logger.warning(f"[Recovery Coordinator] Cannot execute strategy {action.strategy} for {action.organ}")
            return False
    
    def _handle_crewai_recovery(self, action: RecoveryAction, failure: FailureEvent) -> bool:
        """Recovery handler for CrewAI engine."""
        if "agent" in failure.failure_type.lower():
            # Agent creation failure - try with simpler paradigm
            action.parameters["simplified_paradigm"] = True
            time.sleep(1.0)
            return True
        elif "tool" in failure.failure_type.lower():
            # Tool failure - skip tool and continue
            action.parameters["skip_tool"] = True
            return True
        else:
            return self._handle_default_recovery(action, failure)
    
    def _handle_cdp_recovery(self, action: RecoveryAction, failure: FailureEvent) -> bool:
        """Recovery handler for Chrome CDP runtime."""
        if "connection" in failure.failure_type.lower():
            # Connection failure - restart CDP
            action.parameters["restart_cdp"] = True
            time.sleep(2.0)
            return True
        elif "page" in failure.failure_type.lower():
            # Page navigation failure - retry with fallback URL
            action.parameters["fallback_url"] = True
            time.sleep(1.0)
            return True
        else:
            return self._handle_default_recovery(action, failure)
    
    def _handle_app_scanner_recovery(self, action: RecoveryAction, failure: FailureEvent) -> bool:
        """Recovery handler for App Scanner."""
        if "window" in failure.failure_type.lower():
            # Window finding failure - try alternative method
            action.parameters["alternative_method"] = True
            time.sleep(1.0)
            return True
        elif "uia" in failure.failure_type.lower():
            # UIA failure - use fallback walker
            action.parameters["manual_walk"] = True
            return True
        else:
            return self._handle_default_recovery(action, failure)
    
    def _handle_vision_recovery(self, action: RecoveryAction, failure: FailureEvent) -> bool:
        """Recovery handler for Visual Perception."""
        if "model" in failure.failure_type.lower():
            # Model failure - try fallback model
            action.parameters["fallback_model"] = True
            time.sleep(1.0)
            return True
        elif "ocr" in failure.failure_type.lower():
            # OCR failure - skip OCR and use UIA
            action.parameters["skip_ocr"] = True
            return True
        else:
            return self._handle_default_recovery(action, failure)
    
    def _handle_llm_gateway_recovery(self, action: RecoveryAction, failure: FailureEvent) -> bool:
        """Recovery handler for LLM Gateway."""
        if "connection" in failure.failure_type.lower():
            # Connection failure - retry with backoff
            delay = min(2 ** failure.retry_count, 10)
            time.sleep(delay)
            return True
        elif "timeout" in failure.failure_type.lower():
            # Timeout - increase timeout
            action.parameters["increased_timeout"] = True
            return True
        else:
            return self._handle_default_recovery(action, failure)
    
    def _handle_orchestrator_recovery(self, action: RecoveryAction, failure: FailureEvent) -> bool:
        """Recovery handler for Task Orchestrator."""
        if "dependency" in failure.failure_type.lower():
            # Dependency failure - skip task
            action.parameters["skip_task"] = True
            return True
        elif "resource" in failure.failure_type.lower():
            # Resource failure - retry with lower resource requirements
            action.parameters["lower_resources"] = True
            time.sleep(1.0)
            return True
        else:
            return self._handle_default_recovery(action, failure)
    
    def _record_failure(self, failure: FailureEvent) -> None:
        """Record a failure event."""
        self._failure_history.append(failure)
        
        # Trim history
        if len(self._failure_history) > self._max_history:
            self._failure_history = self._failure_history[-self._max_history:]
    
    def _record_recovery(self, action: RecoveryAction) -> None:
        """Record a recovery action."""
        self._recovery_history.append(action)
        
        # Trim history
        if len(self._recovery_history) > self._max_history:
            self._recovery_history = self._recovery_history[-self._max_history:]
    
    def _monitor_loop(self) -> None:
        """Background monitoring loop."""
        logger.info("[Recovery Coordinator] Monitor loop started")
        
        while self._running:
            try:
                time.sleep(5.0)
                
                # Clean up old active recoveries
                self._cleanup_stale_recoveries()
                
                # Clean up old history
                self._cleanup_history()
                
            except Exception as e:
                logger.error(f"[Recovery Coordinator] Monitor loop error: {e}")
        
        logger.info("[Recovery Coordinator] Monitor loop stopped")
    
    def _cleanup_stale_recoveries(self) -> None:
        """Clean up stale active recoveries."""
        current_time = time.time()
        stale_threshold = 300  # 5 minutes
        
        with self._lock:
            stale_keys = [
                key for key, action in self._active_recoveries.items()
                if current_time - action.timestamp > stale_threshold
            ]
            
            for key in stale_keys:
                logger.warning(f"[Recovery Coordinator] Cleaning up stale recovery: {key}")
                del self._active_recoveries[key]
    
    def _cleanup_history(self) -> None:
        """Clean up old history records."""
        cutoff = time.time() - 3600  # Keep last hour
        
        self._failure_history = [f for f in self._failure_history if f.timestamp > cutoff]
        self._recovery_history = [r for r in self._recovery_history if r.timestamp > cutoff]
    
    def get_recovery_status(self, task_id: str) -> Optional[RecoveryAction]:
        """Get the current recovery status for a task."""
        with self._lock:
            for action in self._active_recoveries.values():
                if action.task_id == task_id:
                    return action
        return None
    
    def get_recovery_statistics(self) -> Dict[str, Any]:
        """Get recovery statistics."""
        if not self._recovery_history:
            return {"total_recoveries": 0, "success_rate": 0.0}
        
        total = len(self._recovery_history)
        successful = sum(1 for r in self._recovery_history if r.success)
        
        # Statistics by organ
        by_organ: Dict[str, Dict[str, int]] = {}
        for action in self._recovery_history:
            if action.organ not in by_organ:
                by_organ[action.organ] = {"total": 0, "successful": 0}
            by_organ[action.organ]["total"] += 1
            if action.success:
                by_organ[action.organ]["successful"] += 1
        
        return {
            "total_recoveries": total,
            "successful_recoveries": successful,
            "success_rate": successful / total if total > 0 else 0.0,
            "by_organ": by_organ,
            "active_recoveries": len(self._active_recoveries)
        }
    
    def register_recovery_handler(self, organ: str, handler: Callable) -> None:
        """Register a custom recovery handler for an organ."""
        self._recovery_handlers[organ] = handler
        logger.info(f"[Recovery Coordinator] Registered custom handler for: {organ}")


# Singleton instance
_recovery_coordinator_instance: Optional[CentralizedRecoveryCoordinator] = None

def get_recovery_coordinator() -> CentralizedRecoveryCoordinator:
    """Get the singleton recovery coordinator instance."""
    global _recovery_coordinator_instance
    if _recovery_coordinator_instance is None:
        _recovery_coordinator_instance = CentralizedRecoveryCoordinator()
    return _recovery_coordinator_instance


def report_failure(organ: str, task_id: str, failure_type: str, 
                  severity: str, error_message: str, 
                  context: Optional[Dict[str, Any]] = None,
                  retry_count: int = 0, max_retries: int = 3) -> RecoveryAction:
    """
    Convenience function to report a failure.
    
    Args:
        organ: Organ that failed
        task_id: Task identifier
        failure_type: Type of failure
        severity: Severity level (low, medium, high, critical)
        error_message: Error message
        context: Additional context
        retry_count: Current retry count
        max_retries: Maximum retries allowed
    
    Returns:
        Recovery action to be taken
    """
    coordinator = get_recovery_coordinator()
    
    failure = FailureEvent(
        organ=organ,
        task_id=task_id,
        failure_type=failure_type,
        severity=FailureSeverity(severity.lower()),
        error_message=error_message,
        timestamp=time.time(),
        context=context or {},
        retry_count=retry_count,
        max_retries=max_retries
    )
    
    return coordinator.report_failure(failure)
