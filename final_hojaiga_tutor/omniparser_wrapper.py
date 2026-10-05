"""
OmniParser V2 Wrapper for Universal App Teaching
Provides a Python interface to parse screenshots and extract UI elements
Optimized for GPU with RTX 3050
"""

import sys
import os
import json
import base64
import torch
import numpy as np
from PIL import Image
import io

# Add OmniParser to path
sys.path.insert(0, 'D:/new_automation/OmniParser')

try:
    from ultralytics import YOLO
    OMNIPARSER_AVAILABLE = True
except Exception as e:
    print(f"[WARN] YOLO not available: {e}", file=sys.stderr)
    OMNIPARSER_AVAILABLE = False


class OmniParserWrapper:
    """Wrapper for OmniParser V2 to parse screenshots and extract UI elements"""
    
    def __init__(self, weights_path='D:/new_automation/OmniParser/weights'):
        self.weights_path = weights_path
        self.yolo_model = None
        self.initialized = False
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        self.init_attempted = False
        
        # Lazy initialization - don't init until first use
        print(f"[OmniParser] Ready to initialize on device: {self.device}", file=sys.stderr)
    
    def _initialize(self):
        """Lazy initialization of OmniParser models"""
        if self.init_attempted:
            return self.initialized
            
        self.init_attempted = True
        
        if not OMNIPARSER_AVAILABLE:
            print("[ERROR] YOLO not available", file=sys.stderr)
            return False
            
        try:
            print(f"[OmniParser] Initializing on device: {self.device}", file=sys.stderr)
            
            # Initialize YOLO model directly
            print("[OmniParser] Loading YOLO model...", file=sys.stderr)
            self.yolo_model = YOLO(f'{self.weights_path}/icon_detect/model.pt')
            self.yolo_model.to(self.device)
            
            self.initialized = True
            print("[OmniParser] Initialized successfully", file=sys.stderr)
            return True
            
        except Exception as e:
            print(f"[ERROR] Failed to initialize OmniParser: {e}", file=sys.stderr)
            import traceback
            traceback.print_exc()
            return False
    
    def parse_screenshot(self, image_path=None, image_base64=None, box_threshold=0.05, iou_threshold=0.1, use_ocr=False):
        """
        Parse a screenshot and extract UI elements
        
        Args:
            image_path: Path to screenshot file
            image_base64: Base64 encoded image string
            box_threshold: Threshold for removing low-confidence boxes (default 0.05)
            iou_threshold: Threshold for removing overlapping boxes (default 0.1)
            use_ocr: Whether to run OCR (slow, default False)
            
        Returns:
            JSON with UI elements, bounding boxes, and descriptions
        """
        # Lazy initialize on first use
        if not self._initialize():
            return self._fallback_response(image_path, image_base64)
        
        try:
            # Load image
            if image_base64:
                image_data = base64.b64decode(image_base64)
                image = Image.open(io.BytesIO(image_data))
            elif image_path:
                image = Image.open(image_path)
            else:
                return {"error": "No image provided"}
            
            # Convert to numpy array for processing
            image_np = np.array(image)
            
            # OCR detection (optional, slow)
            text_regions = []
            if use_ocr:
                try:
                    from util.utils import check_ocr_box
                    ocr_bbox_rslt, _ = check_ocr_box(
                        image,  # Pass PIL image
                        display_img=False, 
                        output_bb_format='xyxy', 
                        use_paddleocr=False  # Use EasyOCR
                    )
                    text, ocr_bbox = ocr_bbox_rslt
                    for t, bbox in zip(text, ocr_bbox):
                        text_regions.append({
                            "type": "text",
                            "text": t,
                            "bbox": bbox,
                            "confidence": 0.8
                        })
                    print(f"[OmniParser] OCR found {len(text)} text regions", file=sys.stderr)
                except Exception as e:
                    print(f"[WARN] OCR failed: {e}", file=sys.stderr)
            
            # Run YOLO detection (fast)
            print(f"[OmniParser] Running YOLO detection on {self.device}...", file=sys.stderr)
            results = self.yolo_model(image_np, conf=box_threshold, iou=iou_threshold, imgsz=640, verbose=False)
            boxes = results[0].boxes.cpu().numpy()
            print(f"[OmniParser] YOLO found {len(boxes)} UI elements", file=sys.stderr)
            
            # Convert to structured JSON
            return self._format_result(boxes, text_regions, image.size)
            
        except Exception as e:
            print(f"[ERROR] OmniParser parsing failed: {e}", file=sys.stderr)
            import traceback
            traceback.print_exc()
            return self._fallback_response(image_path, image_base64)
    
    def _format_result(self, boxes, text_regions, image_size):
        """Format OmniParser result into structured JSON"""
        ui_elements = []
        
        width, height = image_size
        
        # Process YOLO detections
        for i, box in enumerate(boxes):
            x1, y1, x2, y2 = box.xyxy[0]
            ui_elements.append({
                "id": i,
                "type": "ui_element",
                "bbox": [float(x1), float(y1), float(x2 - x1), float(y2 - y1)],
                "center": [float((x1 + x2) / 2), float((y1 + y2) / 2)],
                "label": f"element_{i}",
                "description": f"UI element {i}",
                "confidence": float(box.conf[0])
            })
        
        # Add text regions
        for i, text_region in enumerate(text_regions):
            ui_elements.append({
                "id": len(boxes) + i,
                "type": "text",
                "bbox": text_region["bbox"],
                "text": text_region["text"],
                "confidence": text_region["confidence"]
            })
        
        return {
            "success": True,
            "ui_elements": ui_elements,
            "total_elements": len(ui_elements),
            "ui_elements_count": len(boxes),
            "text_regions_count": len(text_regions),
            "image_size": {"width": width, "height": height},
            "method": "omniparser_v2_gpu"
        }
    
    def _fallback_response(self, image_path=None, image_base64=None):
        """Fallback response when OmniParser is not available"""
        return {
            "success": False,
            "error": "OmniParser not initialized",
            "ui_elements": [],
            "total_elements": 0,
            "method": "fallback"
        }


def main():
    """Test the OmniParser wrapper"""
    print("[OmniParser Wrapper] Testing...")
    
    wrapper = OmniParserWrapper()
    
    # Test with a sample image path if provided
    if len(sys.argv) > 1:
        image_path = sys.argv[1]
        print(f"[OmniParser Wrapper] Parsing: {image_path}")
        result = wrapper.parse_screenshot(image_path=image_path, use_ocr=False)
        print(json.dumps(result, indent=2))
    else:
        print("[OmniParser Wrapper] Taking screenshot and parsing...")
        import pyautogui
        from io import BytesIO
        import base64
        screenshot = pyautogui.screenshot()
        buffer = BytesIO()
        screenshot.save(buffer, format='JPEG', quality=85)
        screenshot_base64 = base64.b64encode(buffer.getvalue()).decode()
        result = wrapper.parse_screenshot(image_base64=screenshot_base64, use_ocr=False)
        print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
