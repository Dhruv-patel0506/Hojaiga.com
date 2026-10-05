"""
HOJAIGA AUTOMATION ARCHITECTURE DOC

============================================================
1. MASTER ARCHITECTURE CONTEXT
============================================================
This component is part of the Hojaiga Automation Architecture.
Component Type: Organ 11
Name: Context-Aware Search Engine

============================================================
2. ORGAN/COMPONENT DIAGRAM
============================================================
```mermaid
graph TD
    classDef default fill:#1e1e1e,stroke:#333,stroke-width:2px,color:#d4d4d4;
    classDef component fill:#2d2d2d,stroke:#569cd6,stroke-width:2px,color:#d4d4d4;
    
    INPUT[Task Context]
    
    INPUT --> QUERY_GEN[LLM Query Generator]
    
    QUERY_GEN --> SEARCH[Web Search Engine]
    
    SEARCH --> FILTER[Context Filter]
    
    FILTER --> OUTPUT[Relevant Results]
    
    class QUERY_GEN component
    class SEARCH component
    class FILTER component
```

Inputs: Task context, user intent
Outputs: Contextually relevant search results
Dependencies: requests, logging, typing...
"""

from __future__ import annotations

import logging
import json
import requests
from typing import Dict, Any, Optional, List
from dataclasses import dataclass
from enum import Enum
import time

logger = logging.getLogger("hojaiga.organ11.context_aware_search")


class SearchSource(str, Enum):
    GOOGLE = "google"
    DUCKDUCKGO = "duckduckgo"
    BING = "bing"
    WIKIPEDIA = "wikipedia"
    STACKOVERFLOW = "stackoverflow"


@dataclass
class SearchResult:
    """Represents a single search result with relevance scoring."""
    title: str
    url: str
    snippet: str
    relevance_score: float
    source: SearchSource
    timestamp: float
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "title": self.title,
            "url": self.url,
            "snippet": self.snippet,
            "relevance_score": self.relevance_score,
            "source": self.source.value,
            "timestamp": self.timestamp
        }


@dataclass
class SearchQuery:
    """Represents a generated search query with context."""
    query: str
    reasoning: str
    expected_result_type: str
    priority: int = 1


class ContextAwareSearchEngine:
    """
    Context-aware web search engine that uses LLM to generate intelligent queries
    based on task context and filters results for relevance.
    """
    
    def __init__(self, ollama_url: str = "http://127.0.0.1:11434/api/chat", 
                 model: str = "llama3"):
        self.ollama_url = ollama_url
        self.model = model
        self.search_history: List[Dict[str, Any]] = []
        
    def search(self, task_description: str, context: Optional[Dict[str, Any]] = None,
              max_results: int = 10, sources: Optional[List[SearchSource]] = None) -> List[SearchResult]:
        """
        Perform context-aware search based on task description.
        
        Args:
            task_description: Natural language task description
            context: Additional context (app names, constraints, etc.)
            max_results: Maximum number of results to return
            sources: Specific search sources to use (None = all)
        
        Returns:
            List of SearchResult with relevance scores
        """
        try:
            # Step 1: Generate intelligent search queries using LLM
            queries = self._generate_search_queries(task_description, context)
            
            # Step 2: Execute searches across sources
            all_results = []
            for query in queries:
                query_results = self._execute_search(query, sources or [SearchSource.GOOGLE])
                all_results.extend(query_results)
            
            # Step 3: Filter and rank by relevance
            filtered_results = self._filter_by_relevance(all_results, task_description, context)
            
            # Step 4: Return top results
            top_results = filtered_results[:max_results]
            
            # Log to history
            self.search_history.append({
                "task": task_description,
                "context": context,
                "queries": [q.query for q in queries],
                "results_count": len(top_results),
                "timestamp": time.time()
            })
            
            logger.info(f"[Context Search] Generated {len(queries)} queries, found {len(top_results)} relevant results")
            
            return top_results
            
        except Exception as e:
            logger.error(f"[Context Search] Search failed: {e}")
            return []
    
    def _generate_search_queries(self, task_description: str, 
                                 context: Optional[Dict[str, Any]]) -> List[SearchQuery]:
        """Use LLM to generate intelligent search queries based on task context."""
        try:
            context_str = ""
            if context:
                context_parts = []
                for key, value in context.items():
                    context_parts.append(f"{key}: {value}")
                context_str = "\nContext:\n" + "\n".join(context_parts)
            
            prompt = f"""You are an expert search query generator for the Hojaiga automation system.
Your job is to generate specific, targeted search queries based on a task description.

Task Description:
{task_description}
{context_str}

Generate 3-5 specific search queries that would help accomplish this task.
Each query should be specific enough to find actionable information.

Respond with JSON in this exact format:
{{
    "queries": [
        {{
            "query": "specific search query",
            "reasoning": "why this query is relevant",
            "expected_result_type": "what type of information this should find"
        }}
    ]
}}

Respond ONLY with valid JSON."""
            
            payload = {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": "You are a precise search query generator. Always respond with valid JSON."},
                    {"role": "user", "content": prompt}
                ],
                "stream": False,
                "options": {"temperature": 0.3}
            }
            
            response = requests.post(self.ollama_url, json=payload, timeout=30)
            response.raise_for_status()
            
            response_text = response.json().get("message", {}).get("content", "")
            
            # Parse JSON response
            import re
            json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
            if not json_match:
                raise ValueError("No JSON found in LLM response")
            
            data = json.loads(json_match.group(0))
            queries_data = data.get("queries", [])
            
            queries = []
            for q_data in queries_data:
                queries.append(SearchQuery(
                    query=q_data.get("query", ""),
                    reasoning=q_data.get("reasoning", ""),
                    expected_result_type=q_data.get("expected_result_type", ""),
                    priority=1
                ))
            
            return queries
            
        except Exception as e:
            logger.error(f"[Context Search] Query generation failed: {e}, using fallback")
            return self._fallback_query_generation(task_description)
    
    def _fallback_query_generation(self, task_description: str) -> List[SearchQuery]:
        """Fallback to simple query extraction if LLM fails."""
        # Extract key terms from task description
        import re
        words = re.findall(r'\b[a-zA-Z]{3,}\b', task_description)
        key_terms = [w for w in words if len(w) > 3][:5]
        
        if not key_terms:
            key_terms = ["automation", "task"]
        
        query = " ".join(key_terms)
        
        return [SearchQuery(
            query=query,
            reasoning="Fallback query extracted from task description",
            expected_result_type="general information",
            priority=1
        )]
    
    def _execute_search(self, query: SearchQuery, sources: List[SearchSource]) -> List[SearchResult]:
        """Execute search query across specified sources."""
        results = []
        
        for source in sources:
            try:
                if source == SearchSource.GOOGLE:
                    results.extend(self._search_google(query))
                elif source == SearchSource.DUCKDUCKGO:
                    results.extend(self._search_duckduckgo(query))
                elif source == SearchSource.WIKIPEDIA:
                    results.extend(self._search_wikipedia(query))
                # Add more sources as needed
            except Exception as e:
                logger.warning(f"[Context Search] {source.value} search failed: {e}")
        
        return results
    
    def _search_google(self, query: SearchQuery) -> List[SearchResult]:
        """Search using Google Custom Search API or DuckDuckGo as fallback."""
        # For now, use DuckDuckGo as a free alternative
        return self._search_duckduckgo(query)
    
    def _search_duckduckgo(self, query: SearchQuery) -> List[SearchResult]:
        """Search using DuckDuckGo Instant Answer API."""
        try:
            url = f"https://api.duckduckgo.com/"
            params = {
                "q": query.query,
                "format": "json"
            }
            
            response = requests.get(url, params=params, timeout=10)
            response.raise_for_status()
            
            data = response.json()
            
            results = []
            
            # Extract related topics
            for topic in data.get("RelatedTopics", [])[:5]:
                if isinstance(topic, dict) and "Text" in topic and "FirstURL" in topic:
                    results.append(SearchResult(
                        title=topic.get("Text", ""),
                        url=topic.get("FirstURL", ""),
                        snippet=topic.get("Text", ""),
                        relevance_score=0.7,
                        source=SearchSource.DUCKDUCKGO,
                        timestamp=time.time()
                    ))
            
            return results
            
        except Exception as e:
            logger.error(f"[Context Search] DuckDuckGo search failed: {e}")
            return []
    
    def _search_wikipedia(self, query: SearchQuery) -> List[SearchResult]:
        """Search using Wikipedia API."""
        try:
            url = "https://en.wikipedia.org/w/api.php"
            params = {
                "action": "query",
                "list": "search",
                "srsearch": query.query,
                "format": "json",
                "utf8": "",
                "srlimit": 5
            }
            
            response = requests.get(url, params=params, timeout=10)
            response.raise_for_status()
            
            data = response.json()
            
            results = []
            for item in data.get("query", {}).get("search", []):
                results.append(SearchResult(
                    title=item.get("title", ""),
                    url=f"https://en.wikipedia.org/wiki/{item.get('title', '').replace(' ', '_')}",
                    snippet=item.get("snippet", ""),
                    relevance_score=0.8,
                    source=SearchSource.WIKIPEDIA,
                    timestamp=time.time()
                ))
            
            return results
            
        except Exception as e:
            logger.error(f"[Context Search] Wikipedia search failed: {e}")
            return []
    
    def _filter_by_relevance(self, results: List[SearchResult], task_description: str,
                           context: Optional[Dict[str, Any]]) -> List[SearchResult]:
        """Filter and rank results by relevance using LLM."""
        if not results:
            return results
        
        try:
            # Use LLM to score relevance
            task_lower = task_description.lower()
            
            for result in results:
                # Basic keyword matching for initial scoring
                result_title_lower = result.title.lower()
                result_snippet_lower = result.snippet.lower()
                
                score = 0.5  # Base score
                
                # Check for keyword matches
                task_words = set(task_lower.split())
                title_words = set(result_title_lower.split())
                snippet_words = set(result_snippet_lower.split())
                
                title_matches = len(task_words & title_words)
                snippet_matches = len(task_words & snippet_words)
                
                score += (title_matches * 0.1) + (snippet_matches * 0.05)
                
                # Boost for certain sources
                if result.source == SearchSource.WIKIPEDIA:
                    score += 0.1
                
                result.relevance_score = min(1.0, score)
            
            # Sort by relevance
            results.sort(key=lambda r: r.relevance_score, reverse=True)
            
            return results
            
        except Exception as e:
            logger.error(f"[Context Search] Relevance filtering failed: {e}")
            return results


# Singleton instance
_search_engine_instance: Optional[ContextAwareSearchEngine] = None

def get_context_search_engine() -> ContextAwareSearchEngine:
    """Get the singleton context search engine instance."""
    global _search_engine_instance
    if _search_engine_instance is None:
        _search_engine_instance = ContextAwareSearchEngine()
    return _search_engine_instance


def perform_context_search(task_description: str, context: Optional[Dict[str, Any]] = None,
                          max_results: int = 10) -> List[SearchResult]:
    """
    Convenience function to perform context-aware search.
    
    Args:
        task_description: Natural language task description
        context: Optional additional context
        max_results: Maximum number of results
    
    Returns:
        List of SearchResult
    """
    engine = get_context_search_engine()
    return engine.search(task_description, context, max_results)
