"""Universal Code Automation Engine for Hojaiga.

Dedicated code generation and automation system that can handle:
- Tasks and assignments
- Website building
- Application development
- Any programming language
- Full code output (not just hints)

Separate from teaching - this is for actual production code.
"""
from __future__ import annotations

import os
import ast
import time
import json
import re
import tempfile
from pathlib import Path
from typing import Any, Optional, List, Dict, Tuple
from dataclasses import dataclass, field
from enum import Enum

try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False


class TaskType(Enum):
    """Types of code automation tasks."""
    WEB_DEVELOPMENT = "web_development"
    DESKTOP_APPLICATION = "desktop_application"
    MOBILE_APPLICATION = "mobile_application"
    DATA_PROCESSING = "data_processing"
    AUTOMATION_SCRIPT = "automation_script"
    GAME_DEVELOPMENT = "game_development"
    API_DEVELOPMENT = "api_development"
    DATABASE_DESIGN = "database_design"
    MACHINE_LEARNING = "machine_learning"
    ASSIGNMENT = "assignment"
    BUG_FIX = "bug_fix"
    REFACTOR = "refactor"
    FEATURE_ADD = "feature_add"


class CodeLanguage(Enum):
    """Supported programming languages for code automation."""
    PYTHON = "python"
    JAVASCRIPT = "javascript"
    TYPESCRIPT = "typescript"
    JAVA = "java"
    CSHARP = "csharp"
    CPP = "cpp"
    GO = "go"
    RUST = "rust"
    PHP = "php"
    RUBY = "ruby"
    SWIFT = "swift"
    KOTLIN = "kotlin"
    SQL = "sql"
    HTML = "html"
    CSS = "css"
    SHELL = "shell"
    POWER_SHELL = "powershell"
    R = "r"
    MATLAB = "matlab"
    LUA = "lua"
    DART = "dart"
    PERL = "perl"
    OBJECTIVEC = "objective-c"


class OutputFormat(Enum):
    """Output formats for generated code."""
    SINGLE_FILE = "single_file"
    MULTIPLE_FILES = "multiple_files"
    PROJECT_STRUCTURE = "project_structure"
    DIRECTORY = "directory"


@dataclass
class CodeTask:
    """Task specification for code automation."""
    task_type: TaskType
    description: str
    language: CodeLanguage
    output_format: OutputFormat
    requirements: List[str] = field(default_factory=list)
    file_path: Optional[str] = None
    context_code: Optional[str] = None
    additional_context: str = ""
    quality_level: str = "production"  # "basic", "intermediate", "production"


@dataclass
class CodeResult:
    """Result of code generation."""
    success: bool
    task_type: TaskType
    language: CodeLanguage
    code: str
    file_paths: List[str]
    processing_time_ms: float
    syntax_valid: bool
    syntax_error: Optional[str] = None
    error_message: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


class UniversalCodeAutomationEngine:
    """Universal code automation engine for Hojaiga.
    
    Generates complete production code for:
    - Tasks and assignments
    - Website building
    - Application development
    - Any programming language
    - Full code output (not just hints)
    """
    
    OLLAMA_URL = "http://127.0.0.1:11434/api/chat"
    LLAMA_7B_URL = "http://localhost:8081/v1/chat/completions"
    
    def __init__(self, preferred_backend: str = "ollama"):
        """
        Initialize code automation engine.
        
        Args:
            preferred_backend: "ollama" (faster) or "llama_7b" (smarter)
        """
        self.preferred_backend = preferred_backend
        self.task_history: List[CodeResult] = []
        self._check_backend_availability()
    
    def _check_backend_availability(self) -> None:
        """Check which backends are available."""
        self.backends_available = {}
        
        # Check Ollama
        try:
            resp = requests.get("http://127.0.0.1:11434/api/tags", timeout=5)
            self.backends_available["ollama"] = resp.status_code == 200
        except:
            self.backends_available["ollama"] = False
        
        # Check llama.cpp 7B
        try:
            resp = requests.get("http://localhost:8081", timeout=5)
            self.backends_available["llama_7b"] = resp.status_code == 200
        except:
            self.backends_available["llama_7b"] = False
    
    def generate_complete_code(self, task: CodeTask) -> CodeResult:
        """
        Generate complete production code for a task.
        
        Args:
            task: CodeTask with specifications
            
        Returns:
            CodeResult with generated code and metadata
        """
        start_time = time.time()
        
        try:
            # Build enhanced prompt for code generation
            prompt = self._build_code_generation_prompt(task)
            
            # Generate code using available backend
            code = self._generate_code_via_llm(prompt, task.language)
            
            if not code:
                return CodeResult(
                    success=False,
                    task_type=task.task_type,
                    language=task.language,
                    code="",
                    file_paths=[],
                    processing_time_ms=(time.time() - start_time) * 1000,
                    syntax_valid=False,
                    error_message="Failed to generate code"
                )
            
            # Validate syntax
            syntax_valid, syntax_error = self._validate_syntax(code, task.language)
            
            # Write to file if specified
            file_paths = []
            if task.file_path:
                file_paths = self._write_code_to_file(code, task.file_path, task.output_format)
            
            processing_time = (time.time() - start_time) * 1000
            
            result = CodeResult(
                success=True,
                task_type=task.task_type,
                language=task.language,
                code=code,
                file_paths=file_paths,
                processing_time_ms=processing_time,
                syntax_valid=syntax_valid,
                syntax_error=syntax_error,
                metadata={
                    "backend_used": self._get_active_backend(),
                    "quality_level": task.quality_level,
                    "file_count": len(file_paths)
                }
            )
            
            self.task_history.append(result)
            return result
            
        except Exception as e:
            return CodeResult(
                success=False,
                task_type=task.task_type,
                language=task.language,
                code="",
                file_paths=[],
                processing_time_ms=(time.time() - start_time) * 1000,
                syntax_valid=False,
                error_message=f"Code generation failed: {e}"
            )
    
    def _build_code_generation_prompt(self, task: CodeTask) -> str:
        """Build enhanced prompt for code generation."""
        base_prompt = f"""You are an elite autonomous code architect specialized in {task.language.value}.

TASK TYPE: {task.task_type.value}
QUALITY LEVEL: {task.quality_level.upper()}

REQUIREMENTS:
{chr(10).join(f"- {req}" for req in task.requirements)}

TASK DESCRIPTION:
{task.description}
"""
        
        if task.context_code:
            base_prompt += f"""

EXISTING CODE CONTEXT:
```{task.language.value}
{task.context_code}
```
"""
        
        if task.additional_context:
            base_prompt += f"""

ADDITIONAL CONTEXT:
{task.additional_context}
"""
        
        base_prompt += """

OUTPUT REQUIREMENTS:
- Return ONLY executable code inside code blocks
- Include all necessary imports
- Add comprehensive error handling
- Include type hints where appropriate
- Add docstrings for functions and classes
- Write production-grade, clean code
- Zero conversational fluff - just the code
- Include comments explaining complex sections
"""
        
        return base_prompt
    
    def _generate_code_via_llm(self, prompt: str, language: CodeLanguage) -> str:
        """Generate code using available LLM backend."""
        backend = self._get_active_backend()
        
        if backend == "ollama":
            return self._generate_via_ollama(prompt, language)
        elif backend == "llama_7b":
            return self._generate_via_llama_7b(prompt, language)
        else:
            raise Exception("No available backend")
    
    def _get_active_backend(self) -> str:
        """Get the active backend based on preference and availability."""
        if self.preferred_backend == "ollama" and self.backends_available.get("ollama"):
            return "ollama"
        elif self.backends_available.get("llama_7b"):
            return "llama_7b"
        elif self.backends_available.get("ollama"):
            return "ollama"
        else:
            raise Exception("No backend available")
    
    def _generate_via_ollama(self, prompt: str, language: CodeLanguage) -> str:
        """Generate code using Ollama."""
        model = "qwen2.5:3b"  # Fast and capable
        
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": "You are an elite code architect. Generate clean, production-grade code."},
                {"role": "user", "content": prompt}
            ],
            "stream": False,
            "options": {"temperature": 0.2, "num_predict": 2000}
        }
        
        try:
            resp = requests.post(self.OLLAMA_URL, json=payload, timeout=120.0)
            if resp.status_code != 200:
                raise Exception(f"Ollama HTTP {resp.status_code}")
            
            content = resp.json().get("message", {}).get("content", "")
            m = re.search(r"```(?:\w+)?\s*([\s\S]*?)\s*```", content)
            return m.group(1).strip() if m else content.strip()
            
        except Exception as e:
            raise Exception(f"Ollama generation failed: {e}")
    
    def _generate_via_llama_7b(self, prompt: str, language: CodeLanguage) -> str:
        """Generate code using llama.cpp 7B."""
        payload = {
            "model": "llama",
            "messages": [
                {"role": "system", "content": "You are an elite code architect. Generate clean, production-grade code."},
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.2,
            "max_tokens": 2000,
            "stream": False
        }
        
        try:
            resp = requests.post(self.LLAMA_7B_URL, json=payload, timeout=120.0)
            if resp.status_code != 200:
                raise Exception(f"llama.cpp HTTP {resp.status_code}")
            
            content = resp.json()["choices"][0]["message"]["content"]
            m = re.search(r"```(?:\w+)?\s*([\s\S]*?)\s*```", content)
            return m.group(1).strip() if m else content.strip()
            
        except Exception as e:
            raise Exception(f"llama.cpp generation failed: {e}")
    
    def _validate_syntax(self, code: str, language: CodeLanguage) -> Tuple[bool, Optional[str]]:
        """Validate code syntax."""
        if language in [CodeLanguage.PYTHON]:
            try:
                ast.parse(code)
                return True, None
            except SyntaxError as e:
                return False, str(e)
        # Add more language validators as needed
        return True, None
    
    def _write_code_to_file(self, code: str, file_path: str, output_format: OutputFormat) -> List[str]:
        """Write generated code to file(s)."""
        file_paths = []
        
        if output_format == OutputFormat.SINGLE_FILE:
            p = Path(file_path)
            p.parent.mkdir(parents=True, exist_ok=True)
            with open(p, "w", encoding="utf-8") as f:
                f.write(code)
            file_paths.append(str(p))
        
        elif output_format == OutputFormat.DIRECTORY:
            base_dir = Path(file_path)
            base_dir.mkdir(parents=True, exist_ok=True)
            
            # Parse multiple files from code (if in markdown format)
            file_blocks = re.findall(r"```[\w-]*\s*file:([^\n]+)\s*([\s\S]*?)```", code)
            
            if file_blocks:
                for filename, file_code in file_blocks:
                    file_p = base_dir / filename.strip()
                    file_p.parent.mkdir(parents=True, exist_ok=True)
                    with open(file_p, "w", encoding="utf-8") as f:
                        f.write(file_code.strip())
                    file_paths.append(str(file_p))
            else:
                # Single file fallback
                main_file = base_dir / f"main.{self._get_extension_from_language(language)}"
                with open(main_file, "w", encoding="utf-8") as f:
                    f.write(code)
                file_paths.append(str(main_file))
        
        return file_paths
    
    def _get_extension_from_language(self, language: CodeLanguage) -> str:
        """Get file extension for language."""
        extensions = {
            CodeLanguage.PYTHON: "py",
            CodeLanguage.JAVASCRIPT: "js",
            CodeLanguage.TYPESCRIPT: "ts",
            CodeLanguage.JAVA: "java",
            CodeLanguage.CSHARP: "cs",
            CodeLanguage.CPP: "cpp",
            CodeLanguage.GO: "go",
            CodeLanguage.RUST: "rs",
            CodeLanguage.PHP: "php",
            CodeLanguage.RUBY: "rb",
            CodeLanguage.SWIFT: "swift",
            CodeLanguage.KOTLIN: "kt",
            CodeLanguage.SQL: "sql",
            CodeLanguage.HTML: "html",
            CodeLanguage.CSS: "css",
            CodeLanguage.SHELL: "sh",
            CodeLanguage.POWER_SHELL: "ps1",
            CodeLanguage.R: "r",
            CodeLanguage.MATLAB: "m",
            CodeLanguage.LUA: "lua",
            CodeLanguage.DART: "dart",
            CodeLanguage.PERL: "pl",
            CodeLanguage.OBJECTIVEC: "m"
        }
        return extensions.get(language, "txt")
    
    # Convenience methods for common tasks
    def generate_website(self, description: str, language: CodeLanguage = CodeLanguage.HTML) -> CodeResult:
        """Generate complete website code."""
        task = CodeTask(
            task_type=TaskType.WEB_DEVELOPMENT,
            description=description,
            language=language,
            output_format=OutputFormat.SINGLE_FILE,
            requirements=[
                "Responsive design",
                "Modern UI/UX",
                "Clean code structure",
                "Semantic HTML",
                "Styling included"
            ]
        )
        return self.generate_complete_code(task)
    
    def generate_desktop_app(self, description: str, language: CodeLanguage = CodeLanguage.PYTHON) -> CodeResult:
        """Generate complete desktop application."""
        task = CodeTask(
            task_type=TaskType.DESKTOP_APPLICATION,
            description=description,
            language=language,
            output_format=OutputFormat.SINGLE_FILE,
            requirements=[
                "Complete application structure",
                "Main window and UI components",
                "Event handling",
                "Error handling",
                "Clean code organization"
            ]
        )
        return self.generate_complete_code(task)
    
    def solve_assignment(self, description: str, language: CodeLanguage = CodeLanguage.PYTHON, 
                       additional_context: str = "") -> CodeResult:
        """Solve programming assignment with complete code."""
        task = CodeTask(
            task_type=TaskType.ASSIGNMENT,
            description=description,
            language=language,
            output_format=OutputFormat.SINGLE_FILE,
            additional_context=additional_context,
            requirements=[
                "Complete solution",
                "Well-commented code",
                "Proper error handling",
                "Follow best practices",
                "Include necessary imports"
            ]
        )
        return self.generate_complete_code(task)
    
    def fix_bug(self, buggy_code: str, error_description: str, language: CodeLanguage = CodeLanguage.PYTHON) -> CodeResult:
        """Fix bug in existing code."""
        task = CodeTask(
            task_type=TaskType.BUG_FIX,
            description=f"Fix this bug: {error_description}",
            language=language,
            output_format=OutputFormat.SINGLE_FILE,
            context_code=buggy_code,
            requirements=[
                "Fix the reported bug",
                "Maintain existing functionality",
                "Add comments explaining the fix",
                "Ensure no new bugs introduced"
            ]
        )
        return self.generate_complete_code(task)
    
    def add_feature(self, existing_code: str, feature_description: str, language: CodeLanguage = CodeLanguage.PYTHON) -> CodeResult:
        """Add new feature to existing code."""
        task = CodeTask(
            task_type=TaskType.FEATURE_ADD,
            description=f"Add this feature: {feature_description}",
            language=language,
            output_format=OutputFormat.SINGLE_FILE,
            context_code=existing_code,
            requirements=[
                "Integrate new feature seamlessly",
                "Maintain existing functionality",
                "Add documentation for new feature",
                "Follow existing code style"
            ]
        )
        return self.generate_complete_code(task)
    
    def get_task_history(self) -> List[CodeResult]:
        """Get history of all code generation tasks."""
        return self.task_history.copy()
    
    def get_backend_status(self) -> Dict[str, Any]:
        """Get status of available backends."""
        return {
            "backends_available": self.backends_available,
            "preferred_backend": self.preferred_backend,
            "active_backend": self._get_active_backend(),
            "task_history_count": len(self.task_history)
        }


# Example usage
if __name__ == "__main__":
    engine = UniversalCodeAutomationEngine(preferred_backend="ollama")
    
    print("Backend status:", engine.get_backend_status())
    
    # Test code generation
    task = CodeTask(
        task_type=TaskType.WEB_DEVELOPMENT,
        description="Create a simple personal website with a hero section, about section, and contact form",
        language=Language.HTML,
        output_format=OutputFormat.SINGLE_FILE,
        requirements=["Responsive design", "Modern styling", "Clean HTML"]
    )
    
    result = engine.generate_complete_code(task)
    print("Success:", result.success)
    print("Syntax valid:", result.syntax_valid)
    print("Processing time:", result.processing_time_ms, "ms")
    print("Code length:", len(result.code))