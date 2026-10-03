"""Universal coding and logic tutor with six-step teaching flow.

Implements model code as editable artifact with file, language, line ranges,
diagnostics, and execution state. Provides Socratic tutoring with hint levels
and preserves user code with clear approval workflows.
"""
from __future__ import annotations

import ast
import tempfile
import subprocess
import os
import time
from dataclasses import dataclass, field
from typing import Any, Optional, List, Dict, Tuple
from enum import Enum
from pathlib import Path


class TutorState(Enum):
    """Six-step tutor flow states."""
    UNDERSTAND_GOAL = "understand_goal"
    CLARIFY_CONSTRAINTS = "clarify_constraints"
    DRAW_PLAN = "draw_plan"
    INSPECT_CODE = "inspect_code"
    GIVE_HINT = "give_hint"
    SHOW_SOLUTION = "show_solution"


class HintLevel(Enum):
    """User-selected hint levels for progressive disclosure."""
    NUDGE = "nudge"  # Minimal guidance
    GUIDED_STEPS = "guided_steps"  # Step-by-step guidance
    PSEUDOCODE = "pseudocode"  # Algorithmic structure
    PARTIAL_FIX = "partial_fix"  # Partial solution
    FULL_SOLUTION = "full_solution"  # Complete solution


class Language(Enum):
    """Supported programming languages."""
    PYTHON = "python"
    JAVASCRIPT = "javascript"
    JAVA = "java"
    CPP = "cpp"
    CSHARP = "csharp"
    GO = "go"
    RUST = "rust"
    TYPESCRIPT = "typescript"


@dataclass
class CodeArtifact:
    """Editable code artifact with full metadata."""
    file_path: str
    language: Language
    content: str
    line_ranges: List[Tuple[int, int]]  # Active line ranges
    diagnostics: List[Dict[str, Any]]  # Language server diagnostics
    execution_state: Dict[str, Any]  # Execution results, state
    last_modified: float = field(default_factory=time.time)
    version: int = 1
    
    def get_selected_lines(self) -> str:
        """Get content of selected line ranges."""
        lines = self.content.split('\n')
        selected = []
        for start, end in self.line_ranges:
            selected.extend(lines[start-1:end])  # 1-indexed to 0-indexed
        return '\n'.join(selected)
    
    def update_content(self, new_content: str, approval: bool = False) -> bool:
        """Update content with approval check."""
        if not approval:
            return False
        
        self.content = new_content
        self.last_modified = time.time()
        self.version += 1
        return True


@dataclass
class TutorStep:
    """A single step in the tutoring process."""
    state: TutorState
    timestamp: float
    user_input: str
    system_response: str
    hint_level: HintLevel
    code_changes: Optional[CodeArtifact] = None
    visual_aids: List[Dict[str, Any]] = field(default_factory=list)
    execution_results: Optional[Dict[str, Any]] = None


@dataclass
class TutorSession:
    """Complete tutoring session with history."""
    goal: str
    language: Language
    initial_code: str
    steps: List[TutorStep] = field(default_factory=list)
    current_state: TutorState = TutorState.UNDERSTAND_GOAL
    hint_level: HintLevel = HintLevel.GUIDED_STEPS
    code_artifact: Optional[CodeArtifact] = None
    start_time: float = field(default_factory=time.time)
    
    def add_step(self, step: TutorStep) -> None:
        """Add a step to the session history."""
        self.steps.append(step)
        self.current_state = step.state


class ASTAnalyzer:
    """AST parsing and language-server diagnostics for code analysis."""
    
    def __init__(self):
        self.supported_languages = {
            Language.PYTHON: self._analyze_python,
            Language.JAVASCRIPT: self._analyze_javascript,
        }
    
    def analyze(self, code: str, language: Language) -> List[Dict[str, Any]]:
        """Analyze code and return diagnostics."""
        analyzer = self.supported_languages.get(language)
        if analyzer:
            return analyzer(code)
        return []
    
    def _analyze_python(self, code: str) -> List[Dict[str, Any]]:
        """Analyze Python code using AST."""
        diagnostics = []
        
        try:
            tree = ast.parse(code)
            
            # Check for common issues
            for node in ast.walk(tree):
                # Detect unused imports
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        if not self._is_import_used(tree, alias.name):
                            diagnostics.append({
                                "type": "warning",
                                "message": f"Unused import: {alias.name}",
                                "line": node.lineno,
                                "severity": "low"
                            })
                
                # Detect TODO comments
                if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant):
                    if isinstance(node.value.value, str) and "TODO" in node.value.value:
                        diagnostics.append({
                            "type": "info",
                            "message": "TODO comment found",
                            "line": node.lineno,
                            "severity": "info"
                        })
        
        except SyntaxError as e:
            diagnostics.append({
                "type": "error",
                "message": f"Syntax error: {e.msg}",
                "line": e.lineno,
                "severity": "high"
            })
        
        return diagnostics
    
    def _analyze_javascript(self, code: str) -> List[Dict[str, Any]]:
        """Analyze JavaScript code (simplified)."""
        diagnostics = []
        
        # Basic syntax checks
        if "function" in code and "{" in code and "}" not in code:
            diagnostics.append({
                "type": "error",
                "message": "Unclosed function brace",
                "line": 0,
                "severity": "high"
            })
        
        return diagnostics
    
    def _is_import_used(self, tree: ast.AST, import_name: str) -> bool:
        """Check if an import is actually used in the code."""
        base_name = import_name.split('.')[0]
        for node in ast.walk(tree):
            if isinstance(node, ast.Name) and node.id == base_name:
                return True
            if isinstance(node, ast.Attribute) and node.attr == base_name:
                return True
        return False


class CodeExecutor:
    """Safe code execution with result capture."""
    
    def __init__(self):
        self.execution_timeout = 10  # seconds
        self.temp_dir = tempfile.mkdtemp()
    
    def execute(self, code: str, language: Language) -> Dict[str, Any]:
        """Execute code and return results."""
        if language == Language.PYTHON:
            return self._execute_python(code)
        else:
            return {"success": False, "error": f"Execution not supported for {language.value}"}
    
    def _execute_python(self, code: str) -> Dict[str, Any]:
        """Execute Python code safely."""
        try:
            # Create temporary file
            temp_file = os.path.join(self.temp_dir, "temp_exec.py")
            with open(temp_file, 'w') as f:
                f.write(code)
            
            # Execute with timeout
            result = subprocess.run(
                ["python", temp_file],
                capture_output=True,
                text=True,
                timeout=self.execution_timeout
            )
            
            return {
                "success": result.returncode == 0,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "returncode": result.returncode
            }
        
        except subprocess.TimeoutExpired:
            return {"success": False, "error": "Execution timeout"}
        except Exception as e:
            return {"success": False, "error": str(e)}


class VisualAidGenerator:
    """Generate visual aids for code understanding."""
    
    def __init__(self):
        self.diagram_types = {
            "control_flow": self._generate_control_flow,
            "data_flow": self._generate_data_flow,
            "memory_state": self._generate_memory_state,
            "recursion": self._generate_recursion_tree,
            "api_structure": self._generate_api_structure,
            "architecture": self._generate_architecture
        }
    
    def generate_aid(self, aid_type: str, code: str, language: Language) -> Dict[str, Any]:
        """Generate a visual aid for code understanding."""
        generator = self.diagram_types.get(aid_type)
        if generator:
            return generator(code, language)
        return {"type": "unknown", "data": {}}
    
    def _generate_control_flow(self, code: str, language: Language) -> Dict[str, Any]:
        """Generate control flow diagram."""
        # Simplified control flow extraction
        if language == Language.PYTHON:
            try:
                tree = ast.parse(code)
                nodes = []
                edges = []
                
                for i, node in enumerate(tree.body):
                    node_id = f"node_{i}"
                    node_type = type(node).__name__
                    nodes.append({"id": node_id, "label": node_type})
                    
                    if i > 0:
                        edges.append({"from": f"node_{i-1}", "to": node_id, "label": "next"})
                
                return {
                    "type": "control_flow",
                    "nodes": nodes,
                    "edges": edges
                }
            except:
                pass
        
        return {"type": "control_flow", "nodes": [], "edges": []}
    
    def _generate_data_flow(self, code: str, language: Language) -> Dict[str, Any]:
        """Generate data flow diagram."""
        return {"type": "data_flow", "nodes": [], "edges": []}
    
    def _generate_memory_state(self, code: str, language: Language) -> Dict[str, Any]:
        """Generate memory state visualization."""
        return {"type": "memory_state", "variables": []}
    
    def _generate_recursion_tree(self, code: str, language: Language) -> Dict[str, Any]:
        """Generate recursion tree visualization."""
        return {"type": "recursion_tree", "nodes": [], "edges": []}
    
    def _generate_api_structure(self, code: str, language: Language) -> Dict[str, Any]:
        """Generate API structure diagram."""
        return {"type": "api_structure", "endpoints": []}
    
    def _generate_architecture(self, code: str, language: Language) -> Dict[str, Any]:
        """Generate system architecture diagram."""
        return {"type": "architecture", "components": []}


class UniversalCodeTutor:
    """Universal coding and logic tutor with six-step flow."""
    
    def __init__(self):
        self.ast_analyzer = ASTAnalyzer()
        self.code_executor = CodeExecutor()
        self.visual_aid_generator = VisualAidGenerator()
        self.current_session: Optional[TutorSession] = None
    
    def start_session(self, goal: str, language: Language, initial_code: str = "") -> TutorSession:
        """Start a new tutoring session."""
        self.current_session = TutorSession(
            goal=goal,
            language=language,
            initial_code=initial_code
        )
        
        # Create code artifact
        if initial_code:
            self.current_session.code_artifact = CodeArtifact(
                file_path="untitled",
                language=language,
                content=initial_code,
                line_ranges=[(1, len(initial_code.split('\n')))],
                diagnostics=[],
                execution_state={}
            )
        
        return self.current_session
    
    def process_step(self, user_input: str, hint_level: Optional[HintLevel] = None) -> TutorStep:
        """Process the current tutoring step."""
        if not self.current_session:
            raise ValueError("No active session")
        
        if hint_level:
            self.current_session.hint_level = hint_level
        
        current_state = self.current_session.current_state
        step = self._execute_state_machine(current_state, user_input)
        
        self.current_session.add_step(step)
        return step
    
    def _execute_state_machine(self, state: TutorState, user_input: str) -> TutorStep:
        """Execute the current state of the tutoring state machine."""
        if state == TutorState.UNDERSTAND_GOAL:
            return self._understand_goal(user_input)
        elif state == TutorState.CLARIFY_CONSTRAINTS:
            return self._clarify_constraints(user_input)
        elif state == TutorState.DRAW_PLAN:
            return self._draw_plan(user_input)
        elif state == TutorState.INSPECT_CODE:
            return self._inspect_code(user_input)
        elif state == TutorState.GIVE_HINT:
            return self._give_hint(user_input)
        elif state == TutorState.SHOW_SOLUTION:
            return self._show_solution(user_input)
        else:
            raise ValueError(f"Unknown state: {state}")
    
    def _understand_goal(self, user_input: str) -> TutorStep:
        """Step 1: Understand the user's goal."""
        response = f"I understand you want to: {self.current_session.goal}. Let me clarify a few things to help you better."
        
        return TutorStep(
            state=TutorState.CLARIFY_CONSTRAINTS,
            timestamp=time.time(),
            user_input=user_input,
            system_response=response,
            hint_level=self.current_session.hint_level
        )
    
    def _clarify_constraints(self, user_input: str) -> TutorStep:
        """Step 2: Clarify constraints and requirements."""
        response = "What are the specific constraints or requirements for this task? (e.g., time complexity, space limits, specific libraries)"
        
        return TutorStep(
            state=TutorState.DRAW_PLAN,
            timestamp=time.time(),
            user_input=user_input,
            system_response=response,
            hint_level=self.current_session.hint_level
        )
    
    def _draw_plan(self, user_input: str) -> TutorStep:
        """Step 3: Draw optional plan with visual aids."""
        response = "Here's a plan for approaching this problem:"
        
        # Generate visual aids
        visual_aids = []
        if self.current_session.code_artifact:
            control_flow = self.visual_aid_generator.generate_aid(
                "control_flow",
                self.current_session.code_artifact.content,
                self.current_session.language
            )
            visual_aids.append(control_flow)
        
        return TutorStep(
            state=TutorState.INSPECT_CODE,
            timestamp=time.time(),
            user_input=user_input,
            system_response=response,
            hint_level=self.current_session.hint_level,
            visual_aids=visual_aids
        )
    
    def _inspect_code(self, user_input: str) -> TutorStep:
        """Step 4: Inspect code with AST analysis and diagnostics."""
        if not self.current_session.code_artifact:
            response = "Please provide the code you'd like me to inspect."
            return TutorStep(
                state=TutorState.INSPECT_CODE,
                timestamp=time.time(),
                user_input=user_input,
                system_response=response,
                hint_level=self.current_session.hint_level
            )
        
        # Analyze code
        diagnostics = self.ast_analyzer.analyze(
            self.current_session.code_artifact.content,
            self.current_session.language
        )
        
        # Update diagnostics
        self.current_session.code_artifact.diagnostics = diagnostics
        
        response = f"I've analyzed your code and found {len(diagnostics)} items to discuss. "
        if diagnostics:
            response += f"Main issues: {[d['message'] for d in diagnostics[:3]]}"
        else:
            response += "The code looks syntactically correct!"
        
        return TutorStep(
            state=TutorState.GIVE_HINT,
            timestamp=time.time(),
            user_input=user_input,
            system_response=response,
            hint_level=self.current_session.hint_level
        )
    
    def _give_hint(self, user_input: str) -> TutorStep:
        """Step 5: Give hint based on selected hint level."""
        hint_level = self.current_session.hint_level
        response = ""
        
        if hint_level == HintLevel.NUDGE:
            response = "Consider the data structure you're using. Is there a more efficient approach?"
        elif hint_level == HintLevel.GUIDED_STEPS:
            response = "Step 1: Initialize your variables. Step 2: Set up your loop structure. Step 3: Handle edge cases."
        elif hint_level == HintLevel.PSEUDOCODE:
            response = """
            ```
            function solve(input):
                initialize result
                for each element in input:
                    process element
                    update result
                return result
            ```
            """
        elif hint_level == HintLevel.PARTIAL_FIX:
            response = "Here's a partial fix for the main issue: [specific code suggestion]"
        elif hint_level == HintLevel.FULL_SOLUTION:
            response = "Would you like me to show you the complete solution?"
        
        return TutorStep(
            state=TutorState.SHOW_SOLUTION if hint_level == HintLevel.FULL_SOLUTION else TutorState.GIVE_HINT,
            timestamp=time.time(),
            user_input=user_input,
            system_response=response,
            hint_level=hint_level
        )
    
    def _show_solution(self, user_input: str) -> TutorStep:
        """Step 6: Show solution only when requested."""
        response = "Here's the complete solution with explanations. Please review and let me know if you have questions."
        
        # Execute code to show results
        execution_results = None
        if self.current_session.code_artifact:
            execution_results = self.code_executor.execute(
                self.current_session.code_artifact.content,
                self.current_session.language
            )
        
        return TutorStep(
            state=TutorState.UNDERSTAND_GOAL,  # Cycle back
            timestamp=time.time(),
            user_input=user_input,
            system_response=response,
            hint_level=self.current_session.hint_level,
            execution_results=execution_results
        )
    
    def complete_incomplete_code(self, incomplete_code: str, language: Language) -> str:
        """Complete incomplete code using pattern matching and AST analysis."""
        try:
            if language == Language.PYTHON:
                lines = incomplete_code.split('\n')
                completed_lines = lines.copy()
                modified = False
                
                # Check for incomplete structures (lines ending with colon but no body)
                for i, line in enumerate(lines):
                    stripped = line.strip()
                    if stripped.endswith(':'):
                        # Check if next line exists and is indented
                        if i + 1 >= len(lines) or not lines[i + 1].strip():
                            completed_lines.append('    pass  # TODO: implement')
                            modified = True
                            break
                
                # Check for lines that should have colons but don't
                if not modified:
                    for i, line in enumerate(lines):
                        stripped = line.strip()
                        if any(keyword in stripped for keyword in ['for ', 'while ', 'if ', 'else:', 'def ', 'class ', 'try:', 'except']):
                            if ':' not in line:
                                completed_lines[i] = line.rstrip() + ':'
                                completed_lines.append('    pass  # TODO: implement')
                                modified = True
                                break
                
                if modified:
                    return '\n'.join(completed_lines)
                
        except Exception as e:
            print(f"[CodeTutor] Code completion failed: {e}")
        
        return incomplete_code  # Return original if can't complete
    
    def get_session_summary(self) -> Dict[str, Any]:
        """Get summary of current session."""
        if not self.current_session:
            return {"status": "no_active_session"}
        
        return {
            "goal": self.current_session.goal,
            "language": self.current_session.language.value,
            "current_state": self.current_session.current_state.value,
            "hint_level": self.current_session.hint_level.value,
            "steps_completed": len(self.current_session.steps),
            "session_duration": time.time() - self.current_session.start_time,
            "has_code_artifact": self.current_session.code_artifact is not None
        }
    
    def highlight_code_ranges(self, ranges: List[Tuple[int, int]]) -> Dict[str, Any]:
        """Highlight specific code ranges for visual focus."""
        if not self.current_session or not self.current_session.code_artifact:
            return {"error": "no_code_artifact"}
        
        self.current_session.code_artifact.line_ranges = ranges
        
        return {
            "success": True,
            "highlighted_ranges": ranges,
            "selected_content": self.current_session.code_artifact.get_selected_lines()
        }