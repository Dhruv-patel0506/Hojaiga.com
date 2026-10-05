#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Simplified OmniParser Test - YOLO + EasyOCR only (skip Florence-2 for now)
Measures scan time with UI element detection and text extraction
"""

import time
import sys
import json
import torch
import numpy as np
from PIL import Image
import base64
from io import BytesIO

# Add OmniParser to path
sys.path.insert(0, 'D:/new_automation/OmniParser')

def main():
    print("=" * 60)
    print("OMNIPARSER V2 SIMPLIFIED TEST (YOLO + EasyOCR on GPU)")
    print("=" * 60)
    
    # Check CUDA
    print(f"\n[1/4] Checking CUDA availability...")
    print(f"PyTorch version: {torch.__version__}")
    print(f"CUDA available: {torch.cuda.is_available()}")
    if torch.cuda.is_available():
        print(f"CUDA device: {torch.cuda.get_device_name(0)}")
    
    # Load YOLO model
    print("\n[2/4] Loading YOLO model...")
    start_time = time.time()
    
    try:
        from ultralytics import YOLO
        yolo_model = YOLO('D:/new_automation/OmniParser/weights/icon_detect/model.pt')
        yolo_model.to('cuda')
        
        yolo_time = time.time() - start_time
        print(f"[OK] YOLO model loaded in {yolo_time:.2f}s")
    except Exception as e:
        print(f"[ERROR] Failed to load YOLO: {e}")
        return
    
    # Capture screenshot
    print("\n[3/4] Capturing Notepad screenshot...")
    import pyautogui
    start_time = time.time()
    
    screenshot = pyautogui.screenshot()
    buffer = BytesIO()
    screenshot.save(buffer, format='JPEG', quality=85)
    screenshot_base64 = base64.b64encode(buffer.getvalue()).decode()
    
    capture_time = time.time() - start_time
    print(f"[OK] Screenshot captured in {capture_time:.2f}s")
    print(f"  Resolution: {screenshot.size[0]}x{screenshot.size[1]}")
    
    # Run YOLO detection + EasyOCR
    print("\n[4/4] Running YOLO detection + EasyOCR...")
    start_time = time.time()
    
    try:
        # Run EasyOCR for text detection
        print("  Running EasyOCR for text detection...")
        from util.utils import check_ocr_box
        ocr_bbox_rslt, _ = check_ocr_box(
            screenshot,  # Pass PIL image directly
            display_img=False,
            output_bb_format='xyxy',
            use_paddleocr=False  # Use EasyOCR instead of PaddleOCR
        )
        text, ocr_bbox = ocr_bbox_rslt
        print(f"  OCR found {len(text)} text regions")
        
        # Run YOLO detection
        print("  Running YOLO detection...")
        image_np = np.array(screenshot)
        results = yolo_model(image_np, conf=0.05, iou=0.1, imgsz=640)
        boxes = results[0].boxes.cpu().numpy()
        print(f"  YOLO found {len(boxes)} UI elements")
        
        parse_time = time.time() - start_time
        print(f"[OK] OmniParser completed in {parse_time:.2f}s")
        
        # Display results
        print("\n" + "=" * 60)
        print("RESULTS")
        print("=" * 60)
        print(f"Text regions found: {len(text)}")
        print(f"UI elements detected: {len(boxes)}")
        
        print(f"\nSample text regions:")
        for i, t in enumerate(text[:10], 1):
            print(f"  [{i}] '{t}'")
        
        if len(text) > 10:
            print(f"  ... and {len(text) - 10} more")
        
        # Create structured output
        structured_elements = []
        for i, box in enumerate(boxes):
            x1, y1, x2, y2 = box.xyxy[0]
            structured_elements.append({
                "id": i,
                "type": "ui_element",
                "bbox": [float(x1), float(y1), float(x2), float(y2)],
                "confidence": float(box.conf[0])
            })
        
        for i, (t, bbox) in enumerate(zip(text, ocr_bbox)):
            structured_elements.append({
                "id": len(boxes) + i,
                "type": "text",
                "text": t,
                "bbox": bbox,
                "confidence": 0.8
            })
        
        # Performance summary
        print("\n" + "=" * 60)
        print("PERFORMANCE SUMMARY")
        print("=" * 60)
        print(f"YOLO Model Load:        {yolo_time:.2f}s")
        print(f"Screenshot Capture:     {capture_time:.2f}s")
        print(f"OmniParser Processing:  {parse_time:.2f}s")
        print(f"Total Time:            {yolo_time + capture_time + parse_time:.2f}s")
        print(f"Elements per Second:   {len(structured_elements) / parse_time:.1f}")
        print("=" * 60)
        
        print(f"\n[SUCCESS] OmniParser V2 (YOLO + EasyOCR) is working on GPU!")
        print(f"Performance: {parse_time:.2f}s for UI analysis with {len(structured_elements)} elements")
        
        # Save structured output
        output_file = "D:/new_automation/final_hojaiga_tutor/omniparser_output.json"
        with open(output_file, 'w') as f:
            json.dump({
                "timestamp": time.time(),
                "resolution": screenshot.size,
                "text_regions": len(text),
                "ui_elements": len(boxes),
                "total_elements": len(structured_elements),
                "elements": structured_elements
            }, f, indent=2)
        print(f"\nStructured output saved to: {output_file}")
        
    except Exception as e:
        print(f"[ERROR] OmniParser failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
