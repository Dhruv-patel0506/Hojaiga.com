# Hojaiga Virtual Environment Setup

## Overview

Created a dedicated virtual environment for Hojaiga/CrewAI/ScrapeGraphAI to resolve dependency conflicts that occurred when ScrapeGraphAI was installed in the global Python environment.

## Virtual Environment Location

```
D:\new_automation\hojaiga_env
```

## Problem: Dependency Conflicts

When ScrapeGraphAI was installed globally, it upgraded several packages to versions incompatible with the existing Hojaiga stack:

### Critical Conflicts

1. **CrewAI + OpenAI**
   - CrewAI requires: `openai < 3, >= 2.30.0`
   - ScrapeGraphAI installed: `openai 3.22.1`
   - **Result:** CrewAI cannot import due to version mismatch

2. **CrewAI + OpenTelemetry**
   - CrewAI requires: `opentelemetry-api ~= 1.42.0`
   - ScrapeGraphAI installed: `opentelemetry-api 1.45.0`
   - **Result:** ImportError: cannot import name '_ExtendedAttributes'

3. **Instructor + OpenAI**
   - Instructor requires: `openai < 3.0.0, >= 2.0.0`
   - ScrapeGraphAI installed: `openai 3.22.1`

4. **LiteLLM + OpenAI**
   - LiteLLM requires: `openai < 3.0.0, >= 2.20.0`
   - ScrapeGraphAI installed: `openai 3.22.1`

5. **PaddleX + NumPy**
   - PaddleX requires: `numpy < 2.4, >= 1.24`
   - ScrapeGraphAI installed: `numpy 2.5.3`

6. **Ultralytics + NumPy**
   - Ultralytics requires: `numpy <= 2.1.1, >= 1.23.0`
   - ScrapeGraphAI installed: `numpy 2.5.3`

7. **R2R + FastAPI/HTTPX/OpenAI**
   - R2R requires: `fastapi < 0.115.0, >= 0.114.0`
   - R2R requires: `httpx < 0.28.0, >= 0.27.0`
   - R2R requires: `openai < 2.0.0, >= 1.11.1`
   - ScrapeGraphAI installed incompatible versions

8. **XFormers + Torch**
   - XFormers requires: `torch >= 2.10`
   - Current installation: `torch 2.7.1+cu118`

## Solution: Dedicated Virtual Environment

### Virtual Environment Configuration

The virtual environment contains compatible versions of:

```
crewai==1.15.1
openai==2.54.0 (compatible with CrewAI)
opentelemetry-api==1.42.1 (compatible with CrewAI)
scrapegraphai==2.3.0
langchain-ollama==1.1.0
numpy==2.5.3
pyautogui
uiautomation
pywin32
keyboard
pyodbc
pandas
openpyxl
selenium
playwright
```

### Environment Variables in start_hojaiga.bat

Updated the batch file to use the virtual environment:

```batch
set HOJAIGA_VENV=D:\new_automation\hojaiga_env
set HOJAIGA_PYTHON=%HOJAIGA_VENV%\Scripts\python.exe
set HOJAIGA_PIP=%HOJAIGA_VENV%\Scripts\pip.exe
```

All Python invocations in the batch file now use `%HOJAIGA_PYTHON%` instead of the global `python`:

- Brain_Gatekeeper.py
- server.py
- hojaiga_agent.py
- test_hojaiga_real_task.py
- organ_01_crewai_engine.py

## Verification

### Import Tests in Virtual Environment

```bash
# CrewAI import
D:\new_automation\hojaiga_env\Scripts\python.exe -c "import crewai"
# Result: CrewAI import OK in venv

# ScrapeGraphAI import
D:\new_automation\hojaiga_env\Scripts\python.exe -c "from scrapegraphai.graphs import SmartScraperGraph"
# Result: ScrapeGraphAI import OK in venv
```

## ScrapeGraphAI Integration with CrewAI

### Added to organ_01_crewai_engine.py

1. **Import Section (lines 170-185)**
   ```python
   # ScrapeGraphAI integration for web scraping
   try:
       from core_organs.organ_13_scrapegraphai import ScrapeGraphAIIntegration, get_scrapegraphai
       _HAS_SCRAPEGRAPHAI = True
       print("[CREWAI] ScrapeGraphAI integration loaded OK", flush=True)
   except ImportError as e:
       print(f"[CREWAI] ScrapeGraphAI integration NOT available: {e}", flush=True)
       _HAS_SCRAPEGRAPHAI = False
       ScrapeGraphAIIntegration = None
       get_scrapegraphai = None
   ```

2. **CrewAI Tool (lines 1313-1357)**
   ```python
   @tool("Scrape Webpage with ScrapeGraphAI")
   def scrape_webpage_tool(url: str, prompt: str = "Extract all meaningful data") -> str:
       """Scrape a webpage using ScrapeGraphAI with AI-powered intelligent extraction.
       Uses local Ollama models via langchain-ollama provider.
       Returns structured extracted data."""
       try:
           from scrapegraphai.graphs import SmartScraperGraph
           from langchain_ollama import ChatOllama
           
           # Configure local Ollama model
           ollama_base_url = os.environ.get("HOJAIGA_BRAIN_URL", "http://127.0.0.1:11434/api/chat").replace("/api/chat", "")
           model_name = os.environ.get("HOJAIGA_BRAIN_MODEL", "llama3")
           
           llm = ChatOllama(
               model=model_name,
               base_url=ollama_base_url,
               temperature=0.0
           )
           
           # Create SmartScraperGraph
           graph_config = {
               "llm": llm,
               "headless": True,
               "verbose": True
           }
           
           smart_scraper = SmartScraperGraph(
               prompt=prompt,
               source=url,
               config=graph_config
           )
           
           # Execute scraping
           result = smart_scraper.run()
           
           # Format result
           if isinstance(result, dict):
               extracted = result.get("answer", str(result))
               return f"SCRAPE SUCCESS from {url}: {extracted[:500]}..."
           else:
               return f"SCRAPE SUCCESS from {url}: {str(result)[:500]}..."
               
       except Exception as e:
           return f"ScrapeGraphAI scraping failed: {e}"
   ```

## Benefits of Virtual Environment Approach

1. **Isolation**: Hojaiga/CrewAI/ScrapeGraphAI dependencies are isolated from the global Python environment
2. **Compatibility**: No conflicts with other packages (paddlex, ultralytics, r2r, xformers)
3. **Reproducibility**: The virtual environment can be recreated with the same dependencies
4. **Safety**: Global environment remains unchanged for other tools
5. **Testing**: Can test different dependency combinations without affecting the system

## Running Hojaiga

To launch Hojaiga with the virtual environment:

```batch
cd D:\new_automation
start_hojaiga.bat
```

The batch file will automatically use the virtual environment Python interpreter for all Hojaiga components.

## Future Considerations

### If More Conflicts Arise

The virtual environment can be recreated with specific package versions using a requirements.txt file:

```bash
# Create requirements file
D:\new_automation\hojaiga_env\Scripts\pip.exe freeze > requirements.txt

# Recreate environment
python -m venv hojaiga_env_new
hojaiga_env_new\Scripts\pip.exe install -r requirements.txt
```

### Adding New Packages

When adding new packages to Hojaiga, install them in the virtual environment:

```bash
D:\new_automation\hojaiga_env\Scripts\pip.exe install <package_name>
```

## Status

✅ Virtual environment created: `D:\new_automation\hojaiga_env`
✅ CrewAI installed and verified in venv
✅ ScrapeGraphAI installed and verified in venv
✅ Dependency conflicts resolved
✅ start_hojaiga.bat updated to use venv
✅ ScrapeGraphAI integrated into CrewAI engine
✅ Local Ollama provider configured for ScrapeGraphAI
