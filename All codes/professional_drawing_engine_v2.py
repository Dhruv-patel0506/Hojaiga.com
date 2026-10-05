"""Professional Drawing Engine for Hojaiga - Diffusers Version.

Uses Stable Diffusion via diffusers for professional-level image generation.
Optimized for RTX 3050 6GB VRAM.
"""
import os
import torch
from diffusers import StableDiffusionPipeline, StableDiffusionXLPipeline
from typing import Optional, Dict, Any
from dataclasses import dataclass
from enum import Enum

# Configuration
MODELS_DIR = r"D:\new_automation\All codes\stable-diffusion-webui\models\Stable-diffusion"
CONTROLNET_DIR = r"D:\new_automation\All codes\stable-diffusion-webui\models\ControlNet"
DEVICE = "cuda" if torch.cuda.is_available() else "cpu"

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
    """Subject types for specialized generation."""
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
    style: DrawingStyle = DrawingStyle.REALISTIC
    subject_type: SubjectType = SubjectType.ABSTRACT
    negative_prompt: str = "blurry, low quality, distorted, deformed"
    num_inference_steps: int = 20
    guidance_scale: float = 7.0
    width: int = 512
    height: int = 512

@dataclass
class DrawingResult:
    """Result of drawing generation."""
    success: bool
    image_path: Optional[str]
    prompt: str
    style: str
    processing_time_ms: float
    error_message: Optional[str] = None
    metadata: Dict[str, Any] = None

class ProfessionalDrawingEngine:
    """Professional drawing engine using Stable Diffusion via diffusers.
    
    Optimized for RTX 3050 6GB VRAM with CPU fallback support.
    """
    
    def __init__(self, models_dir: str = MODELS_DIR, controlnet_dir: str = CONTROLNET_DIR):
        self.models_dir = models_dir
        self.controlnet_dir = controlnet_dir
        self.device = DEVICE
        self.is_available = torch.cuda.is_available()
        self.drawing_history = []
        
        # Load available models
        self.available_models = self._scan_models()
        self.available_controlnets = self._scan_controlnets()
        
        # Cache loaded pipelines
        self._pipeline_cache = {}
    
    def _scan_models(self) -> list:
        """Scan for available SD models."""
        if not os.path.exists(self.models_dir):
            return []
        
        models = []
        for f in os.listdir(self.models_dir):
            if f.endswith('.safetensors') or f.endswith('.pth'):
                models.append(f)
        return models
    
    def _scan_controlnets(self) -> list:
        """Scan for available ControlNet models."""
        if not os.path.exists(self.controlnet_dir):
            return []
        
        models = []
        for f in os.listdir(self.controlnet_dir):
            if f.endswith('.safetensors') or f.endswith('.pth'):
                models.append(f)
        return models
    
    def generate_drawing(self, request: DrawingRequest) -> DrawingResult:
        """Generate professional drawing based on request."""
        import time
        start_time = time.time()
        
        try:
            # Build enhanced prompt
            enhanced_prompt = self._build_enhanced_prompt(request)
            
            # Select appropriate model
            model_file = self._select_model(request.subject_type)
            if not model_file:
                return DrawingResult(
                    success=False,
                    image_path=None,
                    prompt=request.prompt,
                    style=request.style.value,
                    processing_time_ms=(time.time() - start_time) * 1000,
                    error_message="No suitable model found"
                )
            
            # Generate image
            image = self._generate_with_diffusers(enhanced_prompt, request, model_file)
            
            if image is None:
                return DrawingResult(
                    success=False,
                    image_path=None,
                    prompt=request.prompt,
                    style=request.style.value,
                    processing_time_ms=(time.time() - start_time) * 1000,
                    error_message="Generation failed"
                )
            
            # Save image
            output_path = self._save_image(image, request)
            
            processing_time = (time.time() - start_time) * 1000
            
            result = DrawingResult(
                success=True,
                image_path=output_path,
                prompt=request.prompt,
                style=request.style.value,
                processing_time_ms=processing_time,
                metadata={
                    "model": model_file,
                    "device": self.device,
                    "steps": request.num_inference_steps,
                    "guidance": request.guidance_scale,
                    "resolution": f"{request.width}x{request.height}"
                }
            )
            
            self.drawing_history.append(result)
            return result
            
        except Exception as e:
            return DrawingResult(
                success=False,
                image_path=None,
                prompt=request.prompt,
                style=request.style.value,
                processing_time_ms=(time.time() - start_time) * 1000,
                error_message=str(e)
            )
    
    def _build_enhanced_prompt(self, request: DrawingRequest) -> str:
        """Build enhanced prompt for professional quality."""
        style_prompt = self._get_style_prompt(request.style)
        subject_prompt = self._get_subject_prompt(request.subject_type)
        
        enhanced = f"{style_prompt} {subject_prompt} {request.prompt}"
        return enhanced.strip()
    
    def _get_style_prompt(self, style: DrawingStyle) -> str:
        """Get style-specific prompt additions."""
        style_prompts = {
            DrawingStyle.REALISTIC: "photorealistic, highly detailed, professional photography",
            DrawingStyle.ARTISTIC: "digital art, artistic, masterpiece, best quality",
            DrawingStyle.SCIENTIFIC: "scientific illustration, detailed, accurate, educational",
            DrawingStyle.MEDICAL: "medical illustration, anatomically accurate, detailed",
            DrawingStyle.TECHNICAL: "technical drawing, engineering diagram, precise",
            DrawingStyle.SKETCH: "sketch, drawing, pencil sketch",
            DrawingStyle.WATERCOLOR: "watercolor painting, artistic, soft colors",
            DrawingStyle.OIL_PAINTING: "oil painting, masterpiece, classical art",
            DrawingStyle.DIGITAL_ART: "digital art, modern, vibrant colors"
        }
        return style_prompts.get(style, "")
    
    def _get_subject_prompt(self, subject: SubjectType) -> str:
        """Get subject-specific prompt additions."""
        subject_prompts = {
            SubjectType.ANATOMICAL: "anatomical, biological structure, detailed",
            SubjectType.BIOLOGICAL: "biological, organic, detailed structure",
            SubjectType.MECHANICAL: "mechanical, engineering, precise",
            SubjectType.ARCHITECTURAL: "architectural, building, structural",
            SubjectType.ABSTRACT: "abstract, conceptual, artistic",
            SubjectType.LANDSCAPE: "landscape, environment, scenic",
            SubjectType.PORTRAIT: "portrait, detailed face, realistic",
            SubjectType.DIAGRAM: "diagram, schematic, clear structure"
        }
        return subject_prompts.get(subject, "")
    
    def _select_model(self, subject_type: SubjectType) -> Optional[str]:
        """Select appropriate model for subject type."""
        # Prefer SDXL for high-quality output
        sdxl_models = [m for m in self.available_models if 'sdxl' in m.lower() or 'xl' in m.lower()]
        sd15_models = [m for m in self.available_models if 'v1-5' in m.lower() or 'sd15' in m.lower()]
        
        # For anatomical/medical, prefer SDXL if available
        if subject_type in [SubjectType.ANATOMICAL, SubjectType.BIOLOGICAL, SubjectType.MEDICAL]:
            if sdxl_models:
                return sdxl_models[0]
        
        # Default to SDXL if available, otherwise SD 1.5
        if sdxl_models:
            return sdxl_models[0]
        if sd15_models:
            return sd15_models[0]
        
        return None
    
    def _generate_with_diffusers(self, prompt: str, request: DrawingRequest, model_file: str):
        """Generate image using diffusers."""
        try:
            # Check if SDXL or SD 1.5
            is_sdxl = 'sdxl' in model_file.lower() or 'xl' in model_file.lower()
            
            if is_sdxl:
                pipeline = StableDiffusionXLPipeline.from_single_file(
                    os.path.join(self.models_dir, model_file),
                    torch_dtype=torch.float16 if self.device == "cuda" else torch.float32,
                    use_safetensors=True
                )
            else:
                pipeline = StableDiffusionPipeline.from_single_file(
                    os.path.join(self.models_dir, model_file),
                    torch_dtype=torch.float16 if self.device == "cuda" else torch.float32,
                    use_safetensors=True
                )
            
            pipeline = pipeline.to(self.device)
            
            # Optimize for low VRAM
            if self.device == "cuda":
                pipeline.enable_attention_slicing()
                pipeline.enable_vae_slicing()
            
            # Generate
            image = pipeline(
                prompt,
                negative_prompt=request.negative_prompt,
                num_inference_steps=request.num_inference_steps,
                guidance_scale=request.guidance_scale,
                width=request.width,
                height=request.height
            ).images[0]
            
            return image
            
        except Exception as e:
            print(f"Diffusers generation error: {e}")
            return None
    
    def _save_image(self, image, request: DrawingRequest) -> str:
        """Save generated image."""
        import uuid
        filename = f"hojaiga_drawing_{uuid.uuid4().hex[:8]}.png"
        output_path = os.path.join(self.models_dir, filename)
        image.save(output_path)
        return output_path
    
    # Convenience methods
    def generate_anatomical_drawing(self, description: str) -> DrawingResult:
        """Generate anatomical drawing."""
        request = DrawingRequest(
            prompt=description,
            style=DrawingStyle.SCIENTIFIC,
            subject_type=SubjectType.ANATOMICAL,
            num_inference_steps=30  # Higher quality for anatomy
        )
        return self.generate_drawing(request)
    
    def generate_scientific_diagram(self, description: str) -> DrawingResult:
        """Generate scientific diagram."""
        request = DrawingRequest(
            prompt=description,
            style=DrawingStyle.SCIENTIFIC,
            subject_type=SubjectType.DIAGRAM,
            num_inference_steps=25
        )
        return self.generate_drawing(request)
    
    def generate_artistic_illustration(self, description: str) -> DrawingResult:
        """Generate artistic illustration."""
        request = DrawingRequest(
            prompt=description,
            style=DrawingStyle.ARTISTIC,
            subject_type=SubjectType.ABSTRACT,
            num_inference_steps=20
        )
        return self.generate_drawing(request)
    
    def get_available_models(self) -> list:
        """Get list of available models."""
        return self.available_models
    
    def get_available_controlnets(self) -> list:
        """Get list of available ControlNet models."""
        return self.available_controlnets

# Initialize global instance
_professional_drawing_engine = None

def get_professional_drawing_engine() -> ProfessionalDrawingEngine:
    """Get or create professional drawing engine instance."""
    global _professional_drawing_engine
    if _professional_drawing_engine is None:
        _professional_drawing_engine = ProfessionalDrawingEngine()
    return _professional_drawing_engine
