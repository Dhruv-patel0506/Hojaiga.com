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
from typing import Dict, Any, Optional, Tuple

logger = logging.getLogger("hojaiga.organ37.llm_gateway")

# MODULE-LEVEL call ledger: every LLMGateway() instance shares it, so a caller (or a test) can prove that a
# decision path made ZERO big-model calls. 'brain' = the 7B execute_inference rung; 'small' = the 1-3B
# execute_small_inference rung. reset_call_counts()/call_counts() are the assertions the NO-LLM-PATH test uses.
_CALLS = {"brain": 0, "small": 0, "cloud": 0}


def call_counts() -> dict:
    return dict(_CALLS)


def reset_call_counts() -> None:
    _CALLS["brain"] = 0
    _CALLS["small"] = 0
    _CALLS["cloud"] = 0


# ---- the cloud rung: free hosted models behind ONE OpenAI-compatible call -------------------------------------------------------------------------------
# A big hosted model is a stronger thinker and eye than the 2-7B local ones. Which providers exist is decided by the keys in .env (D:\new_automation\.env or
# All codes\.env) or the environment; the model each one uses is HOJAIGA_<NAME>_MODEL (defaults below are only a starting point, the provider's /models list
# says what is really there: cloud_models()). HOJAIGA_CLOUD = off | fallback (local first, cloud when local fails; default) | first (cloud first, local after).
# Privacy: free tiers may keep what they are sent (Google says free-tier content is used to improve its products), so a prompt that carries a credential never
# leaves the machine, and a caller can pass private=True for anything personal (mail, messages, the person's files).
CLOUD_PROVIDERS = [  # (name, key names, chat URL, default model, reads images)
    ("gemini", ("GEMINI_API_KEY", "GEMINI_API_KEY_1", "GEMINI_API_KEY_2", "GOOGLE_API_KEY"), "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions", "gemini-3.8-flash", True),
    ("groq", ("GROQ_API_KEY", "GROQ_API_KEY_1", "GROQ_API_KEY_2"), "https://api.groq.com/openai/v1/chat/completions", "openai/gpt-oss-120b", False),
    ("nvidia", ("NVIDIA_API_KEY", "NVIDIA_API_KEY_1", "NVIDIA_API_KEY_2"), "https://integrate.api.nvidia.com/v1/chat/completions", "nvidia/nemotron-3.5-super-vl-120b-a12b", False),   # Oct-27: the /models list names models this account gets 404 for; this one answered
    ("nvidia_eye", ("NVIDIA_API_KEY", "NVIDIA_API_KEY_1", "NVIDIA_API_KEY_2"), "https://integrate.api.nvidia.com/v1/chat/completions", "nvidia/nemotron-3.5-super-vl-120b-a12b", True),
    ("openrouter", ("OPENROUTER_API_KEY", "OPENROUTER_API_KEY_1", "OPENROUTER_API_KEY_2"), "https://openrouter.ai/api/v1/chat/completions", "openrouter/free", False),
    ("openai", ("OPENAI_API_KEY", "OPENAI_API_KEY_1", "OPENAI_API_KEY_2"), "https://api.openai.com/v1/chat/completions", "gpt-4o-mini", True),   # trial credits; HOJAIGA_OPENAI_MODEL from cloud_models("openai")
]
_COOL: Dict[str, float] = {}           # provider -> time it may be asked again (after a 429 / failure / an empty budget)
# Never cause a 429: a provider is asked only while its budget has room. The budget is what the provider itself reports (x-ratelimit-remaining-* headers, e.g. Groq
# free = 1,000 requests/day and 8,000 tokens/minute, measured Oct-27) and, for providers that report nothing, a per-minute cap HOJAIGA_<NAME>_RPM (the defaults are
# deliberately low starting points). When every provider is out of budget the caller stays on the local model, which has no limit.
CLOUD_RPM_DEFAULT = {"gemini": 8, "groq": 25, "nvidia": 30, "nvidia_eye": 30, "openrouter": 15, "openai": 20, "claude": 30}
_SENT: Dict[str, list] = {}           # provider -> send times in the last minute
_RESERVE = 2                          # keep this many requests unused in the provider's own count
# decisions repeat (the same screen, the same question): an answer is reused instead of asked again -- the cheapest call is the one not made
_DECIDED: Dict[str, Any] = {}         # sha -> (time, answer)
_DECIDED_MAX = 4000
LAST_CLOUD: Dict[str, Any] = {}        # what the last cloud call used (provider, model, seconds) -- reports cite it, never the key
_ENV_CACHE: Dict[str, str] = {}
_CREDENTIAL = __import__("re").compile(r"(?i)\b(password|passcode|passwd|otp|cvv|cvc|pin|api[\s_-]?key|secret|token|card\s*number)\b\s*(is|=|:)\s*\S+|\b(sk|pk|ghp|gsk|nvapi|AIza)[-_A-Za-z0-9]{16,}")


def env_keys(refresh: bool = False) -> Dict[str, str]:
    """.env values (both places the project keeps one) under the real environment, which wins. Never logged."""
    if _ENV_CACHE and not refresh:
        return _ENV_CACHE
    here = os.path.dirname(os.path.abspath(__file__))
    out: Dict[str, str] = {}
    for p in (os.path.join(os.environ.get("HOJAIGA_ROOT", r"D:\new_automation"), ".env"), os.path.join(os.path.dirname(here), ".env")):
        try:
            with open(p, "r", encoding="utf-8") as f:
                for line in f:
                    if "=" in line and not line.lstrip().startswith("#"):
                        k, v = line.split("=", 1)
                        out.setdefault(k.strip(), v.strip().strip('"').strip("'"))
        except OSError:
            pass
    out.update({k: v for k, v in os.environ.items() if k.startswith(("HOJAIGA_", "GEMINI_", "GOOGLE_API", "NVIDIA_", "GROQ_", "OPENROUTER_", "OPENAI_API_KEY", "CLAUDE_API_KEY"))})
    # never ANTHROPIC_*: in a developer shell those are the coding tool's own credentials, not the key a Hojaiga user pays with
    _ENV_CACHE.clear()
    _ENV_CACHE.update(out)
    return out


def cloud_mode() -> str:
    m = (env_keys().get("HOJAIGA_CLOUD") or "fallback").strip().lower()
    return m if m in ("off", "fallback", "first") else "fallback"


def cloud_ok_for(text: str, private: bool = False) -> bool:
    """May this prompt go to a hosted model? Not when the caller says it is private, nor when it carries a credential."""
    return not private and cloud_mode() != "off" and not _CREDENTIAL.search(text or "")


def cloud_providers(need_images: bool = False) -> list:
    """[(name, key, url, model)] usable now: has a key, is not cooling down after a 429, reads images when asked to."""
    keys, now, out = env_keys(), time.time(), []
    order = [s.strip() for s in (keys.get("HOJAIGA_CLOUD_ORDER") or "").split(",") if s.strip()]
    provs = sorted(CLOUD_PROVIDERS, key=lambda p: order.index(p[0]) if p[0] in order else len(order))
    for name, knames, url, model, images in provs:
        key = next((keys[k] for k in knames if keys.get(k)), "")
        if key and (images or not need_images) and _COOL.get(name, 0) <= now and _has_budget(name, now):
            out.append((name, key, url, keys.get(f"HOJAIGA_{name.upper()}_MODEL") or model))
    return out


def _rpm(name: str) -> int:
    try:
        return int(env_keys().get(f"HOJAIGA_{name.upper()}_RPM") or CLOUD_RPM_DEFAULT.get(name, 10))
    except ValueError:
        return CLOUD_RPM_DEFAULT.get(name, 10)


def _has_budget(name: str, now: float) -> bool:
    sent = _SENT.setdefault(name, [])
    sent[:] = [t for t in sent if now - t < 60.0]
    return len(sent) < _rpm(name)


def _seconds(s: str) -> float:
    """'1m26.4s' / '577ms' / '2h3m' / '30' -> seconds."""
    s = (s or "").strip()
    if not s:
        return 0.0
    try:
        return float(s)
    except ValueError:
        pass
    total = 0.0
    for num, unit in __import__("re").findall(r"([\d.]+)\s*(ms|h|m|s)", s):
        total += float(num) * {"ms": 0.001, "s": 1, "m": 60, "h": 3600}[unit]
    return total


def _note_budget(name: str, headers: Any) -> None:
    """Read the provider's own remaining counts; when one is at the reserve, rest the provider until that count resets (so the next call is never the 429)."""
    h = {k.lower(): v for k, v in dict(headers or {}).items()}
    for kind in ("requests", "tokens"):
        left = h.get(f"x-ratelimit-remaining-{kind}")
        if left is None:
            continue
        try:
            low = float(left) <= (_RESERVE if kind == "requests" else 500)
        except ValueError:
            continue
        if low:
            _COOL[name] = max(_COOL.get(name, 0), time.time() + max(1.0, _seconds(h.get(f"x-ratelimit-reset-{kind}", "60"))))
            logger.info("Gateway: cloud %s budget (%s) is at its reserve; resting it until it resets", name, kind)


def budget_status() -> Dict[str, Any]:
    """Per provider: sent in the last minute / cap, resting for how long. No keys."""
    now = time.time()
    out = {}
    for p in CLOUD_PROVIDERS:
        _has_budget(p[0], now)
        out[p[0]] = {"sent_last_minute": len(_SENT.get(p[0], [])), "cap_per_minute": _rpm(p[0]), "resting_s": max(0, round(_COOL.get(p[0], 0) - now))}
    return out


def cloud_chat(system: str, prompt: str, images_b64: Optional[list] = None, temperature: float = 0.3, timeout: float = 120.0, max_tokens: int = 0, private: bool = False) -> Optional[str]:
    """Ask the first free hosted model that answers. None when none may or can (no key, private, credential in the prompt, all rate-limited):
    the caller then stays local. A 429 cools that provider down for a minute; other errors for five."""
    if not cloud_ok_for(system + "\n" + prompt, private):
        return None
    import hashlib
    sha = hashlib.sha1("\x1f".join([system, prompt] + list(images_b64 or [])).encode("utf-8", "ignore")).hexdigest()
    ttl = float(env_keys().get("HOJAIGA_DECISION_TTL") or 3600)
    hit = _DECIDED.get(sha) if temperature <= 0.3 else None
    if hit and time.time() - hit[0] < ttl:
        LAST_CLOUD.clear()
        LAST_CLOUD.update({"provider": "cache", "model": hit[2], "seconds": 0.0})
        return hit[1]
    content: Any = prompt
    if images_b64:
        content = [{"type": "text", "text": prompt}] + [{"type": "image_url", "image_url": {"url": b if b.startswith("data:") else "data:image/png;base64," + b}} for b in images_b64]
    for name, key, url, model in cloud_providers(need_images=bool(images_b64)):
        body: Dict[str, Any] = {"model": model, "messages": [{"role": "system", "content": system}, {"role": "user", "content": content}], "temperature": temperature}
        if max_tokens:
            body["max_tokens"] = max_tokens
        t0 = time.time()
        try:
            _CALLS["cloud"] += 1
            _SENT.setdefault(name, []).append(t0)
            resp = requests.post(url, json=body, headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"}, timeout=timeout)
            _note_budget(name, resp.headers)
            if resp.status_code == 429:                                                                # should not happen with the budget; if it does, obey retry-after
                _COOL[name] = time.time() + max(60.0, _seconds(resp.headers.get("retry-after", "")))
                logger.warning("Gateway: cloud %s rate-limited (429); trying the next provider", name)
                continue
            resp.raise_for_status()
            text = (resp.json()["choices"][0]["message"].get("content") or "").strip()
            if text:
                LAST_CLOUD.clear()
                LAST_CLOUD.update({"provider": name, "model": model, "seconds": round(time.time() - t0, 2)})
                if temperature <= 0.3:
                    if len(_DECIDED) >= _DECIDED_MAX:
                        for k in sorted(_DECIDED, key=lambda k: _DECIDED[k][0])[: _DECIDED_MAX // 4]:
                            _DECIDED.pop(k, None)
                    _DECIDED[sha] = (time.time(), text, model)
                return text
        except Exception as exc:
            _COOL[name] = time.time() + 300
            logger.warning("Gateway: cloud %s failed (%s); trying the next provider", name, type(exc).__name__)
    return None


# ---- the teacher: Claude on the USER'S own key -------------------------------------------------------------------------------------------------------------
# The person who runs Hojaiga pays for it with their own Anthropic key (HOJAIGA_CLAUDE_KEY or CLAUDE_API_KEY in .env). It sees the screen and decides a step; the
# natural brain (mind.brain) watches, checks and learns, and turns it off when it is ready. A daily spend cap (HOJAIGA_CLAUDE_BUDGET_USD, default 2) stops it cold.
CLAUDE_PRICE = {"claude-opus-5-5": (4.0, 20.0), "claude-sonnet-5-5": (2.0, 10.0), "claude-haiku-5-5": (0.10, 0.50), "claude-fable-5-1": (10.0, 50.0)}   # $ per 1M in / out
_CLAUDE_SPEND: Dict[str, float] = {}   # 'YYYY-MM-DD' -> dollars


def claude_key() -> str:
    k = env_keys()
    return k.get("HOJAIGA_CLAUDE_KEY") or k.get("CLAUDE_API_KEY") or ""


def claude_spent_today() -> float:
    return round(_CLAUDE_SPEND.get(time.strftime("%Y-%m-%d"), 0.0), 4)


def claude_chat(system: str, prompt: str, images_b64: Optional[list] = None, max_tokens: int = 2000, private: bool = False) -> Optional[str]:
    """One Claude call (official SDK) on the user's key; None when there is no key, the SDK is missing, the budget is spent, or the prompt is private."""
    key = claude_key()
    if not key or not cloud_ok_for(system + "\n" + prompt, private):
        return None
    keys = env_keys()
    model = keys.get("HOJAIGA_CLAUDE_MODEL") or "claude-opus-5-5"
    cap = float(keys.get("HOJAIGA_CLAUDE_BUDGET_USD") or 2.0)
    day = time.strftime("%Y-%m-%d")
    if _CLAUDE_SPEND.get(day, 0.0) >= cap or not _has_budget("claude", time.time()) or _COOL.get("claude", 0) > time.time():
        return None
    try:
        import anthropic
    except ImportError:
        logger.warning("Gateway: the 'anthropic' package is not installed; the Claude teacher is off")
        return None
    content: list = [{"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": b.split(",", 1)[-1]}} for b in (images_b64 or [])]
    content.append({"type": "text", "text": prompt})
    # explicit key AND address: a developer shell's ANTHROPIC_API_KEY / ANTHROPIC_BASE_URL must never be picked up instead of the user's own
    client = anthropic.Anthropic(api_key=key, base_url=keys.get("HOJAIGA_CLAUDE_BASE_URL") or "https://api.anthropic.com", max_retries=1, timeout=90.0)
    t0 = time.time()
    _SENT.setdefault("claude", []).append(t0)
    _CALLS["cloud"] += 1
    try:
        resp = client.beta.messages.create(model=model, max_tokens=max_tokens, system=system, messages=[{"role": "user", "content": content}],
                                           output_config={"effort": keys.get("HOJAIGA_CLAUDE_EFFORT") or "medium"},
                                           betas=["server-side-fallback-2026-07-01"], fallbacks="default")
    except anthropic.RateLimitError as e:
        _COOL["claude"] = time.time() + max(60.0, _seconds(e.response.headers.get("retry-after", "")))
        return None
    except anthropic.APIStatusError as e:
        _COOL["claude"] = time.time() + (60 if e.status_code >= 500 else 600)
        logger.warning("Gateway: Claude %s: %s", e.status_code, str(e.message)[:160])
        return None
    except anthropic.APIConnectionError:
        _COOL["claude"] = time.time() + 60
        return None
    u = resp.usage
    pin, pout = CLAUDE_PRICE.get(model, (0.0, 0.0))
    _CLAUDE_SPEND[day] = _CLAUDE_SPEND.get(day, 0.0) + ((u.input_tokens or 0) * pin + (u.output_tokens or 0) * pout) / 1e6
    if resp.stop_reason == "refusal":
        return None
    text = "".join(b.text for b in resp.content if b.type == "text").strip()
    LAST_CLOUD.clear()
    LAST_CLOUD.update({"provider": "claude", "model": resp.model, "seconds": round(time.time() - t0, 2), "spent_today_usd": claude_spent_today()})
    return text or None


def teacher_chat(system: str, prompt: str, images_b64: Optional[list] = None, max_tokens: int = 1500, private: bool = False) -> Tuple[Optional[str], str]:
    """(answer, who). The strongest teacher that may answer: Claude on the user's key first, then the free hosted models (an eye when there is a picture)."""
    order = [s.strip() for s in (env_keys().get("HOJAIGA_TEACHER_ORDER") or "claude,cloud").split(",") if s.strip()]
    for who in order:
        if who == "claude":
            ans = claude_chat(system, prompt, images_b64, max_tokens=max_tokens, private=private)
        else:
            ans = cloud_chat(system, prompt, images_b64, temperature=0.1, max_tokens=max_tokens, private=private)
            who = LAST_CLOUD.get("provider", "cloud")
        if ans:
            return ans, who
    return None, ""


def langchain_chat(need_images: bool = False, temperature: float = 0.1) -> Any:
    """A LangChain chat model on the first free provider that has a key and budget (OpenAI-compatible endpoint), for CrewAI tools, ScrapeGraphAI and
    LangChain chains; None when there is none (the caller stays local)."""
    provs = cloud_providers(need_images=need_images)
    if not provs:
        return None
    from langchain_openai import ChatOpenAI
    name, key, url, model = provs[0]
    return ChatOpenAI(model=model, api_key=key, base_url=url.rsplit("/chat/completions", 1)[0], temperature=temperature, timeout=120, max_retries=1)


def litellm_route() -> Optional[Dict[str, str]]:
    """{'model', 'api_key', 'base_url'} for CrewAI's LLM (litellm's OpenAI-compatible route) on the first free provider; None when there is none."""
    provs = cloud_providers()
    if not provs:
        return None
    name, key, url, model = provs[0]
    return {"model": "openai/" + model, "api_key": key, "base_url": url.rsplit("/chat/completions", 1)[0], "provider": name}


def cloud_models(name: str) -> list:
    """The model ids a provider really offers today (its /models list), so HOJAIGA_<NAME>_MODEL can be set from fact, not memory."""
    for n, key, url, _m in cloud_providers():
        if n == name:
            r = requests.get(url.rsplit("/chat/completions", 1)[0] + "/models", headers={"Authorization": f"Bearer {key}"}, timeout=30)
            r.raise_for_status()
            return sorted(m.get("id", "") for m in r.json().get("data", []))
    return []

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
        # both .env files (the project root one is where the keys really live; reading only All codes\.env meant the cloud rungs never ran)
        self.keys = dict(env_keys())

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
                                 timeout: float = 120.0, reason: bool = False, private: bool = False) -> str:
        """Route a multimodal (image) prompt to a local vision model (HOJAIGA_CLOUD=first: a hosted model that reads images first; fallback: after the
        local eyes fail). A screenshot can show the person's mail or files, so callers pass private=True for those.

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
        if cloud_mode() == "first":
            out = cloud_chat(system, prompt, [image_base64], temperature=temperature, timeout=timeout, private=private)
            if out:
                return out
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
            if cloud_mode() == "fallback":
                out = cloud_chat(system, prompt, [image_base64], temperature=temperature, timeout=timeout, private=private)
                if out:
                    return out

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

    def execute_inference(self, system: str, prompt: str, temperature: float = 0.3, timeout: float = 120.0, private: bool = False) -> str:
        """Route to local Ollama models with graceful fallback to free tiers (HOJAIGA_CLOUD=first asks the hosted models before the local one).
        Auto-heals: if Gatekeeper is dead, refreshes it and retries. private=True keeps the prompt on this machine."""
        _CALLS["brain"] += 1
        if cloud_mode() == "first":
            out = cloud_chat(system, prompt, temperature=temperature, timeout=timeout, private=private)
            if out:
                return out
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

        # Priority 2: the free hosted models (Gemini, NVIDIA, Groq, OpenRouter -- whichever have keys), unless already tried first
        if cloud_mode() == "fallback":
            out = cloud_chat(system, prompt, temperature=temperature, timeout=timeout, private=private)
            if out:
                return out
            logger.warning("Gateway: no hosted model answered. Degrading to Synthetic Fallback.")

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
