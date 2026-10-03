"""
image_generator.py — Free text-to-image generation using Pollinations.ai
- Unlimited attempts per day (with free secret key)
- Smart prompt enhancement for better contextual images
- Retry with backoff to avoid 429 errors
- No VRAM used, completely external

Setup:
  1. Go to https://enter.pollinations.ai
  2. Get a free secret key (sk_...) — no credit card needed
  3. Set environment variable: HOJAIGA_IMAGE_KEY=sk_your_key
  4. Or it works anonymously with 4 req/min limit

Usage:
    from image_generator import generate_image
    path = generate_image("a beautiful sunset over mountains")
"""

import os
import re
import time
import json
import logging
import urllib.request
import urllib.parse

logger = logging.getLogger("hojaiga.image_generator")

OUTPUT_DIR = os.path.join("D:", os.sep, "new_automation", "var", "hojaiga", "generated_images")
os.makedirs(OUTPUT_DIR, exist_ok=True)

# API key from environment (free from enter.pollinations.ai)
try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), ".env"))
except ImportError:
    pass
API_KEY = os.environ.get("HOJAIGA_IMAGE_KEY", "")

# Rate limiting state
_last_request_time = 0
_anon_min_interval = 16  # 1 req per 15s for anonymous


def _enhance_prompt(user_prompt: str) -> str:
    """
    Enhance a basic user prompt into a detailed, high-quality image generation prompt.
    Understands intent and adds professional photography/art terms for better results.
    """
    prompt = user_prompt.strip()

    # Detect intent and enhance accordingly
    enhancements = []

    # Detect if it's a diagram/technical drawing
    is_diagram = any(w in prompt.lower() for w in [
        "diagram", "chart", "flowchart", "technical", "blueprint",
        "schematic", "wireframe", "layout", "infographic"
    ])

    # Detect if it's a teaching/educational image
    is_educational = any(w in prompt.lower() for w in [
        "teach", "explain", "illustrate", "educational", "label",
        "annotated", "step by step", "how to"
    ])

    # Detect if it's a shape or simple drawing
    is_shape = any(w in prompt.lower() for w in [
        "circle", "square", "triangle", "rectangle", "line",
        "arrow", "star", "heart", "draw", "shape"
    ])

    # Detect if it's a UI mockup or design
    is_ui = any(w in prompt.lower() for w in [
        "ui", "ux", "app design", "website", "interface",
        "button", "menu", "dashboard", "mockup", "wireframe"
    ])

    # Detect if it's a person/portrait
    is_portrait = any(w in prompt.lower() for w in [
        "person", "portrait", "face", "man", "woman", "child",
        "character", "avatar", "selfie"
    ])

    # Detect if it's a scene/landscape
    is_scene = any(w in prompt.lower() for w in [
        "landscape", "sunset", "sky", "mountain", "ocean",
        "forest", "city", "street", "building", "nature"
    ])

    # Apply enhancements based on intent
    if is_diagram:
        enhancements.append("clean technical diagram")
        enhancements.append("professional infographic style")
        enhancements.append("clear labels and annotations")
        enhancements.append("white background")
    elif is_educational:
        enhancements.append("educational illustration")
        enhancements.append("clear and simple design")
        enhancements.append("labeled components")
        enhancements.append("professional textbook quality")
    elif is_shape:
        enhancements.append("clean geometric shapes")
        enhancements.append("bold colors")
        enhancements.append("simple flat design")
        enhancements.append("white background")
    elif is_ui:
        enhancements.append("modern UI design")
        enhancements.append("clean layout")
        enhancements.append("professional app mockup")
        enhancements.append("flat design style")
    elif is_portrait:
        enhancements.append("professional photography")
        enhancements.append("natural lighting")
        enhancements.append("sharp focus")
        enhancements.append("high detail")
    elif is_scene:
        enhancements.append("professional photography")
        enhancements.append("golden hour lighting")
        enhancements.append("high resolution")
        enhancements.append("vibrant colors")
    else:
        # General enhancement
        enhancements.append("high quality")
        enhancements.append("detailed")
        enhancements.append("professional")

    # Compose enhanced prompt
    enhanced = prompt + ", " + ", ".join(enhancements)

    # Add quality boosters at the end
    enhanced += ", 8k, sharp, detailed"

    return enhanced


def _make_request(url: str, timeout: int = 60) -> bytes:
    """Make an HTTP request with proper headers and timeout."""
    headers = {"User-Agent": "Hojaiga/1.0"}
    if API_KEY:
        headers["Authorization"] = f"Bearer {API_KEY}"

    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return response.read()


def generate_image(
    prompt: str,
    width: int = 1024,
    height: int = 768,
    seed: int = -1,
    model: str = "flux",
    filename: str = None,
    enhance: bool = True,
    max_retries: int = 3,
) -> str:
    """
    Generate an image from a text prompt using Pollinations.ai (free).

    Args:
        prompt: Text description of the image to generate
        width: Image width (default 1024)
        height: Image height (default 768)
        seed: Random seed (-1 = random)
        model: Model to use ("flux", "turbo", "flux-realism", "flux-anime")
        filename: Optional filename (auto-generated if None)
        enhance: Auto-enhance prompt for better quality (default True)
        max_retries: Max retry attempts on 429 errors (default 3)

    Returns:
        Absolute path to the saved PNG file, or empty string on failure
    """
    global _last_request_time

    # Enhance prompt for better results
    final_prompt = _enhance_prompt(prompt) if enhance else prompt
    logger.info(f"[IMGGEN] Prompt: '{prompt[:80]}' -> Enhanced: '{final_prompt[:80]}'")

    # Rate limiting — respect anonymous limits
    if not API_KEY:
        elapsed = time.time() - _last_request_time
        if elapsed < _anon_min_interval:
            wait_time = _anon_min_interval - elapsed
            logger.info(f"[IMGGEN] Rate limit: waiting {wait_time:.1f}s (anonymous, no key)")
            time.sleep(wait_time)

    # Generate filename
    if not filename:
        timestamp = int(time.time() * 1000)
        safe_prompt = "".join(c if c.isalnum() or c in (' ', '-', '_') else '' for c in prompt[:30])
        safe_prompt = safe_prompt.strip().replace(' ', '_')
        filename = f"{safe_prompt}_{timestamp}.png"

    filepath = os.path.join(OUTPUT_DIR, filename)

    # Try with retries
    for attempt in range(1, max_retries + 1):
        try:
            encoded_prompt = urllib.parse.quote(final_prompt)
            url = f"https://image.pollinations.ai/prompt/{encoded_prompt}?width={width}&height={height}&nologo=true"
            if seed >= 0:
                url += f"&seed={seed}"
            if model:
                url += f"&model={model}"

            logger.info(f"[IMGGEN] Attempt {attempt}/{max_retries}: generating ({width}x{height}, model={model})")

            _last_request_time = time.time()
            data = _make_request(url, timeout=120)

            if len(data) < 1000:
                logger.warning(f"[IMGGEN] Response too small ({len(data)} bytes), may be error")
                if attempt < max_retries:
                    time.sleep(5)
                    continue
                return ""

            with open(filepath, "wb") as f:
                f.write(data)

            logger.info(f"[IMGGEN] Saved: {filepath} ({len(data)} bytes)")
            return filepath

        except urllib.error.HTTPError as e:
            if e.code == 429:
                wait_time = 10 * attempt  # exponential backoff
                logger.warning(f"[IMGGEN] Rate limited (429), waiting {wait_time}s before retry {attempt}/{max_retries}")
                if attempt < max_retries:
                    time.sleep(wait_time)
                else:
                    logger.error(f"[IMGGEN] All {max_retries} attempts failed due to rate limiting")
                    return ""
            else:
                logger.error(f"[IMGGEN] HTTP error {e.code}: {e.reason}")
                return ""

        except Exception as e:
            logger.error(f"[IMGGEN] Error on attempt {attempt}: {e}")
            if attempt < max_retries:
                time.sleep(3)
            else:
                return ""

    return ""


def generate_image_bytes(
    prompt: str,
    width: int = 1024,
    height: int = 768,
    seed: int = -1,
    model: str = "flux",
    enhance: bool = True,
) -> bytes:
    """
    Generate an image and return raw bytes (for embedding in documents).

    Returns:
        PNG image bytes, or empty bytes on failure
    """
    final_prompt = _enhance_prompt(prompt) if enhance else prompt

    try:
        encoded_prompt = urllib.parse.quote(final_prompt)
        url = f"https://image.pollinations.ai/prompt/{encoded_prompt}?width={width}&height={height}&nologo=true"
        if seed >= 0:
            url += f"&seed={seed}"
        if model:
            url += f"&model={model}"

        logger.info(f"[IMGGEN] Generating bytes: '{final_prompt[:60]}...'")

        data = _make_request(url, timeout=120)
        logger.info(f"[IMGGEN] Got {len(data)} bytes")
        return data

    except Exception as e:
        logger.error(f"[IMGGEN] Failed: {e}")
        return b""


# CLI test
if __name__ == "__main__":
    import sys
    prompt = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else "a cute robot waving hello"
    print(f"Generating: {prompt}")
    print(f"Enhanced: {_enhance_prompt(prompt)}")
    path = generate_image(prompt)
    if path:
        print(f"Saved to: {path}")
    else:
        print("Failed!")
