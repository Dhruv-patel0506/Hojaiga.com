"""Professional Drawing Engine - Local AI Art Integration.

Uses Stable Diffusion, ControlNet, and professional graphics libraries
for high-quality local drawing without any external APIs.
"""
from __future__ import annotations

import os
import time
import json
import requests
import tempfile
from pathlib import Path
from typing import Any, Optional, List, Dict, Tuple
from dataclasses import dataclass
from enum import Enum

try:
    import torch
    from diffusers import StableDiffusionXLControlNetPipeline, ControlNetModel
    from diffusers.utils import load_image
    from PIL import Image, ImageDraw, ImageFont
    import cv2
    import numpy as np
    HAS_PROFESSIONAL_DRAWING = True
except ImportError as e:
    HAS_PROFESSIONAL_DRAWING = False
    print(f"[Professional Drawing] Dependencies not available: {e}")


class DrawingStyle(Enum):
    """Professional drawing styles."""
    REALISTIC = "realistic"
    ARTISTIC = "artistic"
    SCIENTIFIC = "scientific"
    MEDICAL = "medical"
    TECHNICAL = "technical"
    SKETCH = "sketch"
    WATERCOLOR = "watercolor"
    OIL_PAINTING = "oil_painting"
    DIGITAL_ART = "digital_art"


class SubjectType(Enum):
    """Subject categories for specialized handling."""
    ANATOMICAL = "anatomical"
    BIOLOGICAL = "biological"
    MECHANICAL = "mechanical"
    ARCHITECTURAL = "architectural"
    ABSTRACT = "abstract"
    LANDSCAPE = "landscape"
    PORTRAIT = "portrait"
    DIAGRAM = "diagram"


@dataclass
class DrawingRequest:
    """Request for professional drawing."""
    prompt: str
    style: DrawingStyle
    subject_type: SubjectType
    width: int = 1024
    height: int = 1024
    steps: int = 30
    guidance_scale: float = 7.5
    seed: Optional[int] = None
    negative_prompt: str = "low quality, blurry, distorted, deformed, ugly"
    control_image: Optional[str] = None  # Path to control image
    controlnet_type: Optional[str] = None  # "canny", "depth", "pose", "scribble"


@dataclass
class DrawingResult:
    """Result of professional drawing."""
    success: bool
    image_path: Optional[str]
    processing_time_ms: float
    style: DrawingStyle
    error_message: Optional[str] = None
    metadata: Dict[str, Any] = None


class ProfessionalDrawingEngine:
    """Local professional drawing engine using Stable Diffusion + ControlNet.
    
    Completely local, no external APIs, no rate limits.
    Optimized for NVIDIA RTX 3050 (6GB VRAM) with 32GB RAM.
    """
    
    def __init__(self, sd_webui_url: str = "http://127.0.0.1:7860", 
                 use_cpu: bool = False,
                 optimize_for_low_vram: bool = True):
        """
        Initialize with connection to local Stable Diffusion WebUI.
        
        Args:
            sd_webui_url: URL of local AUTOMATIC1111 WebUI
            use_cpu: Force CPU usage (slower but no VRAM limit)
            optimize_for_low_vram: Optimize for 6GB VRAM (RTX 3050)
        """
        self.sd_webui_url = sd_webui_url
        self.use_cpu = use_cpu
        self.optimize_for_low_vram = optimize_for_low_vram
        self.is_available = False
        self.drawing_history: List[DrawingResult] = []
        
        # Optimized settings for RTX 3050 (6GB VRAM)
        if optimize_for_low_vram:
            self.default_width = 512
            self.default_height = 512
            self.default_steps = 20
            self.default_guidance = 7.0
        else:
            self.default_width = 1024
            self.default_height = 1024
            self.default_steps = 30
            self.default_guidance = 7.5
        
        # Check if WebUI is available
        self._check_availability()
    
    def _check_availability(self) -> bool:
        """Check if local Stable Diffusion WebUI is running."""
        try:
            response = requests.get(f"{self.sd_webui_url}/sdapi/v1/sd-models", timeout=5)
            self.is_available = response.status_code == 200
            if self.is_available:
                print("[Professional Drawing] Connected to local Stable Diffusion WebUI")
            return self.is_available
        except Exception as e:
            print(f"[Professional Drawing] Stable Diffusion WebUI not available: {e}")
            return False
    
    def generate_drawing(self, request: DrawingRequest) -> DrawingResult:
        """
        Generate professional drawing using local Stable Diffusion.
        
        Args:
            request: DrawingRequest with prompt, style, and parameters
            
        Returns:
            DrawingResult with image path and metadata
        """
        if not self.is_available:
            return DrawingResult(
                success=False,
                image_path=None,
                processing_time_ms=0.0,
                style=request.style,
                error_message="Stable Diffusion WebUI not available"
            )
        
        start_time = time.time()
        
        try:
            # Apply optimized settings for low VRAM
            if self.optimize_for_low_vram:
                # Use SD 2.1 instead of SDXL for lower VRAM
                request.width = min(request.width, 512)
                request.height = min(request.height, 512)
                request.steps = min(request.steps, 20)
                request.guidance_scale = min(request.guidance_scale, 7.0)
            
            # Build style-specific prompt
            enhanced_prompt = self._build_enhanced_prompt(request)
            
            # Prepare payload for WebUI API
            payload = {
                "prompt": enhanced_prompt,
                "negative_prompt": request.negative_prompt,
                "width": request.width,
                "height": request.height,
                "steps": request.steps,
                "cfg_scale": request.guidance_scale,
                "seed": request.seed if request.seed else -1,
                "sampler_name": "DPM++ 2M Karras",
                "scheduler": "Karras"
            }
            
            # Force CPU if requested
            if self.use_cpu:
                payload["extra_generation_params"] = {
                    "device": "cpu"
                }
            
            # Add ControlNet if specified (only if not using CPU)
            if request.control_image and request.controlnet_type and not self.use_cpu:
                payload["alwayson_scripts"] = {
                    "controlnet": {
                        "args": [{
                            "input_image": self._encode_image(request.control_image),
                            "model": f"control_{request.controlnet_type}",
                            "module": request.controlnet_type,
                            "weight": 1.0
                        }]
                    }
                }
            
            # Send request to local WebUI
            response = requests.post(
                f"{self.sd_webui_url}/sdapi/v1/txt2img",
                json=payload,
                timeout=300  # 5 minute timeout
            )
            
            if response.status_code != 200:
                return DrawingResult(
                    success=False,
                    image_path=None,
                    processing_time_ms=(time.time() - start_time) * 1000,
                    style=request.style,
                    error_message=f"Stable Diffusion API error: {response.status_code}"
                )
            
            # Save image
            result = response.json()
            image_data = result.get("images", [])[0]
            image_bytes = bytes.fromstring(image_data)
            
            temp_dir = tempfile.mkdtemp()
            image_path = os.path.join(temp_dir, f"professional_drawing_{int(time.time())}.png")
            
            with open(image_path, "wb") as f:
                f.write(image_bytes)
            
            processing_time = (time.time() - start_time) * 1000
            
            result = DrawingResult(
                success=True,
                image_path=image_path,
                processing_time_ms=processing_time,
                style=request.style,
                metadata={
                    "seed": result.get("info", {}).get("seed"),
                    "parameters": result.get("info", {}),
                    "optimized_for_low_vram": self.optimize_for_low_vram,
                    "used_cpu": self.use_cpu
                }
            )
            
            self.drawing_history.append(result)
            return result
            
        except Exception as e:
            return DrawingResult(
                success=False,
                image_path=None,
                processing_time_ms=(time.time() - start_time) * 1000,
                style=request.style,
                error_message=f"Drawing generation failed: {e}"
            )
    
    def _build_enhanced_prompt(self, request: DrawingRequest) -> str:
        """Build enhanced prompt based on style and subject type."""
        style_prefixes = {
            DrawingStyle.REALISTIC: "photorealistic, highly detailed, 8k resolution, professional photography",
            DrawingStyle.ARTISTIC: "artistic, creative, expressive, bold colors, dynamic composition",
            DrawingStyle.SCIENTIFIC: "scientific illustration, accurate, detailed, clear labels, educational",
            DrawingStyle.MEDICAL: "medical illustration, anatomically accurate, professional, detailed, clean",
            DrawingStyle.TECHNICAL: "technical drawing, precise, clear lines, engineering standard",
            DrawingStyle.SKETCH: "pencil sketch, hand-drawn, artistic, rough, expressive",
            DrawingStyle.WATERCOLOR: "watercolor painting, soft colors, artistic, fluid, beautiful",
            DrawingStyle.OIL_PAINTING: "oil painting, rich colors, textured, classical, masterpiece",
            DrawingStyle.DIGITAL_ART: "digital art, modern, vibrant, detailed, professional"
        }
        
        subject_prefixes = {
            SubjectType.ANATOMICAL: "anatomical drawing, medically accurate, detailed structure",
            SubjectType.BIOLOGICAL: "biological illustration, scientific accuracy, detailed",
            SubjectType.MECHANICAL: "mechanical drawing, engineering precise, technical",
            SubjectType.ARCHITECTURAL: "architectural drawing, perspective, detailed structure",
            SubjectType.ABSTRACT: "abstract art, creative, unique, expressive",
            SubjectType.LANDSCAPE: "landscape, beautiful scenery, detailed environment",
            SubjectType.PORTRAIT: "portrait, detailed features, realistic",
            SubjectType.DIAGRAM: "diagram, clear, educational, labeled"
        }
        
        style_prefix = style_prefixes.get(request.style, "")
        subject_prefix = subject_prefixes.get(request.subject_type, "")
        
        return f"{style_prefix}, {subject_prefix}, {request.prompt}"
    
    def _encode_image(self, image_path: str) -> str:
        """Encode image to base64 for API."""
        with open(image_path, "rb") as f:
            return f.read().hex()
    
    def create_control_image(self, image_path: str, control_type: str) -> str:
        """
        Create control image from input image.
        
        Args:
            image_path: Path to input image
            control_type: "canny", "depth", "pose", "scribble"
            
        Returns:
            Path to generated control image
        """
        try:
            image = cv2.imread(image_path)
            
            if control_type == "canny":
                # Canny edge detection
                gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
                edges = cv2.Canny(gray, 100, 200)
                control_image = cv2.cvtColor(edges, cv2.COLOR_GRAY2BGR)
            elif control_type == "depth":
                # Simple depth estimation (grayscale as proxy)
                gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
                control_image = cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)
            elif control_type == "scribble":
                # Threshold for scribble effect
                gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
                _, binary = cv2.threshold(gray, 127, 255, cv2.THRESH_BINARY)
                control_image = cv2.cvtColor(binary, cv2.COLOR_GRAY2BGR)
            else:
                control_image = image
            
            # Save control image
            temp_dir = tempfile.mkdtemp()
            control_path = os.path.join(temp_dir, f"control_{control_type}_{int(time.time())}.png")
            cv2.imwrite(control_path, control_image)
            
            return control_path
            
        except Exception as e:
            print(f"[Professional Drawing] Control image creation failed: {e}")
            return image_path
    
    def generate_anatomical_drawing(self, subject: str, detailed: bool = True) -> DrawingResult:
        """Generate anatomical drawing with medical accuracy."""
        request = DrawingRequest(
            prompt=f"detailed anatomical drawing of {subject}, medical illustration, accurate structure",
            style=DrawingStyle.MEDICAL,
            subject_type=SubjectType.ANATOMICAL,
            width=self.default_width,
            height=self.default_height,
            steps=self.default_steps + (10 if detailed else 0),
            guidance_scale=self.default_guidance + (1.0 if detailed else 0)
        )
        return self.generate_drawing(request)
    
    def generate_scientific_diagram(self, subject: str, labeled: bool = True) -> DrawingResult:
        """Generate scientific diagram with labels."""
        labels_str = "with clear labels and annotations" if labeled else ""
        request = DrawingRequest(
            prompt=f"scientific diagram of {subject}, {labels_str}, educational illustration",
            style=DrawingStyle.SCIENTIFIC,
            subject_type=SubjectType.DIAGRAM,
            width=self.default_width,
            height=self.default_height,
            steps=self.default_steps,
            guidance_scale=self.default_guidance
        )
        return self.generate_drawing(request)
    
    def generate_technical_drawing(self, subject: str, precision: str = "high") -> DrawingResult:
        """Generate technical/engineering drawing."""
        request = DrawingRequest(
            prompt=f"technical drawing of {subject}, {precision} precision, engineering standard",
            style=DrawingStyle.TECHNICAL,
            subject_type=SubjectType.MECHANICAL,
            width=self.default_width,
            height=self.default_height,
            steps=self.default_steps + 5,
            guidance_scale=self.default_guidance + 0.5
        )
        return self.generate_drawing(request)
    
    def get_available_models(self) -> List[str]:
        """Get list of available models from local WebUI."""
        if not self.is_available:
            return []
        
        try:
            response = requests.get(f"{self.sd_webui_url}/sdapi/v1/sd-models", timeout=5)
            if response.status_code == 200:
                models = response.json()
                return [model.get("title", "") for model in models]
        except Exception as e:
            print(f"[Professional Drawing] Failed to get models: {e}")
        
        return []
    
    def get_drawing_history(self) -> List[DrawingResult]:
        """Get history of all drawings."""
        return self.drawing_history.copy()


def setup_stable_diffusion_guide() -> str:
    """Return setup guide for Stable Diffusion WebUI."""
    return """
STABLE DIFFUSION WEBUI SETUP GUIDE:

1. Clone the repository:
   git clone https://github.com/AUTOMATIC1111/stable-diffusion-webui.git
   cd stable-diffusion-webui

2. Install dependencies:
   pip install -r requirements.txt

3. Download models (place in models/Stable-diffusion/):
   - SDXL Base: https://huggingface.co/stabilityai/sdxl-turbo
   - SD 2.1: https://huggingface.co/stabilityai/sd-v2-1
   
4. Install ControlNet extension:
   cd extensions
   git clone https://github.com/Mikubill/sd-webui-controlnet.git

5. Download ControlNet models (place in models/ControlNet/):
   - ControlNet Canny
   - ControlNet Depth
   - ControlNet Pose
   - ControlNet Scribble

6. Run WebUI:
   python webui-user.bat

7. Access at: http://127.0.0.1:7860

8. Configure in app.py:
   engine = ProfessionalDrawingEngine(sd_webui_url="http://127.0.0.1:7860")
"""


# Example usage
if __name__ == "__main__":
    print(setup_stable_diffusion_guide())
    
    if HAS_PROFESSIONAL_DRAWING:
        engine = ProfessionalDrawingEngine()
        
        if engine.is_available:
            print("Available models:", engine.get_available_models())
            
            # Generate a test drawing
            result = engine.generate_scientific_diagram("human nervous system")
            print(f"Drawing generated: {result.success}")
            print(f"Image path: {result.image_path}")
        else:
            print("Stable Diffusion WebUI not running. Start it first.")
    else:
        print("Professional drawing dependencies not installed.")
        print("Install with: pip install torch diffusers transformers accelerate controlnet-aux")