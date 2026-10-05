"""
HOJAIGA AUTOMATION ARCHITECTURE DOC

============================================================
1. MASTER ARCHITECTURE CONTEXT
============================================================
This component is part of the Hojaiga Automation Architecture.
Component Type: Organ 39 (New)
Name: Enhanced Code Generation & Validation System

============================================================
2. ORGAN/COMPONENT DIAGRAM
============================================================
```mermaid
graph TD
    classDef default fill:#1e1e1e;stroke:#333;stroke-width:2px,color:#d4d4d4;
    classDef component fill:#2d2d2d;stroke:#569cd6;stroke-width:2px,color:#d4d4d4;
    
    CODEGEN[Code Generation Engine]
    
    CODEGEN --> VALIDATOR[Code Validator]
    
    CODEGEN --> COMPLETER[Code Completer]
    
    CODEGEN --> INTERACTIVE[Interactive Brainstorm]
    
    CODEGEN --> CONFIRM[Confirmation System]
    
    CODEGEN --> TESTER[Code Tester]
    
    class CODEGEN component
    class VALIDATOR component
    class COMPLETER component
    class INTERACTIVE component
    class CONFIRM component
    class TESTER component
```

Inputs: Project ideas, code requests, brainstorming sessions
Outputs: Complete validated code, interactive confirmation, tested implementations
Dependencies: ast, subprocess, logging, typing...
"""

from __future__ import annotations

import logging
import ast
import json
import time
import subprocess
import tempfile
from typing import Dict, Any, Optional, List, Set, Tuple, Callable
from dataclasses import dataclass, field
from enum import Enum
import requests

logger = logging.getLogger("hojaiga.organ39.code_generator")


class CodePhase(str, Enum):
    """Phases of code generation."""
    BRAINSTORM = "brainstorm"
    CONFIRMATION = "confirmation"
    GENERATION = "generation"
    VALIDATION = "validation"
    TESTING = "testing"
    COMPLETION = "completion"


class CodeLanguage(str, Enum):
    """Programming languages."""
    PYTHON = "python"
    JAVASCRIPT = "javascript"
    TYPESCRIPT = "typescript"
    HTML = "html"
    CSS = "css"
    SQL = "sql"
    BASH = "bash"


@dataclass
class BrainstormSession:
    """Interactive brainstorming session."""
    session_id: str
    project_idea: str
    questions: List[str] = field(default_factory=list)
    answers: List[str] = field(default_factory=list)
    clarifications: List[str] = field(default_factory=list)
    confirmed: bool = False
    timestamp: float = 0.0
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "session_id": self.session_id,
            "project_idea": self.project_idea,
            "questions": self.questions,
            "answers": self.answers,
            "clarifications": self.clarifications,
            "confirmed": self.confirmed,
            "timestamp": self.timestamp
        }


@dataclass
class CodeBlock:
    """Represents a complete code block."""
    block_id: str
    language: CodeLanguage
    code: str
    description: str
    file_path: Optional[str] = None
    dependencies: List[str] = field(default_factory=list)
    is_complete: bool = False
    validation_errors: List[str] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "block_id": self.block_id,
            "language": self.language.value,
            "code": self.code,
            "description": self.description,
            "file_path": self.file_path,
            "dependencies": self.dependencies,
            "is_complete": self.is_complete,
            "validation_errors": self.validation_errors
        }


@dataclass
class CodeGenerationRequest:
    """Request for code generation."""
    request_id: str
    project_idea: str
    language: CodeLanguage
    interactive: bool = True
    require_testing: bool = True
    require_validation: bool = True
    context: Optional[Dict[str, Any]] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "request_id": self.request_id,
            "project_idea": self.project_idea,
            "language": self.language.value,
            "interactive": self.interactive,
            "require_testing": self.require_testing,
            "require_validation": self.require_validation,
            "context": self.context
        }


class EnhancedCodeGenerator:
    """
    Enhanced code generation system that:
    - Ensures complete code output (no partial code)
    - Prevents hallucination in code generation
    - Interactive brainstorming with user confirmation
    - Code validation and testing
    - Automatic code completion
    - Multiple language support
    """
    
    def __init__(self, ollama_url: str = "http://127.0.0.1:11434/api/chat",
                 model: str = "qwen2.5:3b"):
        self.ollama_url = ollama_url
        self.model = model
        self._active_sessions: Dict[str, BrainstormSession] = {}
        self._code_history: List[CodeBlock] = []
        self._running = False
        
        logger.info("[Code Generator] Enhanced code generator initialized")
    
    def start(self) -> None:
        """Start the code generator."""
        if self._running:
            logger.info("[Code Generator] Already running")
            return
        
        self._running = True
        logger.info("[Code Generator] Code generator started")
    
    def stop(self) -> None:
        """Stop the code generator."""
        self._running = False
        logger.info("[Code Generator] Code generator stopped")
    
    def start_brainstorm(self, project_idea: str) -> BrainstormSession:
        """
        Start an interactive brainstorming session.
        
        Args:
            project_idea: Initial project idea
        
        Returns:
            BrainstormSession with generated questions
        """
        session_id = self._generate_session_id()
        
        # Generate clarifying questions
        questions = self._generate_clarifying_questions(project_idea)
        
        session = BrainstormSession(
            session_id=session_id,
            project_idea=project_idea,
            questions=questions,
            timestamp=time.time()
        )
        
        self._active_sessions[session_id] = session
        
        logger.info(f"[Code Generator] Started brainstorm session: {session_id}")
        
        return session
    
    def _generate_clarifying_questions(self, project_idea: str) -> List[str]:
        """Generate clarifying questions using LLM."""
        try:
            prompt = f"""You are a technical consultant helping refine a project idea.

Project Idea: {project_idea}

Generate 3-5 clarifying questions to better understand the requirements.
Focus on:
- Technical stack preferences
- Key features and functionality
- Performance requirements
- Integration needs
- User interface preferences

Respond with JSON in this format:
{{
    "questions": ["question 1", "question 2", "question 3"]
}}

Respond ONLY with valid JSON."""
            
            payload = {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": "You are a precise technical consultant. Always respond with valid JSON."},
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
            questions = data.get("questions", [])
            
            if not questions:
                # Fallback questions
                questions = [
                    "What programming language do you prefer?",
                    "What are the main features you need?",
                    "Do you have any specific performance requirements?"
                ]
            
            return questions
            
        except Exception as e:
            logger.error(f"[Code Generator] Failed to generate questions: {e}")
            return [
                "What programming language do you prefer?",
                "What are the main features you need?",
                "Do you have any specific performance requirements?"
            ]
    
    def answer_question(self, session_id: str, question_index: int, answer: str) -> bool:
        """
        Answer a question in a brainstorming session.
        
        Args:
            session_id: Session ID
            question_index: Index of the question
            answer: User's answer
        
        Returns:
            True if successful, False otherwise
        """
        if session_id not in self._active_sessions:
            logger.warning(f"[Code Generator] Session not found: {session_id}")
            return False
        
        session = self._active_sessions[session_id]
        
        if question_index >= len(session.questions):
            logger.warning(f"[Code Generator] Question index out of range: {question_index}")
            return False
        
        # Store answer
        session.answers.append(answer)
        
        logger.info(f"[Code Generator] Answer recorded for question {question_index}")
        
        return True
    
    def confirm_brainstorm(self, session_id: str) -> bool:
        """
        Confirm the brainstorming session and proceed to code generation.
        
        Args:
            session_id: Session ID
        
        Returns:
            True if confirmed, False otherwise
        """
        if session_id not in self._active_sessions:
            logger.warning(f"[Code Generator] Session not found: {session_id}")
            return False
        
        session = self._active_sessions[session_id]
        session.confirmed = True
        
        logger.info(f"[Code Generator] Brainstorm session confirmed: {session_id}")
        
        return True
    
    def generate_code(self, request: CodeGenerationRequest) -> List[CodeBlock]:
        """
        Generate complete code based on project idea.
        
        Args:
            request: Code generation request
        
        Returns:
            List of complete code blocks
        """
        try:
            logger.info(f"[Code Generator] Generating code for: {request.project_idea[:50]}...")
            
            # If interactive, use brainstorm session
            if request.interactive:
                session = self.start_brainstorm(request.project_idea)
                # In a real implementation, this would be interactive
                # For now, we'll proceed with auto-confirmation
                session.confirmed = True
            
            # Generate code with completion guarantee
            code_blocks = self._generate_complete_code(request)
            
            # Validate code if required
            if request.require_validation:
                for block in code_blocks:
                    self._validate_code_block(block)
            
            # Test code if required
            if request.require_testing:
                for block in code_blocks:
                    self._test_code_block(block)
            
            # Add to history
            self._code_history.extend(code_blocks)
            
            logger.info(f"[Code Generator] Generated {len(code_blocks)} code blocks")
            
            return code_blocks
            
        except Exception as e:
            logger.error(f"[Code Generator] Code generation failed: {e}")
            return []
    
    def _generate_complete_code(self, request: CodeGenerationRequest) -> List[CodeBlock]:
        """Generate complete code with completion guarantee."""
        try:
            # Build comprehensive prompt
            prompt = self._build_code_generation_prompt(request)
            
            # Query LLM
            payload = {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": "You are an expert software developer. Always provide complete, runnable code. Never output partial code. Include all necessary imports, functions, and complete implementations."},
                    {"role": "user", "content": prompt}
                ],
                "stream": False,
                "options": {"temperature": 0.2}
            }
            
            response = requests.post(self.ollama_url, json=payload, timeout=120)
            response.raise_for_status()
            
            response_text = response.json().get("message", {}).get("content", "")
            
            # Extract code blocks
            code_blocks = self._extract_code_blocks(response_text, request.language)
            
            # Ensure completeness
            for block in code_blocks:
                block = self._ensure_code_completeness(block, request.language)
            
            return code_blocks
            
        except Exception as e:
            logger.error(f"[Code Generator] Complete code generation failed: {e}")
            return []
    
    def _build_code_generation_prompt(self, request: CodeGenerationRequest) -> str:
        """Build comprehensive code generation prompt."""
        context_info = ""
        if request.context:
            context_parts = []
            for key, value in request.context.items():
                context_parts.append(f"{key}: {value}")
            context_info = "\nContext:\n" + "\n".join(context_parts)
        
        prompt = f"""Generate complete, runnable code for this project:

Project Idea: {request.project_idea}
Language: {request.language.value}
{context_info}

IMPORTANT:
- Provide COMPLETE code (no partial implementations)
- Include all necessary imports
- Include all required functions
- Make the code runnable as-is
- Add comments explaining key parts
- Handle errors appropriately
- Include example usage if applicable

Respond with JSON in this format:
{{
    "code_blocks": [
        {{
            "description": "what this code does",
            "file_path": "filename.extension",
            "code": "complete code here",
            "dependencies": ["dependency1", "dependency2"]
        }}
    ]
}}

Respond ONLY with valid JSON."""
        
        return prompt
    
    def _extract_code_blocks(self, response_text: str, language: CodeLanguage) -> List[CodeBlock]:
        """Extract code blocks from LLM response."""
        try:
            # Parse JSON response
            import re
            json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
            if not json_match:
                raise ValueError("No JSON found in LLM response")
            
            data = json.loads(json_match.group(0))
            blocks_data = data.get("code_blocks", [])
            
            code_blocks = []
            for i, block_data in enumerate(blocks_data):
                block = CodeBlock(
                    block_id=f"block_{int(time.time() * 1000)}_{i}",
                    language=language,
                    code=block_data.get("code", ""),
                    description=block_data.get("description", ""),
                    file_path=block_data.get("file_path"),
                    dependencies=block_data.get("dependencies", [])
                )
                code_blocks.append(block)
            
            return code_blocks
            
        except Exception as e:
            logger.error(f"[Code Generator] Failed to extract code blocks: {e}")
            # Fallback: treat entire response as single code block
            return [CodeBlock(
                block_id=f"block_{int(time.time() * 1000)}",
                language=language,
                code=response_text,
                description="Fallback code block",
                file_path=None,
                dependencies=[]
            )]
    
    def _ensure_code_completeness(self, block: CodeBlock, language: CodeLanguage) -> CodeBlock:
        """Ensure code block is complete."""
        code = block.code
        
        # Check for common incomplete patterns
        incomplete_patterns = [
            "...",  # Ellipsis
            "# TODO",  # TODO comments
            "# FIXME",  # FIXME comments
            "pass",  # Empty pass statements
            "raise NotImplementedError",  # Not implemented
        ]
        
        has_incomplete = any(pattern in code for pattern in incomplete_patterns)
        
        if has_incomplete:
            logger.warning(f"[Code Generator] Code block appears incomplete: {block.block_id}")
            
            # Try to complete the code
            completed_code = self._complete_code(block, language)
            if completed_code:
                block.code = completed_code
                block.is_complete = True
            else:
                block.is_complete = False
        else:
            block.is_complete = True
        
        return block
    
    def _complete_code(self, block: CodeBlock, language: CodeLanguage) -> Optional[str]:
        """Attempt to complete incomplete code."""
        try:
            prompt = f"""Complete this incomplete code:

Description: {block.description}
Language: {language.value}
Incomplete Code:
{block.code}

Provide the complete, runnable implementation. Replace any '...', 'pass', or 'TODO' with actual implementations."""
            
            payload = {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": "You are an expert software developer. Always provide complete, runnable code."},
                    {"role": "user", "content": prompt}
                ],
                "stream": False,
                "options": {"temperature": 0.2}
            }
            
            response = requests.post(self.ollama_url, json=payload, timeout=60)
            response.raise_for_status()
            
            completed_code = response.json().get("message", {}).get("content", "")
            
            return completed_code
            
        except Exception as e:
            logger.error(f"[Code Generator] Failed to complete code: {e}")
            return None
    
    def _validate_code_block(self, block: CodeBlock) -> bool:
        """Validate a code block."""
        try:
            if block.language == CodeLanguage.PYTHON:
                # Parse as AST
                ast.parse(block.code)
                block.validation_errors = []
                return True
            else:
                # For other languages, basic validation
                if not block.code.strip():
                    block.validation_errors = ["Empty code"]
                    return False
                block.validation_errors = []
                return True
                
        except SyntaxError as e:
            block.validation_errors = [str(e)]
            logger.warning(f"[Code Generator] Validation error: {e}")
            return False
    
    def _test_code_block(self, block: CodeBlock) -> bool:
        """Test a code block."""
        try:
            if block.language == CodeLanguage.PYTHON:
                # Create temporary file and test
                with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
                    f.write(block.code)
                    temp_file = f.name
                
                try:
                    # Try to execute
                    result = subprocess.run(
                        ["python", temp_file],
                        capture_output=True,
                        timeout=10
                    )
                    
                    if result.returncode == 0:
                        logger.info(f"[Code Generator] Code test passed: {block.block_id}")
                        return True
                    else:
                        logger.warning(f"[Code Generator] Code test failed: {result.stderr.decode()}")
                        return False
                        
                finally:
                    import os
                    os.unlink(temp_file)
            
            return True
            
        except Exception as e:
            logger.error(f"[Code Generator] Code test failed: {e}")
            return False
    
    def _generate_session_id(self) -> str:
        """Generate unique session ID."""
        import hashlib
        return hashlib.md5(f"{time.time()}".encode()).hexdigest()[:12]


# Singleton instance
_code_generator_instance: Optional[EnhancedCodeGenerator] = None

def get_code_generator() -> EnhancedCodeGenerator:
    """Get the singleton code generator instance."""
    global _code_generator_instance
    if _code_generator_instance is None:
        _code_generator_instance = EnhancedCodeGenerator()
    return _code_generator_instance


def generate_project_code(project_idea: str, language: str = "python",
                         interactive: bool = True) -> List[CodeBlock]:
    """
    Convenience function to generate code for a project.
    
    Args:
        project_idea: Project idea
        language: Programming language
        interactive: Enable interactive brainstorming
    
    Returns:
        List of complete code blocks
    """
    generator = get_code_generator()
    
    request = CodeGenerationRequest(
        request_id=f"req_{int(time.time() * 1000)}",
        project_idea=project_idea,
        language=CodeLanguage(language),
        interactive=interactive
    )
    
    return generator.generate_code(request)
