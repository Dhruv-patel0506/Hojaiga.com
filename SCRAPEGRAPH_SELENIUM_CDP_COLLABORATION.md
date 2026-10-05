# ScrapeGraph AI, Selenium, and CDP Collaboration Guide

## Overview

This document explains how ScrapeGraph AI, Selenium, and Chrome DevTools Protocol (CDP) can collaborate with each other in web automation and scraping contexts, particularly for your Hojaiga automation system.

## Technology Stack Comparison

| Technology | Type | Strengths | Weaknesses | Use Case |
|------------|------|-----------|------------|----------|
| **ScrapeGraph AI** | AI-Powered Scraping Framework | LLM-driven extraction, intelligent data understanding, handles dynamic content | Requires LLM API, slower than traditional scraping | Complex data extraction, understanding unstructured content |
| **Selenium** | Browser Automation (WebDriver) | Mature ecosystem, extensive browser support, cross-platform | Heavy resource usage, slower than CDP, requires driver management | Legacy systems, cross-browser testing, simple automation |
| **CDP** | Chrome DevTools Protocol | Native Chrome control, faster, no driver overhead, better performance | Chrome-only, requires async/await, steeper learning curve | Modern Chrome automation, performance-critical tasks |

## Collaboration Patterns

### Pattern 1: ScrapeGraph AI + CDP (Recommended for Modern Stack)

**Architecture:**
```
CDP Runtime (Organ 19) → ScrapeGraph AI Agent → Data Extraction
```

**How It Works:**
1. CDP handles browser navigation, page loading, and interaction
2. ScrapeGraph AI uses LLM to understand page structure and extract data
3. CDP provides screenshots/DOM to ScrapeGraph AI for analysis
4. ScrapeGraph AI returns structured data based on LLM understanding

**Benefits:**
- Fast browser control via CDP
- Intelligent data extraction via LLM
- Best of both worlds: performance + intelligence

**Implementation Example:**
```python
from scrapegraphai import Scraper
from core_organs.organ_19_chrome_cdp_runtime import CDPRuntimeKernel

# Initialize CDP runtime
kernel = CDPRuntimeKernel()
await kernel.start()
session_id = await kernel.create_tab("https://example.com")

# Navigate with CDP
await kernel.navigate(session_id, "https://example.com")

# Get page content via CDP
page_content = await kernel.get_clean_page_summary(session_id)

# Use ScrapeGraph AI for intelligent extraction
scraper = Scraper(
    llm_model="gpt-4",
    headless=True,
    verbose=True
)
result = scraper.run(
    url="https://example.com",
    prompt="Extract all product names and prices from this page"
)

# Extracted data
print(result)
```

### Pattern 2: ScrapeGraph AI + Selenium (Legacy Compatibility)

**Architecture:**
```
Selenium WebDriver → ScrapeGraph AI Agent → Data Extraction
```

**How It Works:**
1. Selenium handles browser navigation using WebDriver
2. ScrapeGraph AI uses LLM to understand and extract data
3. Selenium provides page source/screenshots to ScrapeGraph AI
4. ScrapeGraph AI returns structured data

**Benefits:**
- Works with any browser (Firefox, Chrome, Safari, Edge)
- Familiar Selenium API
- Good for cross-browser testing

**Drawbacks:**
- Slower than CDP
- Heavier resource usage
- Requires driver management

**Implementation Example:**
```python
from selenium import webdriver
from scrapegraphai import Scraper

# Initialize Selenium
driver = webdriver.Chrome()
driver.get("https://example.com")

# Get page content
page_source = driver.page_source

# Use ScrapeGraph AI
scraper = Scraper(llm_model="gpt-4")
result = scraper.run(
    source=page_source,
    prompt="Extract product data"
)

driver.quit()
```

### Pattern 3: Selenium → CDP Migration Strategy

**Architecture:**
```
Selenium (Legacy) → Migration Layer → CDP (Modern)
```

**How It Works:**
1. Existing Selenium code runs unchanged
2. Migration layer translates Selenium commands to CDP
3. Gradual migration from Selenium to CDP
4. Both systems can run in parallel during transition

**Benefits:**
- Zero-downtime migration
- Gradual modernization
- Backward compatibility

**Implementation Pattern:**
```python
class SeleniumToCDPAdapter:
    """Adapter to make CDP work like Selenium"""
    
    def __init__(self, cdp_kernel):
        self.kernel = cdp_kernel
        self.current_session = None
    
    async def get(self, url):
        """Selenium-like get() method"""
        self.current_session = await self.kernel.create_tab(url)
        await self.kernel.navigate(self.current_session, url)
    
    async def find_element(self, selector):
        """Selenium-like find_element()"""
        # Use CDP DOM.querySelector
        result = await self.kernel._invoke_session(
            self.current_session,
            "DOM.querySelector",
            {"selector": selector}
        )
        return result
    
    async def execute_script(self, script):
        """Selenium-like execute_script()"""
        return await self.kernel.js_runtime.evaluate(
            self.current_session,
            script
        )
```

### Pattern 4: Hybrid CDP + ScrapeGraph AI + Fallback to Selenium

**Architecture:**
```
Primary: CDP + ScrapeGraph AI
Fallback: Selenium (for unsupported browsers)
```

**How It Works:**
1. Try CDP first (fast, Chrome-only)
2. If Chrome not available, fall back to Selenium
3. ScrapeGraph AI works with either
4. Automatic failover

**Benefits:**
- Maximum browser support
- Performance optimization (CDP when possible)
- Resilience

**Implementation Example:**
```python
class HybridAutomation:
    def __init__(self):
        self.use_cdp = True
        self.cdp_kernel = None
        self.selenium_driver = None
    
    async def initialize(self):
        """Try CDP first, fall back to Selenium"""
        try:
            self.cdp_kernel = CDPRuntimeKernel()
            await self.cdp_kernel.start()
            self.use_cdp = True
        except Exception:
            self.selenium_driver = webdriver.Chrome()
            self.use_cdp = False
    
    async def navigate(self, url):
        if self.use_cdp:
            session = await self.cdp_kernel.create_tab(url)
            await self.cdp_kernel.navigate(session, url)
            return session
        else:
            self.selenium_driver.get(url)
            return None
    
    def extract_data(self, prompt):
        """ScrapeGraph AI works with either"""
        scraper = Scraper(llm_model="gpt-4")
        if self.use_cdp:
            # Get content from CDP
            content = await self.cdp_kernel.get_clean_page_summary(session)
        else:
            # Get content from Selenium
            content = self.selenium_driver.page_source
        
        return scraper.run(source=content, prompt=prompt)
```

## Integration with Hojaiga Architecture

### Current Hojaiga Stack
```
Organ 19 (CDP Runtime) → Organ 41 (Scanner) → Organ 42 (Navigation) → Organ 43 (Fallback)
```

### Proposed Integration with ScrapeGraph AI

#### Option 1: ScrapeGraph AI as Organ 45 (Data Extraction Organ)

**File:** `core_organs/organ_45_scrapegraph_ai.py`

```python
"""
Organ 45 — ScrapeGraph AI Integration (Intelligent Data Extraction)

Responsibility: Use ScrapeGraph AI with LLMs to intelligently extract structured
data from web pages, working with CDP for fast browser control.
"""

import asyncio
import logging
from typing import Any, Dict, List, Optional

if r"D:\new_automation\All codes" not in sys.path:
    sys.path.insert(0, r"D:\new_automation\All codes")

logger = logging.getLogger("hojaiga.organ45.scrapegraph_ai")

class ScrapeGraphAIOrgan:
    """
    Intelligent data extraction using ScrapeGraph AI.
    
    Collaboration:
    - Uses CDP (Organ 19) for fast browser navigation
    - Uses LLMs for intelligent data understanding
    - Returns structured data to Brain (Organ 01)
    """
    
    def __init__(self, cdp_kernel=None, llm_model="gpt-4"):
        self.cdp_kernel = cdp_kernel
        self.llm_model = llm_model
        self._scraper = None
        self._available = False
        
    def _init_scrapegraph(self):
        """Initialize ScrapeGraph AI."""
        try:
            from scrapegraphai import Scraper
            self._scraper = Scraper(
                llm_model=self.llm_model,
                headless=True,
                verbose=True
            )
            self._available = True
            logger.info("[ScrapeGraphAI] Initialized successfully")
        except ImportError:
            logger.warning("[ScrapeGraphAI] ScrapeGraph AI not installed")
        except Exception as e:
            logger.error(f"[ScrapeGraphAI] Failed to initialize: {e}")
    
    async def extract_data(self, session_id: str, prompt: str) -> Dict[str, Any]:
        """
        Extract data from current page using ScrapeGraph AI.
        
        Args:
            session_id: CDP session ID
            prompt: Natural language extraction prompt
        """
        if not self._available:
            self._init_scrapegraph()
        
        if not self._available:
            return {"error": "ScrapeGraph AI not available"}
        
        try:
            # Get page content via CDP
            page_summary = await self.cdp_kernel.get_clean_page_summary(session_id)
            
            # Use ScrapeGraph AI for extraction
            result = self._scraper.run(
                source=page_summary,
                prompt=prompt
            )
            
            logger.info(f"[ScrapeGraphAI] Extracted data: {len(result)} items")
            return result
            
        except Exception as e:
            logger.error(f"[ScrapeGraphAI] Extraction failed: {e}")
            return {"error": str(e)}
    
    async def extract_structured(self, session_id: str, schema: Dict[str, Any]) -> Dict[str, Any]:
        """
        Extract data with structured schema.
        
        Args:
            session_id: CDP session ID
            schema: Expected data structure
        """
        prompt = f"Extract data matching this schema: {schema}"
        return await self.extract_data(session_id, prompt)
```

#### Option 2: ScrapeGraph AI as Helper for Scanner Organ

**Integration with Organ 41 (Scanner):**

```python
# In organ_41_scanner.py, add ScrapeGraph AI integration

class ScannerOrgan:
    def __init__(self, cdp_publisher=None, vision_model_url=None, use_scrapegraph=False):
        # ... existing initialization ...
        self.use_scrapegraph = use_scrapegraph
        self.scrapegraph_organ = None
        
        if use_scrapegraph:
            from core_organs.organ_45_scrapegraph_ai import ScrapeGraphAIOrgan
            self.scrapegraph_organ = ScrapeGraphAIOrgan(cdp_kernel=self.cdp_kernel)
    
    async def _enhance_elements_with_ai(self, elements: List[UIElement]) -> List[UIElement]:
        """Use ScrapeGraph AI to enhance element understanding."""
        if not self.use_scrapegraph or not self.scrapegraph_organ:
            return elements
        
        try:
            # Use ScrapeGraph AI to understand element purposes
            prompt = "Analyze these UI elements and predict their actions"
            enhanced = await self.scrapegraph_organ.extract_data(
                self.current_session_id,
                prompt
            )
            
            # Merge AI insights with UI elements
            for elem in elements:
                ai_insight = self._find_ai_insight(elem, enhanced)
                if ai_insight:
                    elem.semantic_action = ai_insight.get("action")
                    elem.confidence = ai_insight.get("confidence", 0.8)
            
            return elements
        except Exception as e:
            logger.warning(f"AI enhancement failed: {e}")
            return elements
```

## Migration Strategy for Hojaiga

### Phase 1: Add ScrapeGraph AI Support (Current)
- Create Organ 45 (ScrapeGraph AI integration)
- Keep existing CDP architecture
- Add optional AI enhancement to Scanner Organ

### Phase 2: Hybrid Mode (Transition)
- Add Selenium adapter for legacy compatibility
- Support both CDP and Selenium in parallel
- Gradually migrate critical paths to CDP

### Phase 3: Full CDP + AI (Target)
- Deprecate Selenium completely
- Use CDP for all browser automation
- Use ScrapeGraph AI for all intelligent extraction
- Remove Selenium dependencies

## When to Use Each Technology

### Use CDP When:
- Chrome-only automation is acceptable
- Performance is critical
- You need fine-grained browser control
- You're building modern automation systems

### Use Selenium When:
- You need cross-browser support (Firefox, Safari, Edge)
- You're maintaining legacy systems
- You need extensive browser compatibility testing
- You're not ready to migrate to async/await

### Use ScrapeGraph AI When:
- You need intelligent data extraction
- Page structure is complex or dynamic
- You want LLM-powered understanding
- You need to extract unstructured data

### Use All Three Together When:
- You want maximum flexibility
- You're in migration phase
- You need fallback options
- You want to combine speed (CDP) with intelligence (ScrapeGraph AI)

## Performance Comparison

| Operation | Selenium | CDP | ScrapeGraph AI + CDP |
|-----------|----------|-----|---------------------|
| Page Load | 2-3s | 1-2s | 1-2s |
| Element Find | 100-200ms | 50-100ms | 50-100ms |
| Data Extraction | Manual parsing | Manual parsing | AI-powered (1-3s) |
| Script Execution | 50-100ms | 20-50ms | 20-50ms |
| Memory Usage | High (driver) | Low (native) | Low + LLM API |

## Installation

### ScrapeGraph AI
```bash
pip install scrapegraphai
# Requires LLM API key (OpenAI, Anthropic, etc.)
export OPENAI_API_KEY="your-key"
```

### Selenium (for legacy/fallback)
```bash
pip install selenium
# ChromeDriver is auto-managed by webdriver-manager
pip install webdriver-manager
```

### CDP (already in Hojaiga)
```bash
# Already installed as part of Hojaiga
pip install websockets aiohttp
```

## Configuration

### Environment Variables
```bash
# ScrapeGraph AI Configuration
export SCRAPEGRAPH_LLM_MODEL="gpt-4"
export SCRAPEGRAPH_API_KEY="your-openai-key"

# Automation Mode
export HOJAIGA_BROWSER_MODE="cdp"  # or "selenium" or "hybrid"
export HOJAIGA_USE_SCRAPEGRAPH="true"
```

### Centralized Config Updates
Add to `centralized_config_manager.py`:
```python
self._schemas["HOJAIGA_BROWSER_MODE"] = ConfigSchema(
    key="HOJAIGA_BROWSER_MODE",
    value_type=ConfigValueType.STRING,
    default="cdp",
    description="Browser automation mode: cdp, selenium, hybrid",
    env_var="HOJAIGA_BROWSER_MODE",
    allowed_values=["cdp", "selenium", "hybrid"]
)

self._schemas["HOJAIGA_USE_SCRAPEGRAPH"] = ConfigSchema(
    key="HOJAIGA_USE_SCRAPEGRAPH",
    value_type=ConfigValueType.BOOLEAN,
    default=True,
    description="Enable ScrapeGraph AI for intelligent data extraction",
    env_var="HOJAIGA_USE_SCRAPEGRAPH"
)

self._schemas["SCRAPEGRAPH_LLM_MODEL"] = ConfigSchema(
    key="SCRAPEGRAPH_LLM_MODEL",
    value_type=ConfigValueType.STRING,
    default="gpt-4",
    description="LLM model for ScrapeGraph AI",
    env_var="SCRAPEGRAPH_LLM_MODEL"
)
```

## Summary

**Recommended Stack for Hojaiga:**
1. **Primary:** CDP (Organ 19) for fast Chrome automation
2. **Intelligence:** ScrapeGraph AI (Organ 45) for LLM-powered extraction
3. **Fallback:** Selenium adapter for legacy compatibility (optional)
4. **Integration:** Hybrid mode during migration phase

**Benefits:**
- Maximum performance with CDP
- Intelligent extraction with ScrapeGraph AI
- Backward compatibility with Selenium
- Smooth migration path
- Future-proof architecture

**Next Steps:**
1. Create Organ 45 (ScrapeGraph AI integration)
2. Add optional AI enhancement to Scanner Organ
3. Implement Selenium adapter for hybrid mode
4. Test with Gmail example
5. Gradually migrate all paths to CDP + AI
