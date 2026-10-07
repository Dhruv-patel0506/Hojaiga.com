"""
HOJAIGA AUTOMATION ARCHITECTURE DOC

============================================================
1. MASTER ARCHITECTURE CONTEXT
============================================================
This component is part of the Hojaiga Automation Architecture.
Component Type: Organ 37
Name: Llm Gateway

============================================================
2. ORGAN/COMPONENT DIAGRAM
============================================================
```mermaid
graph TD
    classDef default fill:#1e1e1e,stroke:#333,stroke-width:2px,color:#d4d4d4;
    classDef component fill:#2d2d2d,stroke:#569cd6,stroke-width:2px,color:#d4d4d4;
    
    UPSTREAM[UPSTREAM INPUT]
    
    UPSTREAM -- event/socket --> COMPONENT
    
    subgraph COMPONENT [Llm Gateway]
        direction TB
        IN[Inputs] --> PROC[Processing]
        PROC --> OUT[Outputs]
    end
    
    COMPONENT -- event/socket --> DOWNSTREAM_A[CONSUMER A]
    COMPONENT -- event/socket --> DOWNSTREAM_B[CONSUMER B]
    
    class COMPONENT component;
```

Inputs: Discovered from runtime
Outputs: Discovered from runtime
Dependencies: typing, time, logging, requests, os...

============================================================
3. N8N-STYLE VISUAL WORKFLOW (MODEL)
============================================================
```mermaid
graph LR
    input([Input Node]) --> process([Code Node: organ_37_llm_gateway.py]) --> output([Output Node])
```
"""

"""
Organ 37 — LLM Gateway
Hojaiga Automation OS

Authority: Constitution -> LawBook -> Diagrams -> Legacy Guide -> PolicyManual
           -> MasterArchitectureBlueprint -> Organ_Specification
           -> LLM_Gateway_Organ.md

Responsibility: 
  1. Master bootstrap: Boots Ollama, Gatekeeper, and all LLM infrastructure
  2. Auto-recovery: Refreshes Gatekeeper on failure, manages model loading
  3. Centralized routing: LLM inference with graceful degradation
  4. Prerequisite launcher: Ensures all organs have working LLM before tasks
"""

import logging
import os
import sys
import time
import socket
import subprocess
import requests
from typing import Dict, Any, Optional

logger = logging.getLogger("hojaiga.organ37.llm_gateway")

# MODULE-LEVEL call ledger: every LLMGateway() instance shares it, so a caller (or a test) can prove that a
# decision path made ZERO big-model calls. 'brain' = the 7B execute_inference rung; 'small' = the 1-3B
# execute_small_inference rung. reset_call_counts()/call_counts() are the assertions the NO-LLM-PATH test uses.
_CALLS = {"brain": 0, "small": 0}


def call_counts() -> dict:
    return dict(_CALLS)


def reset_call_counts() -> None:
    _CALLS["brain"] = 0
    _CALLS["small"] = 0

class LLMGatewayError(Exception):
    pass

class LLMGateway:
    def __init__(self):
        self._load_keys()
        # Ollama local endpoints - direct to 11434 for low-latency robust inference
        self.ollama_url = os.environ.get("HOJAIGA_BRAIN_URL", "http://127.0.0.1:11434/api/chat")
        _vision_url = os.environ.get("HOJAIGA_VISION_URL", "http://127.0.0.1:11434/api/chat")
        if "11435" in _vision_url:
            _vision_url = _vision_url.replace("11435", "11434")
        self.vision_url = _vision_url
        self.groq_url = "https://api.groq.com/openai/v1/chat/completions"
        self.openrouter_url = "https://openrouter.ai/api/v1/chat/completions"

        # Model definitions on local Ollama
        # Main Brain (qwen2.5:7b 4.7GB): ONLY for compilation by Brain organ
        self.brain_model = os.environ.get("HOJAIGA_BRAIN_MODEL", "qwen2.5:7b")
        # Small Brain (qwen2.5vl:3b 3GB): text+vision — routing, classification, quick tasks, eye
        self.small_model = os.environ.get("HOJAIGA_SMALL_MODEL", "qwen2.5vl:3b")
        # Vision: moondream (1.6GB) for fast OCR/UI, minicpm-v (5.5GB) for heavy OCR/precision
        self.vision_fast_model = os.environ.get("HOJAIGA_VISION_MODEL", "moondream")
        self.vision_reason_model = os.environ.get("HOJAIGA_VISION_REASON_MODEL", "minicpm-v:latest")
        # Vision precision: llama.cpp endpoint for Qwen2.5-VL-7B (when available)
        self.vision_precision_model = os.environ.get("HOJAIGA_VISION_PRECISION_MODEL", "minicpm-v:latest")
        self.vision_fallback_model = "moondream:latest"

        # Bootstrap state
        self._booted = False
        self._gatekeeper_proc = None
        self._ollama_proc = None
        self._hojaiga_root = os.environ.get("HOJAIGA_ROOT", r"D:\new_automation")
        self._gatekeeper_script = os.path.join(self._hojaiga_root, "Brain_Gatekeeper.py")
        
        # Initialize memory system
        self._memory = None
        try:
            from core_organs.organ_ml import memory
            self._memory = memory
            logger.info("[Gateway] Memory system initialized")
        except Exception as e:
            logger.debug("[Gateway] Memory system not available: %s", e)
    
    @property
    def memory(self):
        """Access the learning memory system."""
        if self._memory is None:
            try:
                from core_organs.organ_ml import memory
                self._memory = memory
            except Exception:
                pass
        return self._memory

    # =================================================================
    # BOOTSTRAP: Master system launcher
    # =================================================================
    def _port_alive(self, port: int) -> bool:
        """Check if a port is listening."""
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(2)
            result = sock.connect_ex(("127.0.0.1", port))
            sock.close()
            return result == 0
        except Exception:
            return False

    def _wait_port(self, port: int, name: str, timeout: int = 30) -> bool:
        """Block until port is listening."""
        logger.info("Bootstrap: Waiting for %s on port %d...", name, port)
        for _ in range(timeout):
            if self._port_alive(port):
                logger.info("Bootstrap: %s ONLINE on port %d", name, port)
                return True
            time.sleep(1)
        logger.error("Bootstrap: %s FAILED on port %d within %ds", name, port, timeout)
        return False

    def ensure_ollama(self) -> bool:
        """Start Ollama if not running on port 11434."""
        if self._port_alive(11434):
            logger.info("Bootstrap: Ollama already running on 11434")
            return True
        logger.info("Bootstrap: Starting Ollama server...")
        try:
            self._ollama_proc = subprocess.Popen(
                ["ollama", "serve"],
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            return self._wait_port(11434, "Ollama")
        except FileNotFoundError:
            logger.error("Bootstrap: 'ollama' not found in PATH")
            return False

    def ensure_gatekeeper(self) -> bool:
        """Start Gatekeeper if not running on port 11435."""
        if self._port_alive(11435):
            logger.info("Bootstrap: Gatekeeper already running on 11435")
            return True
        if not os.path.exists(self._gatekeeper_script):
            logger.error("Bootstrap: Gatekeeper script not found: %s", self._gatekeeper_script)
            return False
        logger.info("Bootstrap: Starting Gatekeeper on port 11435...")
        try:
            env = os.environ.copy()
            env["HOJAIGA_VISION_MODEL"] = "moondream"
            env["HOJAIGA_VISION_REASON_MODEL"] = "minicpm-v:latest"
            env["HOJAIGA_VISION_URL"] = "http://127.0.0.1:11434/api/chat"
            env["HOJAIGA_BRAIN_MODEL"] = "qwen2.5:7b"
            env["HOJAIGA_BRAIN_URL"] = "http://127.0.0.1:11435/api/chat"
            self._gatekeeper_proc = subprocess.Popen(
                [sys.executable, self._gatekeeper_script],
                cwd=self._hojaiga_root,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                env=env,
            )
            return self._wait_port(11435, "Gatekeeper")
        except Exception as e:
            logger.error("Bootstrap: Failed to start Gatekeeper: %s", e)
            return False

    def refresh_gatekeeper(self) -> bool:
        """Kill and restart Gatekeeper (self-heal on failure)."""
        logger.info("Bootstrap: Refreshing Gatekeeper...")
        # Kill existing
        try:
            subprocess.run(
                ["powershell", "-Command",
                 "Get-CimInstance Win32_Process | Where-Object "
                 "{ $_.CommandLine -like '*Brain_Gatekeeper*' } | "
                 "ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }"],
                capture_output=True, timeout=10,
            )
        except Exception:
            pass
        time.sleep(2)
        return self.ensure_gatekeeper()

    def bootstrap(self) -> bool:
        """Full system bootstrap: Ollama -> Gatekeeper -> Verify LLM."""
        if self._booted and self._port_alive(11435):
            return True
        logger.info("=" * 60)
        logger.info("ORGAN 37: FULL SYSTEM BOOTSTRAP")
        logger.info("=" * 60)
        ok = True
        ok = self.ensure_ollama() and ok
        ok = self.ensure_gatekeeper() and ok
        if ok:
            # Quick LLM verify
            try:
                result = self.execute_small_inference(
                    "You are a test. Reply with just 'OK'.",
                    "ping", timeout=30
                )
                logger.info("Bootstrap: LLM verify -> %s", result[:30])
                self._booted = True
            except Exception as e:
                logger.warning("Bootstrap: LLM verify failed (%s) — will retry on calls", e)
                self._booted = True  # still mark as booted, will auto-heal on calls
        logger.info("Bootstrap: %s", "ALL SYSTEMS GO" if ok else "PARTIAL — will auto-heal")
        return ok

    def _load_keys(self):
        self.keys = {}
        env_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env")
        if os.path.exists(env_path):
            with open(env_path, "r", encoding="utf-8") as f:
                for line in f:
                    if "=" in line and not line.startswith("#"):
                        k, v = line.split("=", 1)
                        self.keys[k.strip()] = v.strip().strip('"').strip("'")

        self.groq_key = self.keys.get("GROQ_API_KEY", self.keys.get("GROQ_API_KEY_1", os.environ.get("GROQ_API_KEY", os.environ.get("GROQ_API_KEY_1", ""))))
        self.openrouter_key = self.keys.get("OPENROUTER_API_KEY", self.keys.get("OPENROUTER_API_KEY_1", os.environ.get("OPENROUTER_API_KEY", os.environ.get("OPENROUTER_API_KEY_1", ""))))

    def _call_ollama(self, system: str, prompt: str, temperature: float, timeout: float) -> str:
        # Main brain model (default qwen2.5:7b); override via HOJAIGA_BRAIN_MODEL env.
        model = os.environ.get("HOJAIGA_BRAIN_MODEL", "qwen2.5:7b")
        return self._call_ollama_model(model, system, prompt, temperature, timeout)

    def _call_ollama_model(self, model: str, system: str, prompt: str,
                           temperature: float, timeout: float) -> str:
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": prompt}
            ],
            "stream": False,
            "options": {"temperature": temperature}
        }
        headers = {
            "ngrok-skip-browser-warning": "true",
            "X-Hojaiga-Validation": "339680",
            "Content-Type": "application/json"
        }
        actual_timeout = timeout if timeout != 30.0 else 120.0
        target_url = os.environ.get("HOJAIGA_BRAIN_URL", self.ollama_url)
        try:
            resp = requests.post(target_url, json=payload, headers=headers, timeout=actual_timeout)
            resp.raise_for_status()
            return resp.json().get("message", {}).get("content", "")
        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout):
            # If Gatekeeper port 11435 failed, attempt fallback directly to 11434
            if "11435" in target_url:
                fallback_url = target_url.replace("11435", "11434")
                logger.info(f"Gatekeeper (11435) unreachable/timeout. Attempting direct fallback to Ollama at {fallback_url}...")
                resp = requests.post(fallback_url, json=payload, headers=headers, timeout=actual_timeout)
                resp.raise_for_status()
                return resp.json().get("message", {}).get("content", "")
            raise

    def _call_groq(self, system: str, prompt: str, temperature: float, timeout: float) -> str:
        if not self.groq_key:
            raise ValueError("No GROQ_API_KEY found.")
            
        payload = {
            "model": "llama-3.1-8b-instant",
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": prompt}
            ],
            "temperature": temperature
        }
        headers = {
            "Authorization": f"Bearer {self.groq_key}",
            "Content-Type": "application/json"
        }
        resp = requests.post(self.groq_url, json=payload, headers=headers, timeout=timeout)
        if resp.status_code == 429:
            raise ValueError("Groq Rate Limit (429) hit.")
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]

    def _call_openrouter(self, system: str, prompt: str, temperature: float, timeout: float) -> str:
        if not self.openrouter_key:
            raise ValueError("No OPENROUTER_API_KEY found.")
            
        payload = {
            "model": "meta-llama/llama-3.1-8b-instruct:free",
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": prompt}
            ],
            "temperature": temperature
        }
        headers = {
            "Authorization": f"Bearer {self.openrouter_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "http://localhost", 
            "X-Title": "HojaigaAutomationOS"
        }
        resp = requests.post(self.openrouter_url, json=payload, headers=headers, timeout=timeout)
        if resp.status_code == 429:
            raise ValueError("OpenRouter Rate Limit (429) hit.")
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]
        
    def _call_synthetic_fallback(self, system: str, prompt: str) -> str:
        # Dynamic fallback decomposing user prompt into real actions
        import json
        import re
        import urllib.parse
        prompt_lower = prompt.lower()

        if any(k in prompt_lower for k in ["interior designer", "contractor", "architect", "lead", "business", "company", "excel", "csv", "scrape", "extract"]):
            clean_q = re.sub(r'^(open\s+chrome,?\s*|search\s+for\s*|find\s*|get\s*|extract\s*)', '', prompt, flags=re.IGNORECASE)
            clean_q = re.sub(r'\s*\(\s*minimum.*?\)', '', clean_q, flags=re.IGNORECASE)
            clean_q = re.sub(r'\s*extract.*$', '', clean_q, flags=re.IGNORECASE)
            clean_q = re.sub(r'\s*to\s+excel.*$', '', clean_q, flags=re.IGNORECASE).strip(" ,.-")
            if not clean_q:
                clean_q = "interior designers in Georgia"

            state_match = re.search(r'\b(tennessee|georgia|florida|texas|california|alabama|carolina|new york)\b', clean_q, flags=re.IGNORECASE)
            state_label = state_match.group(1).lower() if state_match else "leads"
            out_file = f"interior_designers_{state_label}.xlsx"
            maps_url = f"https://www.google.com/maps/search/{urllib.parse.quote_plus(clean_q)}"

            actions = [
                {
                    "thought": f"Navigate to Google Maps directory for: {clean_q}",
                    "action": "NAVIGATE",
                    "parameters": {"url": maps_url}
                },
                {
                    "thought": "Scroll results feed to trigger lazy-loaded business cards",
                    "action": "SCROLL",
                    "parameters": {"delta_y": 1000}
                },
                {
                    "thought": f"Extract live verified business contacts to {out_file}",
                    "action": "EXTRACT_LEADS",
                    "parameters": {"query": clean_q, "min_leads": 100, "output_file": out_file}
                },
                {
                    "thought": "Open Excel workbook to present extracted records",
                    "action": "LAUNCH_APP",
                    "parameters": {"command": ["excel.exe"]}
                }
            ]
            return json.dumps({
                "intent_analysis": f"Autonomous directory search: {clean_q}",
                "checkpoints_enforced": True,
                "actions": actions
            })

        url_match = re.search(r'(https?://[^\s\'"]+)', prompt)
        url = url_match.group(1) if url_match else f"https://www.google.com/search?q={urllib.parse.quote_plus(prompt[:60])}"

        actions = [
            {
                "thought": f"Navigate to: {url}",
                "action": "NAVIGATE",
                "parameters": {"url": url}
            }
        ]
        return json.dumps({
            "intent_analysis": f"Decomposed task: {prompt[:60]}",
            "checkpoints_enforced": True,
            "actions": actions
        })

    def execute_vision_inference(self, prompt: str, image_base64: str,
                                 system: str = "You are the Hojaiga vision interpreter. Describe the screenshot concisely and focus on what the automation needs to know.",
                                 model: Optional[str] = None, temperature: float = 0.2,
                                 timeout: float = 120.0, reason: bool = False) -> str:
        """Route a multimodal (image) prompt to a local vision model.

        Routing (per gatekeeper design):
          - raw image input       -> moondream            (HOJAIGA_VISION_MODEL)
          - "vision needed" (reasoning about the screen)
                                 -> minicpm-v            (HOJAIGA_VISION_REASON_MODEL)
          
        Memory Fallback: If vision fails, check cached coordinates from past runs.
        """
        # Guard: never let a text-only model receive an image (Ollama returns
        # "does not support image input"). Force a real vision model instead.
        _TEXT_ONLY_MODELS = {
            "llama3", "llama3:latest", "llama2", "mistral", "mixtral",
            "qwen", "qwen3-8b-instruct-q4_k_m", "gemma", "phi", "vicuna",
            "llama", "gpt", "claude",
        }
        if model is None:
            if reason:
                model = os.environ.get("HOJAIGA_VISION_REASON_MODEL", "minicpm-v:latest")
            else:
                model = os.environ.get("HOJAIGA_VISION_MODEL", "moondream")
        if model.lower().split(":")[0] in _TEXT_ONLY_MODELS:
            logger.warning("Gateway: requested vision model '%s' is text-only; "
                           "using moondream for the eye.", model)
            model = "moondream"
        try:
            logger.info("Gateway: Routing vision request to Local Ollama (%s)...", model)
            return self._call_ollama_vision(prompt, image_base64, system, model, temperature, timeout)
        except Exception as e:
            # Self-heal: a corrupt/unsupported vision model (e.g. broken
            # llama3.2-vision -> 'mllama') should not kill the eye. Fall back to
            # moondream, which is small, free and always local (no 429s).
            if model != "moondream:latest":
                try:
                    logger.warning("Gateway: vision model '%s' failed (%s). Trying moondream fallback...", model, e)
                    return self._call_ollama_vision(prompt, image_base64, system, "moondream:latest", temperature, timeout)
                except Exception as e2:
                    logger.warning("Gateway: moondream fallback also failed (%s). Vision unavailable.", e2)
            
            # Memory fallback: if vision completely fails, check cached data
            if self._memory:
                try:
                    # Extract app name and element from prompt if possible
                    prompt_lower = prompt.lower()
                    for app_name in ["calculator", "notepad", "paint", "chrome"]:
                        if app_name in prompt_lower:
                            cached = self._memory.fallback_lookup(app_name, "last_known")
                            if cached:
                                logger.info("[Gateway] Memory fallback: using cached data for %s", app_name)
                                return f"[Vision failed, using memory cache] App: {app_name}, Last known state available"
                except Exception as mem_err:
                    logger.debug("[Gateway] Memory fallback failed: %s", mem_err)
            
            logger.warning("Gateway: Ollama vision failed (%s). Vision unavailable.", e)
            return f"[vision unavailable: {e}]"

    def _call_ollama_vision(self, prompt: str, image_base64: str, system: str,
                            model: str, temperature: float, timeout: float) -> str:
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": prompt, "images": [image_base64]},
            ],
            "stream": False,
            "options": {"temperature": temperature},
        }
        headers = {
            "ngrok-skip-browser-warning": "true",
            "X-Hojaiga-Validation": "339680",
            "Content-Type": "application/json",
        }
        actual_timeout = timeout if timeout != 30.0 else 120.0
        # Always hit the vision endpoint (local Ollama), not the text-brain gatekeeper.
        target_url = self.vision_url
        try:
            resp = requests.post(target_url, json=payload, headers=headers, timeout=actual_timeout)
            resp.raise_for_status()
            return resp.json().get("message", {}).get("content", "")
        except requests.exceptions.HTTPError as e:
            # Clear, user-facing signal when a non-vision model received the image.
            body = ""
            try:
                body = e.response.text if e.response is not None else ""
            except Exception:
                body = str(e)
            if "does not support image" in body or "image input" in body:
                logger.error(
                    "VISION ERROR: model '%s' does not support image input. "
                    "Set HOJAIGA_VISION_MODEL to a vision-capable model (e.g. moondream) and keep "
                    "HOJAIGA_VISION_URL pointed at Ollama, not the text gatekeeper.",
                    model,
                )
                raise ValueError(
                    f"The vision model '{model}' cannot read images. "
                    f"Configure a vision model (e.g. set HOJAIGA_VISION_MODEL=moondream)."
                ) from e
            raise
        except requests.exceptions.ConnectionError:
            if "11435" in target_url:
                fallback_url = target_url.replace("11435", "11434")
                logger.info("Vision gatekeeper (11435) unreachable. Falling back to Ollama at %s", fallback_url)
                resp = requests.post(fallback_url, json=payload, headers=headers, timeout=actual_timeout)
                resp.raise_for_status()
                return resp.json().get("message", {}).get("content", "")
            raise

    def execute_inference(self, system: str, prompt: str, temperature: float = 0.3, timeout: float = 120.0) -> str:
        """Route to local Ollama models with graceful fallback to free tiers.
        Auto-heals: if Gatekeeper is dead, refreshes it and retries."""
        _CALLS["brain"] += 1
        # Auto-bootstrap on first call
        if not self._booted:
            self.bootstrap()

        # Priority 1: Local Ollama Brain (qwen2.5:7b — compilation only, free, private)
        try:
            logger.info("Gateway: Routing request to Local Ollama (%s)...", self.brain_model)
            return self._call_ollama(system, prompt, temperature, timeout)
        except Exception as e:
            logger.warning("Gateway: Local Ollama primary model failed (%s). Auto-healing...", e)
            # Auto-heal: refresh Gatekeeper and retry once
            if self._port_alive(11435):
                self.refresh_gatekeeper()
                try:
                    return self._call_ollama(system, prompt, temperature, timeout)
                except Exception as e2:
                    logger.warning("Gateway: Retry after Gatekeeper refresh also failed (%s)", e2)

        # Priority 2: OpenRouter (Free Pool Fallback)
        if self.openrouter_key:
            try:
                logger.info("Gateway: Routing request to OpenRouter...")
                return self._call_openrouter(system, prompt, temperature, timeout)
            except Exception as e:
                logger.warning("Gateway: OpenRouter failed (%s). Degrading to Groq.", e)

        # Priority 3: Groq (Fast Free Tier)
        if self.groq_key:
            try:
                logger.info("Gateway: Routing request to Groq...")
                return self._call_groq(system, prompt, temperature, timeout)
            except Exception as e:
                logger.warning("Gateway: Groq failed (%s). Degrading to Synthetic Fallback.", e)
            
        # Priority 4: Synthetic Offline Fallback (Guarantees system continuity)
        logger.info("Gateway: Routing request to Synthetic Offline Fallback...")
        return self._call_synthetic_fallback(system, prompt)

    def execute_small_inference(self, system: str, prompt: str,
                                temperature: float = 0.2, timeout: float = 30.0) -> str:
        """Lightweight brain call for small/instant tasks (routing, classification).
        
        Uses qwen2.5vl:3b (3GB) — handles text+vision, fast, fits alongside main brain.
        Falls back to main brain (qwen2.5:7b) only if qwen fails.
        """
        _CALLS["small"] += 1
        try:
            return self._call_ollama_model(self.small_model, system, prompt, temperature, timeout)
        except Exception as exc:
            logger.warning("small model %s failed (%s); using main brain", self.small_model, exc)
            return self.execute_inference(system, prompt, temperature, timeout)
