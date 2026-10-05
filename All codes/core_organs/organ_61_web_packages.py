"""
Organ 61 — Lightweight Web Packages Integration

Responsibility: Use modern, lightweight web packages to make Hojaiga lighter, more reliable, and efficient.
Uses the best packages from the web ecosystem.

Features:
- httpx (lighter, faster than requests)
- aiohttp (async HTTP)
- pydantic (data validation)
- rich (beautiful terminal output)
- loguru (better logging)
- tqdm (progress bars)
- beautifulsoup4 (HTML parsing)
- playwright (modern web automation)
- tenacity (retry logic)
- click (CLI framework)
- pyyaml (YAML parsing)
- python-dotenv (environment variables)
"""

import asyncio
import logging
import sys
from typing import Any, Dict, List, Optional
from enum import Enum

if r"D:\new_automation\All codes" not in sys.path:
    sys.path.insert(0, r"D:\new_automation\All codes")

logger = logging.getLogger("hojaiga.organ61.web_packages")


class PackageCategory(Enum):
    """Categories of web packages."""
    HTTP_CLIENT = "http_client"
    ASYNC_HTTP = "async_http"
    DATA_VALIDATION = "data_validation"
    TERMINAL_OUTPUT = "terminal_output"
    LOGGING = "logging"
    PROGRESS = "progress"
    HTML_PARSING = "html_parsing"
    WEB_AUTOMATION = "web_automation"
    RETRY_LOGIC = "retry_logic"
    CLI_FRAMEWORK = "cli_framework"
    CONFIG_PARSING = "config_parsing"
    ENV_MANAGEMENT = "env_management"


class WebPackageIntegration:
    """
    Integration with lightweight web packages.
    
    Uses modern, efficient packages from the web ecosystem:
    - httpx: HTTP/1.1 and HTTP/2 support, faster than requests
    - aiohttp: Async HTTP client
    - pydantic: Data validation using Python type annotations
    - rich: Beautiful terminal output
    - loguru: Better logging with rotation and compression
    - tqdm: Progress bars
    - beautifulsoup4: HTML parsing
    - playwright: Modern web automation (faster than Selenium)
    - tenacity: Retry logic with exponential backoff
    - click: CLI framework
    - pyyaml: YAML parsing
    - python-dotenv: Environment variable management
    """
    
    def __init__(self):
        self._packages = {}
        self._package_status = {}
        self._check_packages()
    
    def _check_packages(self):
        """Check which packages are available."""
        packages = {
            "httpx": PackageCategory.HTTP_CLIENT,
            "aiohttp": PackageCategory.ASYNC_HTTP,
            "pydantic": PackageCategory.DATA_VALIDATION,
            "rich": PackageCategory.TERMINAL_OUTPUT,
            "loguru": PackageCategory.LOGGING,
            "tqdm": PackageCategory.PROGRESS,
            "bs4": PackageCategory.HTML_PARSING,
            "playwright": PackageCategory.WEB_AUTOMATION,
            "tenacity": PackageCategory.RETRY_LOGIC,
            "click": PackageCategory.CLI_FRAMEWORK,
            "yaml": PackageCategory.CONFIG_PARSING,
            "dotenv": PackageCategory.ENV_MANAGEMENT,
        }
        
        for package, category in packages.items():
            try:
                __import__(package)
                self._package_status[package] = True
                logger.info(f"[WebPackages] {package} is available")
            except ImportError:
                self._package_status[package] = False
                logger.warning(f"[WebPackages] {package} is not available")
    
    async def http_get(self, url: str, headers: Dict[str, str] = None, 
                     timeout: int = 30) -> Dict[str, Any]:
        """
        Perform HTTP GET using httpx (lighter, faster than requests).
        
        Args:
            url: URL to fetch
            headers: HTTP headers
            timeout: Timeout in seconds
        
        Returns:
            Response data
        """
        logger.info(f"[WebPackages] HTTP GET: {url}")
        
        try:
            if self._package_status.get("httpx"):
                import httpx
                async with httpx.AsyncClient(timeout=timeout) as client:
                    response = await client.get(url, headers=headers)
                    return {
                        "success": True,
                        "status_code": response.status_code,
                        "headers": dict(response.headers),
                        "content": response.text,
                        "bytes": len(response.content)
                    }
            else:
                # Fallback to aiohttp
                if self._package_status.get("aiohttp"):
                    import aiohttp
                    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=timeout)) as session:
                        async with session.get(url, headers=headers) as response:
                            text = await response.text()
                            return {
                                "success": True,
                                "status_code": response.status,
                                "headers": dict(response.headers),
                                "content": text,
                                "bytes": len(text.encode())
                            }
                else:
                    # Fallback to standard library
                    import urllib.request
                    import urllib.error
                    req = urllib.request.Request(url, headers=headers or {})
                    with urllib.request.urlopen(req, timeout=timeout) as response:
                        content = response.read().decode()
                        return {
                            "success": True,
                            "status_code": response.status,
                            "content": content,
                            "bytes": len(content)
                        }
        except Exception as e:
            logger.error(f"[WebPackages] HTTP GET failed: {e}")
            return {"success": False, "error": str(e)}
    
    async def http_post(self, url: str, data: Dict[str, Any] = None, 
                      headers: Dict[str, str] = None, timeout: int = 30) -> Dict[str, Any]:
        """
        Perform HTTP POST using httpx.
        
        Args:
            url: URL to post to
            data: Data to post
            headers: HTTP headers
            timeout: Timeout in seconds
        
        Returns:
            Response data
        """
        logger.info(f"[WebPackages] HTTP POST: {url}")
        
        try:
            if self._package_status.get("httpx"):
                import httpx
                async with httpx.AsyncClient(timeout=timeout) as client:
                    response = await client.post(url, json=data, headers=headers)
                    return {
                        "success": True,
                        "status_code": response.status_code,
                        "headers": dict(response.headers),
                        "content": response.text
                    }
            else:
                # Fallback to aiohttp
                if self._package_status.get("aiohttp"):
                    import aiohttp
                    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=timeout)) as session:
                        async with session.post(url, json=data, headers=headers) as response:
                            text = await response.text()
                            return {
                                "success": True,
                                "status_code": response.status,
                                "content": text
                            }
        except Exception as e:
            logger.error(f"[WebPackages] HTTP POST failed: {e}")
            return {"success": False, "error": str(e)}
    
    def parse_html(self, html: str, selector: str = None) -> Dict[str, Any]:
        """
        Parse HTML using beautifulsoup4.
        
        Args:
            html: HTML content
            selector: CSS selector
        
        Returns:
            Parsed data
        """
        logger.info(f"[WebPackages] Parsing HTML")
        
        try:
            if self._package_status.get("bs4"):
                from bs4 import BeautifulSoup
                soup = BeautifulSoup(html, 'html.parser')
                
                if selector:
                    elements = soup.select(selector)
                    return {
                        "success": True,
                        "elements": [str(e) for e in elements],
                        "count": len(elements)
                    }
                else:
                    return {
                        "success": True,
                        "title": soup.title.string if soup.title else None,
                        "text": soup.get_text(),
                        "links": [a.get('href') for a in soup.find_all('a', href=True)]
                    }
            else:
                # Fallback to simple regex
                import re
                links = re.findall(r'href="([^"]+)"', html)
                title_match = re.search(r'<title>([^<]+)</title>', html)
                title = title_match.group(1) if title_match else None
                
                return {
                    "success": True,
                    "title": title,
                    "links": links,
                    "method": "regex_fallback"
                }
        except Exception as e:
            logger.error(f"[WebPackages] HTML parsing failed: {e}")
            return {"success": False, "error": str(e)}
    
    def validate_data(self, data: Dict[str, Any], schema: Dict[str, Any]) -> Dict[str, Any]:
        """
        Validate data using pydantic.
        
        Args:
            data: Data to validate
            schema: Schema definition
        
        Returns:
            Validation result
        """
        logger.info(f"[WebPackages] Validating data")
        
        try:
            if self._package_status.get("pydantic"):
                from pydantic import BaseModel, ValidationError
                from typing import Dict as TypingDict, Any as TypingAny
                
                # Create dynamic model
                fields = {}
                for field_name, field_info in schema.items():
                    field_type = field_info.get("type", str)
                    fields[field_name] = (field_type, ...)
                
                DynamicModel = type('DynamicModel', (BaseModel,), fields)
                
                try:
                    validated = DynamicModel(**data)
                    return {
                        "success": True,
                        "validated": validated.dict(),
                        "errors": None
                    }
                except ValidationError as e:
                    return {
                        "success": False,
                        "validated": None,
                        "errors": e.errors()
                    }
            else:
                # Fallback to simple validation
                errors = []
                for field_name, field_info in schema.items():
                    if field_name not in data:
                        errors.append(f"Missing field: {field_name}")
                    else:
                        expected_type = field_info.get("type", str)
                        if not isinstance(data[field_name], expected_type):
                            errors.append(f"Type mismatch for {field_name}")
                
                return {
                    "success": len(errors) == 0,
                    "validated": data if len(errors) == 0 else None,
                    "errors": errors if errors else None
                }
        except Exception as e:
            logger.error(f"[WebPackages] Data validation failed: {e}")
            return {"success": False, "error": str(e)}
    
    def rich_print(self, message: str, style: str = None):
        """
        Print using rich for beautiful terminal output.
        
        Args:
            message: Message to print
            style: Rich style
        """
        try:
            if self._package_status.get("rich"):
                from rich.console import Console
                from rich.text import Text
                console = Console()
                
                if style:
                    text = Text(message, style=style)
                    console.print(text)
                else:
                    console.print(message)
            else:
                print(message)
        except Exception as e:
            logger.error(f"[WebPackages] Rich print failed: {e}")
            print(message)
    
    def setup_logging(self, log_file: str = "hojaiga.log", rotation: str = "10 MB"):
        """
        Setup logging using loguru.
        
        Args:
            log_file: Log file path
            rotation: Rotation setting
        """
        try:
            if self._package_status.get("loguru"):
                from loguru import logger as loguru_logger
                loguru_logger.add(log_file, rotation=rotation, level="INFO")
                loguru_logger.info("Loguru logging initialized")
            else:
                import logging
                logging.basicConfig(
                    filename=log_file,
                    level=logging.INFO,
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
                )
        except Exception as e:
            logger.error(f"[WebPackages] Logging setup failed: {e}")
    
    def progress_bar(self, iterable, description: str = "Processing"):
        """
        Show progress bar using tqdm.
        
        Args:
            iterable: Iterable to track
            description: Progress bar description
        
        Returns:
            Iterable with progress bar
        """
        try:
            if self._package_status.get("tqdm"):
                from tqdm import tqdm
                return tqdm(iterable, desc=description)
            else:
                return iterable
        except Exception as e:
            logger.error(f"[WebPackages] Progress bar failed: {e}")
            return iterable
    
    async def retry_with_backoff(self, func, max_retries: int = 3, 
                                 base_delay: float = 1.0) -> Any:
        """
        Retry function with exponential backoff using tenacity.
        
        Args:
            func: Function to retry
            max_retries: Maximum number of retries
            base_delay: Base delay in seconds
        
        Returns:
            Function result
        """
        try:
            if self._package_status.get("tenacity"):
                from tenacity import retry, stop_after_attempt, wait_exponential
                
                @retry(stop=stop_after_attempt(max_retries),
                      wait=wait_exponential(multiplier=1, min=base_delay, max=60))
                async def _retry_wrapper():
                    return await func()
                
                return await _retry_wrapper()
            else:
                # Manual retry
                for attempt in range(max_retries):
                    try:
                        return await func()
                    except Exception as e:
                        if attempt == max_retries - 1:
                            raise
                        delay = base_delay * (2 ** attempt)
                        await asyncio.sleep(delay)
        except Exception as e:
            logger.error(f"[WebPackages] Retry failed: {e}")
            raise
    
    def load_config(self, config_path: str) -> Dict[str, Any]:
        """
        Load config using pyyaml.
        
        Args:
            config_path: Path to config file
        
        Returns:
            Config data
        """
        try:
            if self._package_status.get("yaml"):
                import yaml
                with open(config_path, 'r') as f:
                    return yaml.safe_load(f)
            else:
                # Fallback to JSON
                import json
                with open(config_path, 'r') as f:
                    return json.load(f)
        except Exception as e:
            logger.error(f"[WebPackages] Config loading failed: {e}")
            return {}
    
    def load_env(self, env_file: str = ".env") -> Dict[str, str]:
        """
        Load environment variables using python-dotenv.
        
        Args:
            env_file: Path to .env file
        
        Returns:
            Environment variables
        """
        try:
            if self._package_status.get("dotenv"):
                from dotenv import load_dotenv
                load_dotenv(env_file)
                import os
                return dict(os.environ)
            else:
                # Fallback to manual parsing
                import os
                env_vars = {}
                if os.path.exists(env_file):
                    with open(env_file, 'r') as f:
                        for line in f:
                            line = line.strip()
                            if line and not line.startswith('#') and '=' in line:
                                key, value = line.split('=', 1)
                                env_vars[key.strip()] = value.strip()
                                os.environ[key.strip()] = value.strip()
                return env_vars
        except Exception as e:
            logger.error(f"[WebPackages] Env loading failed: {e}")
            return {}
    
    def get_package_status(self) -> Dict[str, bool]:
        """Get status of all packages."""
        return self._package_status.copy()
    
    def install_missing_packages(self) -> str:
        """Generate pip install command for missing packages."""
        missing = [pkg for pkg, status in self._package_status.items() if not status]
        
        if not missing:
            return "All packages are installed!"
        
        install_map = {
            "httpx": "httpx[http2]",
            "aiohttp": "aiohttp",
            "pydantic": "pydantic",
            "rich": "rich",
            "loguru": "loguru",
            "tqdm": "tqdm",
            "bs4": "beautifulsoup4",
            "playwright": "playwright",
            "tenacity": "tenacity",
            "click": "click",
            "yaml": "pyyaml",
            "dotenv": "python-dotenv",
        }
        
        packages_to_install = [install_map.get(pkg, pkg) for pkg in missing]
        command = f"pip install {' '.join(packages_to_install)}"
        
        return command
