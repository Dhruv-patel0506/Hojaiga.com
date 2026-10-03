"""Simple Stable Diffusion generator using diffusers.
This bypasses the complex AUTOMATIC1111 WebUI setup.
"""
import torch
from diffusers import StableDiffusionPipeline, StableDiffusionXLPipeline, ControlNetModel, StableDiffusionControlNetPipeline
from diffusers.utils import make_image_grid
import os

# Configuration
MODELS_DIR = r"D:\new_automation\All codes\stable-diffusion-webui\models\Stable-diffusion"
CONTROLNET_DIR = r"D:\new_automation\All codes\stable-diffusion-webui\models\ControlNet"
DEVICE = "cuda" if torch.cuda.is_available() else "cpu"

print(f"Using device: {DEVICE}")
print(f"CUDA available: {torch.cuda.is_available()}")

def generate_sdxl(prompt, model_path="sd_xl_base_1.0.safetensors"):
    """Generate image using SDXL."""
    print(f"\nGenerating with SDXL: {prompt}")
    
    try:
        # Load SDXL pipeline
        pipe = StableDiffusionXLPipeline.from_single_file(
            os.path.join(MODELS_DIR, model_path),
            torch_dtype=torch.float16 if DEVICE == "cuda" else torch.float32,
            use_safetensors=True
        )
        pipe = pipe.to(DEVICE)
        
        # Generate
        image = pipe(prompt, num_inference_steps=20, guidance_scale=7.0).images[0]
        
        # Save
        output_path = "generated_sdxl.png"
        image.save(output_path)
        print(f"Saved to: {output_path}")
        return image
        
    except Exception as e:
        print(f"SDXL generation failed: {e}")
        return None

def generate_sd15(prompt, model_path="v1-5-pruned-emaonly.safetensors"):
    """Generate image using SD 1.5."""
    print(f"\nGenerating with SD 1.5: {prompt}")
    
    try:
        # Load SD 1.5 pipeline
        pipe = StableDiffusionPipeline.from_single_file(
            os.path.join(MODELS_DIR, model_path),
            torch_dtype=torch.float16 if DEVICE == "cuda" else torch.float32,
            use_safetensors=True
        )
        pipe = pipe.to(DEVICE)
        
        # Generate
        image = pipe(prompt, num_inference_steps=20, guidance_scale=7.0).images[0]
        
        # Save
        output_path = "generated_sd15.png"
        image.save(output_path)
        print(f"Saved to: {output_path}")
        return image
        
    except Exception as e:
        print(f"SD 1.5 generation failed: {e}")
        return None

def generate_with_controlnet(prompt, controlnet_path, model_path="v1-5-pruned-emaonly.safetensors"):
    """Generate image using ControlNet."""
    print(f"\nGenerating with ControlNet: {prompt}")
    
    try:
        # Load ControlNet
        controlnet = ControlNetModel.from_single_file(
            os.path.join(CONTROLNET_DIR, controlnet_path),
            torch_dtype=torch.float16 if DEVICE == "cuda" else torch.float32
        )
        
        # Load pipeline with ControlNet
        pipe = StableDiffusionControlNetPipeline.from_single_file(
            os.path.join(MODELS_DIR, model_path),
            controlnet=controlnet,
            torch_dtype=torch.float16 if DEVICE == "cuda" else torch.float32,
            use_safetensors=True
        )
        pipe = pipe.to(DEVICE)
        
        # Generate (requires conditioning image)
        # For now, just test loading
        print("ControlNet loaded successfully!")
        return None
        
    except Exception as e:
        print(f"ControlNet generation failed: {e}")
        return None

if __name__ == "__main__":
    print("=== Simple Stable Diffusion Generator ===")
    
    # Check available models
    sd_models = os.listdir(MODELS_DIR) if os.path.exists(MODELS_DIR) else []
    controlnet_models = os.listdir(CONTROLNET_DIR) if os.path.exists(CONTROLNET_DIR) else []
    
    print(f"\nAvailable SD models: {sd_models}")
    print(f"Available ControlNet models: {controlnet_models}")
    
    # Test SDXL if available
    if "sd_xl_base_1.0.safetensors" in sd_models:
        generate_sdxl("A beautiful landscape with mountains and a lake")
    
    # Test SD 1.5 if available
    if "v1-5-pruned-emaonly.safetensors" in sd_models:
        generate_sd15("A cute cat sitting on a windowsill")
    
    print("\n=== Generation Complete ===")
