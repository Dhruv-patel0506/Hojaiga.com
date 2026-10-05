"""
HOJAIGA AUTOMATION ARCHITECTURE DOC

============================================================
1. MASTER ARCHITECTURE CONTEXT
============================================================
This component is part of the Hojaiga Automation Architecture.
Component Type: Organ 10 Enhancement
Name: LLM-Based Agent Paradigm Classifier

============================================================
2. ORGAN/COMPONENT DIAGRAM
============================================================
```mermaid
graph TD
    classDef default fill:#1e1e1e,stroke:#333,stroke-width:2px,color:#d4d4d4;
    classDef component fill:#2d2d2d,stroke:#569cd6,stroke-width:2px,color:#d4d4d4;
    
    INPUT[User Task Description]
    
    INPUT --> CLASSIFIER
    
    subgraph COMPONENT [LLM Paradigm Classifier]
        direction TB
        LLM[Local LLM Classification]
        PARADIGM_MAP[Paradigm Mapping]
        CONFIDENCE[Confidence Scoring]
    end
    
    COMPONENT --> OUTPUT[Assigned Paradigm]
    
    class COMPONENT component;
```

Inputs: User task descriptions
Outputs: Agent paradigm assignments with confidence scores
Dependencies: requests, logging, typing...
"""

from __future__ import annotations

import logging
import json
import requests
from typing import Dict, Any, Optional, List
from enum import Enum

logger = logging.getLogger("hojaiga.organ10.llm_paradigm_classifier")


class AgentParadigm(str, Enum):
    PARALLEL_WEB_AUTOMATION = "parallel_web_automation"
    AGENT_CHATROOM = "agent_chatroom"
    STOCHASTIC_CONSENSUS = "stochastic_consensus"
    VERIFICATION_LOOP = "verification_loop"
    VIDEO_TO_ACTION = "video_to_action"
    DETERMINISTIC_LEAD_GEN = "deterministic_lead_gen"
    RESEARCH_AND_WRITE = "research_and_write"


class ParadigmClassificationResult:
    def __init__(self, paradigm: AgentParadigm, confidence: float, reasoning: str):
        self.paradigm = paradigm
        self.confidence = confidence
        self.reasoning = reasoning
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "paradigm": self.paradigm.value,
            "confidence": self.confidence,
            "reasoning": self.reasoning
        }


class LLMParadigmClassifier:
    """
    Uses local LLM to intelligently classify tasks into the 7 Hojaiga agent paradigms.
    Replaces simplistic keyword matching with true intent understanding.
    """
    
    def __init__(self, ollama_url: str = "http://127.0.0.1:11434/api/chat", 
                 model: str = "llama3"):
        self.ollama_url = ollama_url
        self.model = model
        
        # Paradigm descriptions for LLM classification
        self.paradigm_descriptions = {
            AgentParadigm.PARALLEL_WEB_AUTOMATION: 
                "Multi-browser concurrent web automation tasks, scraping multiple websites, "
                "parallel browsing, web research across multiple tabs",
            
            AgentParadigm.AGENT_CHATROOM:
                "Multi-agent discussion, debate, dialogue, conversation, collaborative decision making",
            
            AgentParadigm.STOCHASTIC_CONSENSUS:
                "Voting-based decision making, evaluating options, multi-perspective analysis, "
                "reaching consensus through multiple agents",
            
            AgentParadigm.VERIFICATION_LOOP:
                "Audit, verify, check, inspect, validate, quality assurance, compliance checking",
            
            AgentParadigm.VIDEO_TO_ACTION:
                "Video processing, screen recording, stream analysis, video transcript extraction, "
                "video-to-action conversion",
            
            AgentParadigm.DETERMINISTIC_LEAD_GEN:
                "Structured lead generation, data extraction, directory scraping, business contact gathering",
            
            AgentParadigm.RESEARCH_AND_WRITE:
                "Content generation, documentation, research, writing, analysis, knowledge synthesis"
        }
    
    def classify(self, task_description: str, context: Optional[Dict[str, Any]] = None) -> ParadigmClassificationResult:
        """
        Classify a task into the most appropriate agent paradigm using LLM.
        
        Args:
            task_description: Natural language description of the task
            context: Additional context (app names, constraints, etc.)
        
        Returns:
            ParadigmClassificationResult with paradigm, confidence, and reasoning
        """
        try:
            # Build classification prompt
            prompt = self._build_classification_prompt(task_description, context)
            
            # Query LLM
            response = self._query_llm(prompt)
            
            # Parse response
            result = self._parse_classification_response(response)
            
            logger.info(f"[LLM Classifier] Task: '{task_description[:50]}...' -> Paradigm: {result.paradigm.value} (confidence: {result.confidence:.2f})")
            
            return result
            
        except Exception as e:
            logger.error(f"[LLM Classifier] Classification failed: {e}, falling back to keyword matching")
            return self._fallback_classification(task_description)
    
    def _build_classification_prompt(self, task_description: str, context: Optional[Dict[str, Any]]) -> str:
        """Build the classification prompt for the LLM."""
        
        context_str = ""
        if context:
            context_parts = []
            for key, value in context.items():
                context_parts.append(f"{key}: {value}")
            context_str = "Additional Context:\n" + "\n".join(context_parts) + "\n"
        
        # Build paradigm descriptions
        paradigm_descriptions = "\n".join([
            f"{p.value}: {desc}" for p, desc in self.paradigm_descriptions.items()
        ])
        
        prompt = f"""You are an expert task classifier for the Hojaiga automation system. 
Your job is to classify tasks into the most appropriate agent paradigm.

Available Paradigms:
{paradigm_descriptions}

Task Description:
{task_description}

{context_str}

Respond with JSON in this exact format:
{{
    "paradigm": "paradigm_name",
    "confidence": 0.0-1.0,
    "reasoning": "brief explanation of why this paradigm fits"
}}

Choose the single best paradigm and respond ONLY with valid JSON."""
        
        return prompt
    
    def _query_llm(self, prompt: str) -> str:
        """Query the local LLM for classification."""
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": "You are a precise task classifier. Always respond with valid JSON."},
                {"role": "user", "content": prompt}
            ],
            "stream": False,
            "options": {"temperature": 0.1}
        }
        
        response = requests.post(self.ollama_url, json=payload, timeout=30)
        response.raise_for_status()
        
        return response.json().get("message", {}).get("content", "")
    
    def _parse_classification_response(self, response: str) -> ParadigmClassificationResult:
        """Parse the LLM response into a classification result."""
        try:
            # Extract JSON from response
            import re
            json_match = re.search(r'\{.*\}', response, re.DOTALL)
            if not json_match:
                raise ValueError("No JSON found in response")
            
            data = json.loads(json_match.group(0))
            
            paradigm_str = data.get("paradigm", "research_and_write")
            confidence = float(data.get("confidence", 0.5))
            reasoning = data.get("reasoning", "No reasoning provided")
            
            # Validate paradigm
            try:
                paradigm = AgentParadigm(paradigm_str)
            except ValueError:
                logger.warning(f"[LLM Classifier] Unknown paradigm '{paradigm_str}', defaulting to RESEARCH_AND_WRITE")
                paradigm = AgentParadigm.RESEARCH_AND_WRITE
            
            return ParadigmClassificationResult(paradigm, confidence, reasoning)
            
        except Exception as e:
            logger.error(f"[LLM Classifier] Failed to parse response: {e}")
            raise
    
    def _fallback_classification(self, task_description: str) -> ParadigmClassificationResult:
        """Fallback to keyword-based classification if LLM fails."""
        task_lower = task_description.lower()
        
        # Simple keyword fallback
        if any(k in task_lower for k in ["video", "record", "stream", "screen record"]):
            return ParadigmClassificationResult(AgentParadigm.VIDEO_TO_ACTION, 0.6, "Keyword fallback: video-related")
        elif any(k in task_lower for k in ["verify", "audit", "check", "inspect"]):
            return ParadigmClassificationResult(AgentParadigm.VERIFICATION_LOOP, 0.6, "Keyword fallback: verification-related")
        elif any(k in task_lower for k in ["browser", "web", "http", "chrome", "scrape", "navigate"]):
            return ParadigmClassificationResult(AgentParadigm.PARALLEL_WEB_AUTOMATION, 0.6, "Keyword fallback: web-related")
        elif any(k in task_lower for k in ["lead", "extract", "scrape", "directory", "business"]):
            return ParadigmClassificationResult(AgentParadigm.DETERMINISTIC_LEAD_GEN, 0.6, "Keyword fallback: lead generation")
        elif any(k in task_lower for k in ["chat", "discuss", "debate", "converse"]):
            return ParadigmClassificationResult(AgentParadigm.AGENT_CHATROOM, 0.6, "Keyword fallback: conversation-related")
        elif any(k in task_lower for k in ["consensus", "voting", "evaluate"]):
            return ParadigmClassificationResult(AgentParadigm.STOCHASTIC_CONSENSUS, 0.6, "Keyword fallback: consensus-related")
        else:
            return ParadigmClassificationResult(AgentParadigm.RESEARCH_AND_WRITE, 0.5, "Keyword fallback: default")


# Singleton instance
_classifier_instance: Optional[LLMParadigmClassifier] = None

def get_paradigm_classifier() -> LLMParadigmClassifier:
    """Get the singleton paradigm classifier instance."""
    global _classifier_instance
    if _classifier_instance is None:
        _classifier_instance = LLMParadigmClassifier()
    return _classifier_instance


def classify_task_paradigm(task_description: str, context: Optional[Dict[str, Any]] = None) -> ParadigmClassificationResult:
    """
    Convenience function to classify a task into a paradigm.
    
    Args:
        task_description: Natural language task description
        context: Optional additional context
    
    Returns:
        ParadigmClassificationResult
    """
    classifier = get_paradigm_classifier()
    return classifier.classify(task_description, context)
