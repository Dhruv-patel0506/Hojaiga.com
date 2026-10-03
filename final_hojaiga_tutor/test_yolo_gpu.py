#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Simplified OmniParser Test - YOLO Only (No OCR)
Measures scan time with GPU acceleration
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
    print("OMNIPARSER V2 YOLO-ONLY TEST (GPU)")
    print("=" * 60)
    
    # Check CUDA
    print(f"\n[1/4] Checking CUDA availability...")
    print(f"PyTorch version: {torch.__version__}")
    print(f"CUDA available: {torch.cuda.is_available()}")
    if torch.cuda.is_available():
        print(f"CUDA device: {torch.cuda.get_device_name(0)}")
        print(f"CUDA device count: {torch.cuda.device_count()}")
    
    # Import YOLO model
    print("\n[2/4] Loading YOLO model from local weights...")
    start_time = time.time()
    
    try:
        from ultralytics import YOLO
        # Load YOLO model directly from local weights
        yolo_model = YOLO('D:/new_automation/OmniParser/weights/icon_detect/model.pt')
        yolo_model.to('cuda')
        
        init_time = time.time() - start_time
        print(f"[OK] YOLO model loaded in {init_time:.2f}s")
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
    
    # Save for reference
    screenshot.save('D:/new_automation/final_hojaiga_tutor/notepad_yolo_test.jpg')
    
    capture_time = time.time() - start_time
    print(f"[OK] Screenshot captured in {capture_time:.2f}s")
    print(f"  Resolution: {screenshot.size[0]}x{screenshot.size[1]}")
    
    # Run YOLO detection
    print("\n[4/4] Running YOLO detection on GPU...")
    start_time = time.time()
    
    try:
        image_np = np.array(screenshot)
        
        # Run YOLO inference
        results = yolo_model(image_np, conf=0.05, iou=0.1, imgsz=640)
        
        detect_time = time.time() - start_time
        print(f"[OK] YOLO detection completed in {detect_time:.2f}s")
        
        # Count detections
        num_detections = len(results[0].boxes) if len(results) > 0 else 0
        print(f"  Detections: {num_detections}")
        
        # Display results
        print("\n" + "=" * 60)
        print("PERFORMANCE SUMMARY")
        print("=" * 60)
        print(f"YOLO Model Load:     {init_time:.2f}s")
        print(f"Screenshot Capture:  {capture_time:.2f}s")
        print(f"YOLO Detection:      {detect_time:.2f}s")
        print(f"Total Time:          {init_time + capture_time + detect_time:.2f}s")
        print(f"Detections per Sec:  {num_detections / detect_time:.1f}")
        print("=" * 60)
        
        print(f"\n[SUCCESS] OmniParser YOLO is working on GPU!")
        print(f"Performance: {detect_time:.2f}s for {num_detections} detections")
        
    except Exception as e:
        print(f"[ERROR] YOLO detection failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
