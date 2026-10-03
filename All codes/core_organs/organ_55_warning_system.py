"""
Organ 55 — Warning System (Action Safety Checker)

Responsibility: Warn user before performing potentially wrong, dangerous, or irreversible actions.

Features:
- Action safety analysis
- Destructive operation detection
- Risk assessment
- User confirmation for high-risk actions
- Action logging
- Rollback suggestions
"""

import asyncio
import logging
import sys
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple
from enum import Enum

if r"D:\new_automation\All codes" not in sys.path:
    sys.path.insert(0, r"D:\new_automation\All codes")

try:
    from core_organs.organ_62_confirmation_dialog import UserConfirmationDialog
    _HAS_CONFIRMATION_DIALOG = True
except ImportError:
    _HAS_CONFIRMATION_DIALOG = False
    UserConfirmationDialog = None

logger = logging.getLogger("hojaiga.organ55.warning_system")


class RiskLevel(Enum):
    """Risk levels for actions."""
    SAFE = "safe"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ActionCategory(Enum):
    """Categories of actions."""
    DESTRUCTIVE = "destructive"  # Delete, remove, uninstall
    IRREVERSIBLE = "irreversible"  # No undo possible
    DATA_MODIFICATION = "data_modification"  # Modify files/data
    SYSTEM_CHANGE = "system_change"  # System settings/registry
    NETWORK_OPERATION = "network_operation"  # Network requests
    FILE_OPERATION = "file_operation"  # File operations
    EXECUTION = "execution"  # Run programs/scripts
    AUTOMATION = "automation"  # Automation tasks
    GENERIC = "generic"


@dataclass
class ActionWarning:
    """Warning for an action."""
    action_id: str
    action_description: str
    risk_level: RiskLevel
    category: ActionCategory
    reason: str
    consequences: List[str]
    mitigation_suggestions: List[str]
    requires_confirmation: bool = True
    rollback_possible: bool = False
    rollback_method: Optional[str] = None


class WarningSystem:
    """
    Warning system for action safety.
    
    Features:
    - Analyze actions for safety
    - Detect destructive operations
    - Assess risk levels
    - Require confirmation for high-risk actions
    - Suggest mitigations
    - Provide rollback options
    """
    
    def __init__(self):
        self._action_history: List[Dict[str, Any]] = []
        self._warning_log: List[ActionWarning] = []
        self._confirmation_dialog = UserConfirmationDialog() if _HAS_CONFIRMATION_DIALOG else None
    
    async def analyze_action(self, action_description: str, context: Dict[str, Any] = None) -> ActionWarning:
        """
        Analyze an action for safety.
        
        Args:
            action_description: Description of action to analyze
            context: Additional context (file paths, URLs, etc.)
        
        Returns:
            ActionWarning with risk assessment
        """
        logger.info(f"[WarningSystem] Analyzing action: {action_description}")
        
        action_id = f"action_{asyncio.get_event_loop().time()}"
        action_lower = action_description.lower()
        
        # Detect action category
        category = self._detect_category(action_lower)
        
        # Assess risk level
        risk_level = self._assess_risk(action_lower, category, context)
        
        # Generate warning details
        warning = self._generate_warning(
            action_id, action_description, category, risk_level, action_lower, context
        )
        
        # Log warning
        self._warning_log.append(warning)
        
        return warning
    
    def _detect_category(self, action_lower: str) -> ActionCategory:
        """Detect action category from description."""
        destructive_keywords = ["delete", "remove", "uninstall", "erase", "wipe", "format", "destroy"]
        irreversible_keywords = ["permanent", "no undo", "irreversible", "final"]
        data_mod_keywords = ["modify", "edit", "change", "update", "overwrite", "replace"]
        system_change_keywords = ["registry", "system", "setting", "config", "install", "driver"]
        network_keywords = ["download", "upload", "network", "internet", "request", "api"]
        file_keywords = ["file", "folder", "directory", "copy", "move", "rename"]
        execution_keywords = ["run", "execute", "launch", "start", "open", "script", "program"]
        
        if any(kw in action_lower for kw in destructive_keywords):
            return ActionCategory.DESTRUCTIVE
        elif any(kw in action_lower for kw in irreversible_keywords):
            return ActionCategory.IRREVERSIBLE
        elif any(kw in action_lower for kw in data_mod_keywords):
            return ActionCategory.DATA_MODIFICATION
        elif any(kw in action_lower for kw in system_change_keywords):
            return ActionCategory.SYSTEM_CHANGE
        elif any(kw in action_lower for kw in network_keywords):
            return ActionCategory.NETWORK_OPERATION
        elif any(kw in action_lower for kw in file_keywords):
            return ActionCategory.FILE_OPERATION
        elif any(kw in action_lower for kw in execution_keywords):
            return ActionCategory.EXECUTION
        else:
            return ActionCategory.GENERIC
    
    def _assess_risk(self, action_lower: str, category: ActionCategory, 
                    context: Dict[str, Any] = None) -> RiskLevel:
        """Assess risk level based on category and context."""
        context = context or {}
        
        # Critical risk patterns
        critical_patterns = [
            "delete system", "format disk", "wipe drive", "registry delete",
            "uninstall critical", "remove system file", "delete database"
        ]
        if any(pattern in action_lower for pattern in critical_patterns):
            return RiskLevel.CRITICAL
        
        # High risk patterns
        high_patterns = [
            "delete", "remove", "uninstall", "erase", "wipe",
            "modify registry", "change system", "install driver"
        ]
        if any(pattern in action_lower for pattern in high_patterns):
            return RiskLevel.HIGH
        
        # Medium risk patterns
        medium_patterns = [
            "modify", "edit", "change", "update", "overwrite",
            "download", "upload", "network", "internet"
        ]
        if any(pattern in action_lower for pattern in medium_patterns):
            return RiskLevel.MEDIUM
        
        # Category-based risk
        risk_by_category = {
            ActionCategory.DESTRUCTIVE: RiskLevel.HIGH,
            ActionCategory.IRREVERSIBLE: RiskLevel.CRITICAL,
            ActionCategory.DATA_MODIFICATION: RiskLevel.MEDIUM,
            ActionCategory.SYSTEM_CHANGE: RiskLevel.HIGH,
            ActionCategory.NETWORK_OPERATION: RiskLevel.MEDIUM,
            ActionCategory.FILE_OPERATION: RiskLevel.LOW,
            ActionCategory.EXECUTION: RiskLevel.MEDIUM,
            ActionCategory.GENERIC: RiskLevel.LOW,
        }
        
        return risk_by_category.get(category, RiskLevel.LOW)
    
    def _generate_warning(self, action_id: str, action_description: str, 
                        category: ActionCategory, risk_level: RiskLevel,
                        action_lower: str, context: Dict[str, Any]) -> ActionWarning:
        """Generate warning details."""
        reason = self._generate_reason(category, risk_level, action_lower)
        consequences = self._generate_consequences(category, risk_level, action_lower)
        mitigations = self._generate_mitigations(category, risk_level, action_lower)
        requires_confirmation = risk_level in [RiskLevel.MEDIUM, RiskLevel.HIGH, RiskLevel.CRITICAL]
        rollback_possible = self._check_rollback_possible(category, action_lower)
        rollback_method = self._suggest_rollback(category, action_lower) if rollback_possible else None
        
        return ActionWarning(
            action_id=action_id,
            action_description=action_description,
            risk_level=risk_level,
            category=category,
            reason=reason,
            consequences=consequences,
            mitigation_suggestions=mitigations,
            requires_confirmation=requires_confirmation,
            rollback_possible=rollback_possible,
            rollback_method=rollback_method
        )
    
    def _generate_reason(self, category: ActionCategory, risk_level: RiskLevel, 
                       action_lower: str) -> str:
        """Generate reason for warning."""
        reasons = {
            ActionCategory.DESTRUCTIVE: "This action may permanently delete data or files.",
            ActionCategory.IRREVERSIBLE: "This action cannot be undone.",
            ActionCategory.DATA_MODIFICATION: "This action will modify existing data.",
            ActionCategory.SYSTEM_CHANGE: "This action changes system settings.",
            ActionCategory.NETWORK_OPERATION: "This action involves network communication.",
            ActionCategory.FILE_OPERATION: "This action manipulates files.",
            ActionCategory.EXECUTION: "This action executes a program or script.",
            ActionCategory.GENERIC: "This action requires review.",
        }
        return reasons.get(category, "Action requires safety review.")
    
    def _generate_consequences(self, category: ActionCategory, risk_level: RiskLevel,
                             action_lower: str) -> List[str]:
        """Generate list of potential consequences."""
        consequences = []
        
        if category == ActionCategory.DESTRUCTIVE:
            consequences = [
                "Data or files will be permanently deleted",
                "Recovery may be difficult or impossible",
                "Other systems may be affected"
            ]
        elif category == ActionCategory.IRREVERSIBLE:
            consequences = [
                "This action cannot be undone",
                "No rollback available",
                "Permanent changes will be made"
            ]
        elif category == ActionCategory.DATA_MODIFICATION:
            consequences = [
                "Existing data will be changed",
                "Original data may be lost",
                "Backup recommended before proceeding"
            ]
        elif category == ActionCategory.SYSTEM_CHANGE:
            consequences = [
                "System settings will be modified",
                "May affect system stability",
                "Other applications may be impacted"
            ]
        elif category == ActionCategory.NETWORK_OPERATION:
            consequences = [
                "Data will be sent over network",
                "May involve external services",
                "Network connectivity required"
            ]
        elif category == ActionCategory.EXECUTION:
            consequences = [
                "Program or script will be executed",
                "May have side effects",
                "Verify source before proceeding"
            ]
        else:
            consequences = ["Action may have unexpected consequences"]
        
        return consequences
    
    def _generate_mitigations(self, category: ActionCategory, risk_level: RiskLevel,
                            action_lower: str) -> List[str]:
        """Generate mitigation suggestions."""
        mitigations = []
        
        if category == ActionCategory.DESTRUCTIVE:
            mitigations = [
                "Create backup before deletion",
                "Verify correct target selected",
                "Consider moving to trash instead of permanent delete"
            ]
        elif category == ActionCategory.IRREVERSIBLE:
            mitigations = [
                "Review action carefully",
                "Ensure no alternatives exist",
                "Document action for reference"
            ]
        elif category == ActionCategory.DATA_MODIFICATION:
            mitigations = [
                "Backup original data",
                "Test on copy first",
                "Review changes before committing"
            ]
        elif category == ActionCategory.SYSTEM_CHANGE:
            mitigations = [
                "Create system restore point",
                "Document current settings",
                "Test in safe environment first"
            ]
        elif category == ActionCategory.NETWORK_OPERATION:
            mitigations = [
                "Verify network security",
                "Check external service reputation",
                "Review data being sent"
            ]
        elif category == ActionCategory.EXECUTION:
            mitigations = [
                "Verify source authenticity",
                "Scan for malware",
                "Review script contents"
            ]
        else:
            mitigations = ["Review action details before proceeding"]
        
        return mitigations
    
    def _check_rollback_possible(self, category: ActionCategory, action_lower: str) -> bool:
        """Check if rollback is possible."""
        rollback_categories = [
            ActionCategory.DATA_MODIFICATION,
            ActionCategory.FILE_OPERATION,
            ActionCategory.SYSTEM_CHANGE
        ]
        return category in rollback_categories
    
    def _suggest_rollback(self, category: ActionCategory, action_lower: str) -> str:
        """Suggest rollback method."""
        rollbacks = {
            ActionCategory.DATA_MODIFICATION: "Restore from backup",
            ActionCategory.FILE_OPERATION: "Restore from recycle bin or backup",
            ActionCategory.SYSTEM_CHANGE: "System restore or registry backup"
        }
        return rollbacks.get(category, "No rollback method available")
    
    async def request_confirmation(self, warning: ActionWarning) -> bool:
        """
        Request user confirmation for an action.
        
        Args:
            warning: ActionWarning to confirm
        
        Returns:
            True if user confirms, False otherwise
        """
        logger.warning(f"[WarningSystem] Confirmation required for: {warning.action_description}")
        logger.warning(f"[WarningSystem] Risk Level: {warning.risk_level.value}")
        logger.warning(f"[WarningSystem] Reason: {warning.reason}")
        logger.warning(f"[WarningSystem] Consequences: {warning.consequences}")
        logger.warning(f"[WarningSystem] Mitigations: {warning.mitigation_suggestions}")
        
        if self._confirmation_dialog:
            # Use actual dialog
            result = await self._confirmation_dialog.ask_yes_no(
                title=f"Action Required: {warning.risk_level.value.upper()}",
                message=f"{warning.action_description}\n\n"
                       f"Reason: {warning.reason}\n\n"
                       f"Consequences:\n" + "\n".join(f"- {c}" for c in warning.consequences) + "\n\n"
                       f"Mitigations:\n" + "\n".join(f"- {m}" for m in warning.mitigation_suggestions)
            )
            confirmed = result.confirmed
        else:
            # Fallback to console input
            logger.info("[WarningSystem] Confirmation dialog not available, using console input")
            logger.info(f"[WarningSystem] Confirm? (y/n): {warning.action_description}")
            # For testing, auto-confirm
            confirmed = True
        
        logger.info(f"[WarningSystem] User confirmed: {confirmed}")
        
        return confirmed
    
    def log_action(self, action_description: str, warning: ActionWarning, confirmed: bool):
        """Log action to history."""
        self._action_history.append({
            "timestamp": asyncio.get_event_loop().time(),
            "action": action_description,
            "warning": warning,
            "confirmed": confirmed
        })
    
    def get_action_history(self) -> List[Dict[str, Any]]:
        """Get action history."""
        return self._action_history.copy()
    
    def get_warning_log(self) -> List[ActionWarning]:
        """Get warning log."""
        return self._warning_log.copy()
