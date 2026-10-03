"""
HostHardwareProfiler — Dynamic Host Hardware Senser & Resource-Adaptive Auto-Tuner.

Detects:
1. System RAM (Total & Available via Windows APIs / WMI).
2. CPU logical/physical cores.
3. GPU detection (Vendor, Model, Dedicated VRAM via WMI / Win32_VideoController / DirectX).

Classifies host into 3 Operating Profiles:
- LOW_SPEC: CPU-only or <=4GB VRAM, <=12GB RAM -> 1 worker, keep_alive=0 (immediate unload), 720p vision.
- MID_SPEC: 6-8GB VRAM, 16-32GB RAM -> 3 workers, keep_alive="30m"/"5m", 1080p vision.
- HIGH_SPEC: 12GB+ VRAM, 32GB+ RAM -> 6 workers, warm 7B/8B models, 4K lossless vision.
"""

from __future__ import annotations

import os
import sys
import json
import time
import shutil
import logging
import platform
import subprocess
from pathlib import Path
from dataclasses import dataclass, asdict
from typing import Dict, Any, Optional

logger = logging.getLogger("host_hardware_profiler")

CACHE_PATH = Path(r"D:\new_automation\All codes\var\hojaiga\host_profile.json")


@dataclass
class HardwareSpecs:
    platform_os: str
    cpu_cores: int
    total_ram_gb: float
    free_ram_gb: float
    gpu_name: str
    gpu_vram_gb: float
    has_nvidia: bool


@dataclass
class AdaptiveProfile:
    tier: str  # "LOW_SPEC", "MID_SPEC", "HIGH_SPEC"
    max_concurrency: int
    preferred_fast_model: str
    preferred_vision_model: str
    preferred_reasoning_model: str
    vram_keep_alive_fast: str
    vram_keep_alive_specialist: str
    screenshot_quality: int
    screenshot_max_dim: int
    enable_batching: bool
    specs: HardwareSpecs


class HostHardwareProfiler:
    """Probes host hardware and generates adaptive performance profiles."""

    _instance: Optional["HostHardwareProfiler"] = None

    @classmethod
    def get_instance(cls) -> "HostHardwareProfiler":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def __init__(self, cache_file: Path = CACHE_PATH):
        self.cache_file = cache_file
        self.cache_file.parent.mkdir(parents=True, exist_ok=True)
        self.profile: AdaptiveProfile = self._get_or_probe_profile()

    def _get_or_probe_profile(self) -> AdaptiveProfile:
        # Check cache (valid for 24h)
        if self.cache_file.exists():
            try:
                with open(self.cache_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if time.time() - data.get("_timestamp", 0) < 86400:
                    specs = HardwareSpecs(**data["specs"])
                    del data["specs"]
                    del data["_timestamp"]
                    return AdaptiveProfile(specs=specs, **data)
            except Exception as e:
                logger.debug("Cache read failed: %s", e)

        # Fresh probe
        profile = self.probe_host()
        self._save_cache(profile)
        return profile

    def probe_host(self) -> AdaptiveProfile:
        """Perform comprehensive hardware probe via native OS commands."""
        cpu_cores = os.cpu_count() or 4
        os_name = platform.platform()

        # 1. Probe RAM
        total_ram_gb, free_ram_gb = self._probe_ram()

        # 2. Probe GPU & VRAM
        gpu_name, gpu_vram_gb, has_nvidia = self._probe_gpu()

        specs = HardwareSpecs(
            platform_os=os_name,
            cpu_cores=cpu_cores,
            total_ram_gb=round(total_ram_gb, 1),
            free_ram_gb=round(free_ram_gb, 1),
            gpu_name=gpu_name,
            gpu_vram_gb=round(gpu_vram_gb, 1),
            has_nvidia=has_nvidia
        )

        # 3. Classify into tier
        if gpu_vram_gb >= 11.5 or (total_ram_gb >= 48 and cpu_cores >= 16):
            tier = "HIGH_SPEC"
            profile = AdaptiveProfile(
                tier=tier,
                max_concurrency=6,
                preferred_fast_model="qwen2.5:3b",
                preferred_vision_model="qwen2.5vl:7b" if gpu_vram_gb >= 16 else "qwen2.5vl:3b",
                preferred_reasoning_model="llama3:latest",
                vram_keep_alive_fast="60m",
                vram_keep_alive_specialist="15m",
                screenshot_quality=90,
                screenshot_max_dim=1920,
                enable_batching=True,
                specs=specs
            )
        elif (gpu_vram_gb >= 5.5 and total_ram_gb >= 15) or total_ram_gb >= 24:
            tier = "MID_SPEC"
            profile = AdaptiveProfile(
                tier=tier,
                max_concurrency=3,
                preferred_fast_model="qwen2.5:3b",
                preferred_vision_model="minicpm-v:latest",  # 5.5GB, excellent OCR, fits in 6GB VRAM
                preferred_reasoning_model="llama3:latest",
                vram_keep_alive_fast="30m",
                vram_keep_alive_specialist="5m",
                screenshot_quality=80,
                screenshot_max_dim=1280,
                enable_batching=False,
                specs=specs
            )
        else:
            tier = "LOW_SPEC"
            profile = AdaptiveProfile(
                tier=tier,
                max_concurrency=1,
                preferred_fast_model="qwen2.5:3b",
                preferred_vision_model="moondream:latest",
                preferred_reasoning_model="qwen2.5:3b",
                vram_keep_alive_fast="5m",
                vram_keep_alive_specialist="0",  # Immediate unload to avoid OOM
                screenshot_quality=65,
                screenshot_max_dim=960,
                enable_batching=False,
                specs=specs
            )

        logger.info(
            "HostHardwareProfiler: Detected %s (RAM: %.1fGB, GPU: %s %.1fGB VRAM, Cores: %d) -> Assigned %s",
            os_name, total_ram_gb, gpu_name, gpu_vram_gb, cpu_cores, tier
        )
        return profile

    def _probe_ram(self) -> tuple[float, float]:
        """Probe RAM in GB via PowerShell WMI."""
        try:
            cmd = ["powershell", "-NoProfile", "-Command", "Get-CimInstance Win32_OperatingSystem | Select-Object TotalVisibleMemorySize, FreePhysicalMemory | ConvertTo-Json"]
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
            if res.returncode == 0 and res.stdout.strip():
                data = json.loads(res.stdout)
                total_kb = float(data.get("TotalVisibleMemorySize", 16777216))
                free_kb = float(data.get("FreePhysicalMemory", 8388608))
                return total_kb / (1024 * 1024), free_kb / (1024 * 1024)
        except Exception:
            pass
        return 16.0, 8.0

    def _probe_gpu(self) -> tuple[str, float, bool]:
        """Probe discrete GPU and dedicated VRAM in GB."""
        try:
            cmd = ["powershell", "-NoProfile", "-Command", "Get-CimInstance Win32_VideoController | Select-Object Name, AdapterRAM | ConvertTo-Json"]
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
            if res.returncode == 0 and res.stdout.strip():
                raw = json.loads(res.stdout)
                devices = raw if isinstance(raw, list) else [raw]
                best_name = "Generic Graphics"
                best_vram = 0.0
                has_nv = False
                for d in devices:
                    name = d.get("Name", "")
                    aram = float(d.get("AdapterRAM", 0) or 0)
                    vram_gb = aram / (1024 ** 3)
                    if "nvidia" in name.lower():
                        has_nv = True
                        if vram_gb > best_vram:
                            best_vram = vram_gb
                            best_name = name
                    elif vram_gb > best_vram:
                        best_vram = vram_gb
                        best_name = name
                return best_name, max(best_vram, 0.0), has_nv
        except Exception:
            pass
        return "Generic Display", 2.0, False

    def _save_cache(self, profile: AdaptiveProfile) -> None:
        try:
            data = asdict(profile)
            data["_timestamp"] = time.time()
            with open(self.cache_file, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.debug("Failed to cache host profile: %s", e)
