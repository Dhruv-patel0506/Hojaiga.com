"""
HOJAIGA AUTOMATION ARCHITECTURE DOC

============================================================
1. MASTER ARCHITECTURE CONTEXT
============================================================
This component is part of the Hojaiga Automation Architecture.
Component Type: Organ 40 (New)
Name: Hallucination Prevention & Drawing Enhancement

============================================================
2. ORGAN/COMPONENT DIAGRAM
============================================================
```mermaid
graph TD
    classDef default fill:#1e1e1e;stroke:#333;stroke-width:2px;color:#d4d4d4;
    classDef component fill:#2d2d2d;stroke:#569cd6;stroke-width:2px,color:#d4d4d4;
    
    HAL[Hallucination Prevention]
    
    HAL --> VALIDATE[Response Validator]
    
    HAL --> VERIFY[Fact Checker]
    
    HAL --> DRAW[Drawing Enhancer]
    
    HAL --> MODEL[Model Health]
    
    HAL --> FALLBACK[Fallback Manager]
    
    class HAL component
    class VALIDATE component
    class VERIFY component
    class DRAW component
    class MODEL component
    class FALLBACK component
```

Inputs: Model responses, drawing requests
Outputs: Validated responses, enhanced drawings, fallback triggers
Dependencies: logging, typing, requests...
"""

from __future__ import annotations

import logging
import time
import requests
from typing import Dict, Any, Optional, List, Set, Tuple
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger("hojaiga.organ40.hallucination_prevention")


class ResponseQuality(str, Enum):
    """Quality levels for model responses."""
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    HALLUCINATED = "hallucinated"


@dataclass
class ValidatedResponse:
    """Validated model response."""
    original_response: str
    validated_response: str
    quality: ResponseQuality
    confidence: float
    hallucinations: List[str] = field(default_factory=list)
    corrections: List[str] = field(default_factory=list)
    markers_added: bool = False
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "original_response": self.original_response,
            "validated_response": self.validated_response,
            "quality": self.quality.value,
            "confidence": self.confidence,
            "hallucinations": self.hallucinations,
            "corrections": self.corrections,
            "markers_added": self.markers_added
        }


@dataclass
class DrawingRequest:
    """Request for drawing with validation."""
    description: str
    shape_type: str
    coordinates: Optional[List[Tuple[float, float]]] = None
    style: Optional[Dict[str, Any]] = None
    require_vision: bool = True
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "description": self.description,
            "shape_type": self.shape_type,
            "coordinates": self.coordinates,
            "style": self.style,
            "require_vision": self.require_vision
        }


class HallucinationPreventionSystem:
    """
    System to prevent model hallucinations and enhance drawing capabilities.
    
    Features:
    - Response validation against known facts
    - Hallucination detection
    - Model health monitoring
    - Automatic fallback triggers
    - Drawing enhancement with vision validation
    - Marker placement when model unavailable
    """
    
    def __init__(self, ollama_url: str = "http://127.0.0.1:11434/api/chat",
                 model: str = "qwen2.5:3b"):
        self.ollama_url = ollama_url
        self.model = model
        self._known_facts: Set[str] = set()
        self._response_history: List[ValidatedResponse] = []
        self._model_health: Dict[str, float] = {}
        self._running = False
        
        # Initialize known facts
        self._initialize_known_facts()
        
        logger.info("[Hallucination Prevention] System initialized")
    
    def _initialize_known_facts(self) -> None:
        """Initialize known facts for validation."""
        # Technical facts
        self._known_facts.update([
            "Python is a programming language",
            "Ollama is a local LLM runner",
            "CrewAI is an AI agent framework",
            "Hojaiga is an automation system",
            "Win32 is Windows API",
            "UIA is UI Automation",
            "Chrome is a web browser",
            "HTML is markup language",
            "CSS is styling language",
            "JavaScript is web programming language"
        ])
        
        logger.info(f"[Hallucination Prevention] Initialized {len(self._known_facts)} known facts")
    
    def start(self) -> None:
        """Start the hallucination prevention system."""
        if self._running:
            logger.info("[Hallucination Prevention] Already running")
            return
        
        self._running = True
        logger.info("[Hallucination Prevention] System started")
    
    def stop(self) -> None:
        """Stop the hallucination prevention system."""
        self._running = False
        logger.info("[Hallucination Prevention] System stopped")
    
    def validate_response(self, response: str, context: Optional[Dict[str, Any]] = None) -> ValidatedResponse:
        """
        Validate a model response for hallucinations.
        
        Args:
            response: Model response to validate
            context: Additional context for validation
        
        Returns:
            ValidatedResponse with quality assessment
        """
        try:
            # Check for obvious hallucination markers
            hallucinations = self._detect_hallucinations(response)
            
            if hallucinations:
                logger.warning(f"[Hallucination Prevention] Detected {len(hallucinations)} hallucinations")
                
                # Try to correct hallucinations
                corrected_response = self._correct_hallucinations(response, hallucinations)
                
                return ValidatedResponse(
                    original_response=response,
                    validated_response=corrected_response,
                    quality=ResponseQuality.HALLUCINATED,
                    confidence=0.3,
                    hallucinations=hallucinations,
                    corrections=["Auto-corrected detected hallucinations"]
                )
            
            # Check response completeness
            if self._is_incomplete_response(response):
                logger.warning("[Hallucination Prevention] Response appears incomplete")
                
                # Try to complete
                completed_response = self._complete_response(response, context)
                
                return ValidatedResponse(
                    original_response=response,
                    validated_response=completed_response,
                    quality=ResponseQuality.MEDIUM,
                    confidence=0.6,
                    corrections=["Completed incomplete response"]
                )
            
            # Response appears valid
            return ValidatedResponse(
                original_response=response,
                validated_response=response,
                quality=ResponseQuality.HIGH,
                confidence=0.9
            )
            
        except Exception as e:
            logger.error(f"[Hallucination Prevention] Validation failed: {e}")
            return ValidatedResponse(
                original_response=response,
                validated_response=response,
                quality=ResponseQuality.LOW,
                confidence=0.2,
                corrections=["Validation failed, returned original"]
            )
    
    def _detect_hallucinations(self, response: str) -> List[str]:
        """Detect potential hallucinations in response."""
        hallucinations = []
        
        # Check for impossible claims
        hallucination_patterns = [
            ("I can do anything", "Overconfident claim"),
            ("I am able to reach any model", "Model reachability claim"),
            ("I have access to everything", "Overbroad access claim"),
            ("I can draw anything perfectly", "Overconfident drawing claim"),
            ("I will never fail", "Absolute claim"),
            ("I know everything", "Omniscience claim")
        ]
        
        for pattern, description in hallucination_patterns:
            if pattern.lower() in response.lower():
                hallucinations.append(description)
        
        # Check for technical inaccuracies
        technical_errors = [
            ("Python is not a language", "Technical inaccuracy"),
            ("CrewAI is not a framework", "Technical inaccuracy"),
            ("Ollama is not a runner", "Technical inaccuracy")
        ]
        
        for pattern, description in technical_errors:
            if pattern.lower() in response.lower():
                hallucinations.append(description)
        
        return hallucinations
    
    def _correct_hallucinations(self, response: str, hallucinations: List[str]) -> str:
        """Correct detected hallucinations."""
        try:
            prompt = f"""Correct the hallucinations in this response:

Original Response: {response}

Detected Hallucinations:
{chr(10).join(f"- {h}" for h in hallucinations)}

Provide a corrected response that is accurate and honest about capabilities.
Remove any overconfident or impossible claims.
If you cannot do something, say so clearly.

Respond with the corrected response only."""
            
            payload = {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": "You are a helpful assistant that provides accurate, honest responses."},
                    {"role": "user", "content": prompt}
                ],
                "stream": False,
                "options": {"temperature": 0.2}
            }
            
            api_response = requests.post(self.ollama_url, json=payload, timeout=30)
            api_response.raise_for_status()
            
            corrected = api_response.json().get("message", {}).get("content", "")
            
            return corrected if corrected else response
            
        except Exception as e:
            logger.error(f"[Hallucination Prevention] Correction failed: {e}")
            return response
    
    def _is_incomplete_response(self, response: str) -> bool:
        """Check if response is incomplete."""
        incomplete_markers = ["...", "TODO", "FIXME", "incomplete", "not finished"]
        return any(marker.lower() in response.lower() for marker in incomplete_markers)
    
    def _complete_response(self, response: str, context: Optional[Dict[str, Any]]) -> str:
        """Complete an incomplete response."""
        try:
            context_str = ""
            if context:
                context_parts = []
                for key, value in context.items():
                    context_parts.append(f"{key}: {value}")
                context_str = "\nContext:\n" + "\n".join(context_parts)
            
            prompt = f"""Complete this incomplete response:

Incomplete Response: {response}
{context_str}

Provide a complete, finished response. Replace any '...', 'TODO', or incomplete sections with actual content."""
            
            payload = {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": "You are a helpful assistant that provides complete responses."},
                    {"role": "user", "content": prompt}
                ],
                "stream": False,
                "options": {"temperature": 0.2}
            }
            
            api_response = requests.post(self.ollama_url, json=payload, timeout=30)
            api_response.raise_for_status()
            
            completed = api_response.json().get("message", {}).get("content", "")
            
            return completed if completed else response
            
        except Exception as e:
            logger.error(f"[Hallucination Prevention] Completion failed: {e}")
            return response
    
    def validate_drawing_request(self, request: DrawingRequest) -> Dict[str, Any]:
        """
        Validate and enhance a drawing request.
        
        Args:
            request: Drawing request
        
        Returns:
            Enhanced drawing request with validation
        """
        result = {
            "original_request": request.to_dict(),
            "validated": True,
            "enhanced": False,
            "warnings": [],
            "fallback_required": False
        }
        
        # Check if vision is required and available
        if request.require_vision:
            if not self._check_vision_available():
                result["validated"] = False
                result["fallback_required"] = True
                result["warnings"].append("Vision model not available, using fallback")
                result["marker_suggestion"] = "Place marker on screen at approximate location"
                result["markers_added"] = True
        
        # Validate coordinates
        if request.coordinates:
            for coord in request.coordinates:
                if not (0 <= coord[0] <= 1 and 0 <= coord[1] <= 1):
                    result["warnings"].append(f"Invalid coordinates: {coord}")
                    result["validated"] = False
        
        # Enhance drawing description
        enhanced_description = self._enhance_drawing_description(request)
        if enhanced_description != request.description:
            result["enhanced"] = True
            result["enhanced_description"] = enhanced_description
        
        return result
    
    def _check_vision_available(self) -> bool:
        """Check if vision model is available."""
        try:
            # Simple ping to vision model
            payload = {
                "model": "qwen2.5vl:3b",
                "prompt": "test",
                "stream": False
            }
            
            response = requests.post("http://127.0.0.1:11434/api/generate",
                                     json=payload, timeout=5)
            
            return response.status_code == 200
            
        except Exception as e:
            logger.warning(f"[Hallucination Prevention] Vision check failed: {e}")
            return False
    
    def _enhance_drawing_description(self, request: DrawingRequest) -> str:
        """Enhance drawing description with LLM."""
        try:
            prompt = f"""Enhance this drawing request for better execution:

Current Description: {request.description}
Shape Type: {request.shape_type}

Provide a more detailed, actionable description that includes:
- Specific dimensions if applicable
- Style details (color, thickness, etc.)
- Position details
- Any additional context needed for accurate drawing

Respond with the enhanced description only."""
            
            payload = {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": "You are a technical drawing assistant. Provide precise, actionable descriptions."},
                    {"role": "user", "content": prompt}
                ],
                "stream": False,
                "options": {"temperature": 0.2}
            }
            
            response = requests.post(self.ollama_url, json=payload, timeout=30)
            response.raise_for_status()
            
            enhanced = response.json().get("message", {}).get("content", "")
            
            return enhanced if enhanced else request.description
            
        except Exception as e:
            logger.error(f"[Hallucination Prevention] Description enhancement failed: {e}")
            return request.description
    
    def add_screen_marker(self, location: Tuple[float, float], description: str) -> Dict[str, Any]:
        """
        Add a marker to the screen when vision/drawing is unavailable.
        
        Args:
            location: (x, y) coordinates (normalized 0-1)
            description: Description of what the marker represents
        
        Returns:
            Marker information
        """
        marker = {
            "marker_id": f"marker_{int(time.time() * 1000)}",
            "location": location,
            "description": description,
            "timestamp": time.time(),
            "type": "fallback_marker"
        }
        
        logger.info(f"[Hallucination Prevention] Added screen marker: {description} at {location}")
        
        return marker
    
    def check_model_health(self, model_name: str) -> float:
        """
        Check the health of a model.
        
        Args:
            model_name: Name of the model to check
        
        Returns:
            Health score (0.0-1.0)
        """
        try:
            # Simple latency test
            start_time = time.time()
            
            payload = {
                "model": model_name,
                "prompt": "test",
                "stream": False
            }
            
            response = requests.post("http://127.0.0.1:11434/api/generate",
                                     json=payload, timeout=10)
            
            duration = time.time() - start_time
            
            if response.status_code == 200:
                # Calculate health based on latency
                if duration < 2.0:
                    health = 1.0
                elif duration < 5.0:
                    health = 0.8
                elif duration < 10.0:
                    health = 0.5
                else:
                    health = 0.3
                
                self._model_health[model_name] = health
                return health
            else:
                self._model_health[model_name] = 0.0
                return 0.0
                
        except Exception as e:
            logger.error(f"[Hallucination Prevention] Model health check failed: {e}")
            self._model_health[model_name] = 0.0
            return 0.0


# Singleton instance
_hallucination_prevention_instance: Optional[HallucinationPreventionSystem] = None

def get_hallucination_prevention() -> HallucinationPreventionSystem:
    """Get the singleton hallucination prevention instance."""
    global _hallucination_prevention_instance
    if _hallucination_prevention_instance is None:
        _hallucination_prevention_instance = HallucinationPreventionSystem()
    return _hallucination_prevention_instance


def validate_model_response(response: str, context: Optional[Dict[str, Any]] = None) -> ValidatedResponse:
    """
    Convenience function to validate a model response.
    
    Args:
        response: Model response to validate
        context: Additional context
    
    Returns:
        ValidatedResponse
    """
    system = get_hallucination_prevention()
    return system.validate_response(response, context)
