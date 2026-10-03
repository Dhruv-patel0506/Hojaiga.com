"""
HOJAIGA AUTOMATION ARCHITECTURE DOC

============================================================
1. MASTER ARCHITECTURE CONTEXT
============================================================
This component is part of the Hojaiga Automation Architecture.
Component Type: Organ 13 (New)
Name: ScrapeGraphAI Integration

============================================================
2. ORGAN/COMPONENT DIAGRAM
============================================================
```mermaid
graph TD
    classDef default fill:#1e1e1e;stroke:#333;stroke-width:2px,color:#d4d4d4;
    classDef component fill:#2d2d2d;stroke:#569cd6;stroke-width:2px,color:#d4d4d4;
    
    SCRAPE[ScrapeGraphAI Integration]
    
    SCRAPE --> PIPELINE[Scraping Pipeline]
    
    SCRAPE --> GRAPHS[Graph Logic]
    
    SCRAPE --> EXTRACTION[Multi-Column Extraction]
    
    SCRAPE --> QUALITY[Quality Assessment]
    
    SCRAPE --> VALIDATION[Data Validation]
    
    class SCRAPE component
    class PIPELINE component
    class GRAPHS component
    class EXTRACTION component
    class QUALITY component
    class VALIDATION component
```

Inputs: URLs, scraping requests, data schemas
Outputs: Structured multi-column data with quality metrics
Dependencies: scrapegraphai, logging, typing, pandas...
"""

from __future__ import annotations

import logging
import json
import time
from typing import Dict, Any, Optional, List, Set, Tuple
from dataclasses import dataclass, field
from enum import Enum
import pandas as pd

logger = logging.getLogger("hojaiga.organ13.scrapegraphai")

# Soft import for ScrapeGraphAI
try:
    from scrapegraphai.graphs import SmartScraperGraph, SearchGraph, ScraperGraph
    from scrapegraphai.nodes import FetchNode, ParseNode, GenerateAnswerNode
    _HAS_SCRAPEGRAPHAI = True
except ImportError:
    _HAS_SCRAPEGRAPHAI = False
    logger.warning("[ScrapeGraphAI] ScrapeGraphAI not installed. Install with: pip install scrapegraphai")


class ScrapingStrategy(str, Enum):
    """Strategies for web scraping."""
    SMART_SCRAPER = "smart_scraper"  # AI-powered intelligent scraping
    SEARCH_GRAPH = "search_graph"  # Search and extract
    BASIC_SCRAPER = "basic_scraper"  # Simple scraping
    CUSTOM_GRAPH = "custom_graph"  # Custom graph logic


class DataQuality(str, Enum):
    """Quality levels for scraped data."""
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    UNKNOWN = "unknown"


@dataclass
class ScrapingRequest:
    """Request for web scraping."""
    url: str
    strategy: ScrapingStrategy
    schema: Optional[Dict[str, Any]] = None
    columns: Optional[List[str]] = None
    quality_threshold: DataQuality = DataQuality.MEDIUM
    max_pages: int = 10
    follow_links: bool = True
    extract_images: bool = False
    extract_links: bool = True
    description: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "url": self.url,
            "strategy": self.strategy.value,
            "schema": self.schema,
            "columns": self.columns,
            "quality_threshold": self.quality_threshold.value,
            "max_pages": self.max_pages,
            "follow_links": self.follow_links,
            "extract_images": self.extract_images,
            "extract_links": self.extract_links,
            "description": self.description
        }


@dataclass
class ScrapingResult:
    """Result from web scraping."""
    request_id: str
    url: str
    success: bool
    data: Optional[pd.DataFrame] = None
    raw_data: Optional[List[Dict[str, Any]]] = None
    quality_score: float = 0.0
    quality_level: DataQuality = DataQuality.UNKNOWN
    pages_scraped: int = 0
    extraction_time_sec: float = 0.0
    error_message: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "request_id": self.request_id,
            "url": self.url,
            "success": self.success,
            "data": self.data.to_dict() if self.data is not None else None,
            "raw_data": self.raw_data,
            "quality_score": self.quality_score,
            "quality_level": self.quality_level.value,
            "pages_scraped": self.pages_scraped,
            "extraction_time_sec": self.extraction_time_sec,
            "error_message": self.error_message,
            "metadata": self.metadata
        }


class ScrapeGraphAIIntegration:
    """
    Integration of ScrapeGraphAI for advanced web scraping.
    
    Features:
    - Multi-column data extraction
    - Quality assessment
    - Graph-based scraping logic
    - AI-powered intelligent extraction
    - Follow links and pagination
    - Data validation
    """
    
    def __init__(self, ollama_url: str = "http://127.0.0.1:11434"):
        self.ollama_url = ollama_url
        self._running = False
        self._scraping_history: List[ScrapingResult] = []
        
        if not _HAS_SCRAPEGRAPHAI:
            logger.error("[ScrapeGraphAI] ScrapeGraphAI not available. Install with: pip install scrapegraphai")
            return
        
        logger.info("[ScrapeGraphAI] ScrapeGraphAI integration initialized")
    
    def start(self) -> None:
        """Start the ScrapeGraphAI integration."""
        if self._running:
            logger.info("[ScrapeGraphAI] Already running")
            return
        
        if not _HAS_SCRAPEGRAPHAI:
            logger.error("[ScrapeGraphAI] Cannot start - ScrapeGraphAI not installed")
            return
        
        self._running = True
        logger.info("[ScrapeGraphAI] Integration started")
    
    def stop(self) -> None:
        """Stop the ScrapeGraphAI integration."""
        self._running = False
        logger.info("[ScrapeGraphAI] Integration stopped")
    
    def scrape(self, request: ScrapingRequest) -> ScrapingResult:
        """
        Perform web scraping with ScrapeGraphAI.
        
        Args:
            request: Scraping request with URL and parameters
        
        Returns:
            ScrapingResult with extracted data
        """
        if not _HAS_SCRAPEGRAPHAI:
            return ScrapingResult(
                request_id=self._generate_request_id(),
                url=request.url,
                success=False,
                error_message="ScrapeGraphAI not installed"
            )
        
        start_time = time.time()
        request_id = self._generate_request_id()
        
        try:
            logger.info(f"[ScrapeGraphAI] Scraping: {request.url} with strategy: {request.strategy.value}")
            
            # Choose scraping strategy
            if request.strategy == ScrapingStrategy.SMART_SCRAPER:
                result = self._smart_scrape(request, request_id)
            elif request.strategy == ScrapingStrategy.SEARCH_GRAPH:
                result = self._search_scrape(request, request_id)
            elif request.strategy == ScrapingStrategy.BASIC_SCRAPER:
                result = self._basic_scrape(request, request_id)
            else:
                result = self._custom_scrape(request, request_id)
            
            # Calculate quality score
            result.quality_score = self._calculate_quality_score(result)
            result.quality_level = self._determine_quality_level(result.quality_score)
            result.extraction_time_sec = time.time() - start_time
            
            # Add to history
            self._scraping_history.append(result)
            
            logger.info(f"[ScrapeGraphAI] Scraping complete: {request.url} (quality: {result.quality_level.value})")
            
            return result
            
        except Exception as e:
            logger.error(f"[ScrapeGraphAI] Scraping failed: {e}")
            return ScrapingResult(
                request_id=request_id,
                url=request.url,
                success=False,
                error_message=str(e),
                extraction_time_sec=time.time() - start_time
            )
    
    def _smart_scrape(self, request: ScrapingRequest, request_id: str) -> ScrapingResult:
        """Use SmartScraperGraph for AI-powered scraping."""
        try:
            # Configure graph
            graph_config = {
                "llm": {
                    "model": "ollama/qwen2.5:3b",
                    "temperature": 0.1,
                    "format": "json",
                    "base_url": self.ollama_url
                },
                "verbose": True,
                "headless": True
            }
            
            # Create smart scraper
            smart_scraper = SmartScraperGraph(
                prompt=request.description or "Extract all structured data from this page",
                source=request.url,
                config=graph_config
            )
            
            # Run scraper
            result = smart_scraper.run()
            
            # Parse result
            if isinstance(result, dict):
                raw_data = [result]
            elif isinstance(result, list):
                raw_data = result
            else:
                raw_data = [{"content": str(result)}]
            
            # Convert to DataFrame with multi-column extraction
            df = self._extract_multi_columns(raw_data, request.columns)
            
            return ScrapingResult(
                request_id=request_id,
                url=request.url,
                success=True,
                data=df,
                raw_data=raw_data,
                pages_scraped=1,
                metadata={"strategy": "smart_scraper"}
            )
            
        except Exception as e:
            logger.error(f"[ScrapeGraphAI] Smart scraper failed: {e}")
            raise
    
    def _search_scrape(self, request: ScrapingRequest, request_id: str) -> ScrapingResult:
        """Use SearchGraph for search and extraction."""
        try:
            # Configure graph
            graph_config = {
                "llm": {
                    "model": "ollama/qwen2.5:3b",
                    "temperature": 0.1,
                    "format": "json",
                    "base_url": self.ollama_url
                },
                "verbose": True,
                "headless": True
            }
            
            # Create search graph
            search_graph = SearchGraph(
                prompt=request.description or "Search and extract relevant information",
                source=request.url,
                config=graph_config
            )
            
            # Run scraper
            result = search_graph.run()
            
            # Parse result
            if isinstance(result, dict):
                raw_data = [result]
            elif isinstance(result, list):
                raw_data = result
            else:
                raw_data = [{"content": str(result)}]
            
            # Convert to DataFrame
            df = self._extract_multi_columns(raw_data, request.columns)
            
            return ScrapingResult(
                request_id=request_id,
                url=request.url,
                success=True,
                data=df,
                raw_data=raw_data,
                pages_scraped=1,
                metadata={"strategy": "search_graph"}
            )
            
        except Exception as e:
            logger.error(f"[ScrapeGraphAI] Search scraper failed: {e}")
            raise
    
    def _basic_scrape(self, request: ScrapingRequest, request_id: str) -> ScrapingResult:
        """Use basic ScraperGraph for simple scraping."""
        try:
            # Configure graph
            graph_config = {
                "llm": {
                    "model": "ollama/qwen2.5:3b",
                    "temperature": 0.1,
                    "format": "json",
                    "base_url": self.ollama_url
                },
                "verbose": True,
                "headless": True
            }
            
            # Create basic scraper
            scraper = ScraperGraph(
                prompt=request.description or "Extract all data from this page",
                source=request.url,
                config=graph_config
            )
            
            # Run scraper
            result = scraper.run()
            
            # Parse result
            if isinstance(result, dict):
                raw_data = [result]
            elif isinstance(result, list):
                raw_data = result
            else:
                raw_data = [{"content": str(result)}]
            
            # Convert to DataFrame
            df = self._extract_multi_columns(raw_data, request.columns)
            
            return ScrapingResult(
                request_id=request_id,
                url=request.url,
                success=True,
                data=df,
                raw_data=raw_data,
                pages_scraped=1,
                metadata={"strategy": "basic_scraper"}
            )
            
        except Exception as e:
            logger.error(f"[ScrapeGraphAI] Basic scraper failed: {e}")
            raise
    
    def _custom_scrape(self, request: ScrapingRequest, request_id: str) -> ScrapingResult:
        """Custom graph-based scraping."""
        # Implement custom graph logic
        logger.info("[ScrapeGraphAI] Custom scraping not yet implemented")
        return ScrapingResult(
            request_id=request_id,
            url=request.url,
            success=False,
            error_message="Custom scraping not yet implemented"
        )
    
    def _extract_multi_columns(self, raw_data: List[Dict[str, Any]], 
                              columns: Optional[List[str]] = None) -> pd.DataFrame:
        """
        Extract multi-column data from raw scraping results.
        
        Args:
            raw_data: Raw data from scraping
            columns: Specific columns to extract (None = extract all)
        
        Returns:
            DataFrame with extracted columns
        """
        if not raw_data:
            return pd.DataFrame()
        
        # Flatten nested structures
        flattened_data = []
        for item in raw_data:
            flattened = self._flatten_dict(item)
            flattened_data.append(flattened)
        
        # Create DataFrame
        df = pd.DataFrame(flattened_data)
        
        # Filter columns if specified
        if columns:
            available_columns = [col for col in columns if col in df.columns]
            if available_columns:
                df = df[available_columns]
        
        return df
    
    def _flatten_dict(self, d: Dict[str, Any], parent_key: str = "", sep: str = "_") -> Dict[str, Any]:
        """Flatten nested dictionary."""
        items = []
        for k, v in d.items():
            new_key = f"{parent_key}{sep}{k}" if parent_key else k
            if isinstance(v, dict):
                items.extend(self._flatten_dict(v, new_key, sep=sep).items())
            elif isinstance(v, list):
                # Handle lists by converting to string or counting
                if v and isinstance(v[0], dict):
                    # List of dicts - flatten each
                    for i, item in enumerate(v):
                        items.extend(self._flatten_dict(item, f"{new_key}{sep}{i}", sep=sep).items())
                else:
                    items.append((new_key, str(v)))
            else:
                items.append((new_key, v))
        return dict(items)
    
    def _calculate_quality_score(self, result: ScrapingResult) -> float:
        """Calculate quality score for scraped data."""
        if not result.success or result.data is None:
            return 0.0
        
        score = 0.0
        
        # Data completeness
        if result.data is not None and not result.data.empty:
            score += 0.3
        
        # Column count
        if result.data is not None and len(result.data.columns) > 1:
            score += 0.2
        
        # Row count
        if result.data is not None and len(result.data) > 5:
            score += 0.2
        
        # Data consistency
        if result.data is not None:
            non_null_ratio = result.data.count().sum() / (len(result.data) * len(result.data.columns))
            score += non_null_ratio * 0.3
        
        return min(1.0, score)
    
    def _determine_quality_level(self, score: float) -> DataQuality:
        """Determine quality level from score."""
        if score >= 0.8:
            return DataQuality.HIGH
        elif score >= 0.5:
            return DataQuality.MEDIUM
        elif score >= 0.3:
            return DataQuality.LOW
        else:
            return DataQuality.UNKNOWN
    
    def _generate_request_id(self) -> str:
        """Generate unique request ID."""
        import hashlib
        return hashlib.md5(f"{time.time()}".encode()).hexdigest()[:12]
    
    def get_scraping_history(self) -> List[Dict[str, Any]]:
        """Get scraping history."""
        return [result.to_dict() for result in self._scraping_history]


# Singleton instance
_scrapegraphai_instance: Optional[ScrapeGraphAIIntegration] = None

def get_scrapegraphai() -> ScrapeGraphAIIntegration:
    """Get the singleton ScrapeGraphAI integration instance."""
    global _scrapegraphai_instance
    if _scrapegraphai_instance is None:
        _scrapegraphai_instance = ScrapeGraphAIIntegration()
    return _scrapegraphai_instance


def scrape_url(url: str, description: str = "", columns: Optional[List[str]] = None,
              strategy: str = "smart_scraper") -> ScrapingResult:
    """
    Convenience function to scrape a URL.
    
    Args:
        url: URL to scrape
        description: Description of what to extract
        columns: Specific columns to extract
        strategy: Scraping strategy
    
    Returns:
        ScrapingResult
    """
    integration = get_scrapegraphai()
    
    request = ScrapingRequest(
        url=url,
        strategy=ScrapingStrategy(strategy),
        description=description,
        columns=columns
    )
    
    return integration.scrape(request)
