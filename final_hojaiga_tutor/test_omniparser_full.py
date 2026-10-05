#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Full OmniParser Test - YOLO + Florence-2 on GPU
Measures complete scan time with UI element descriptions
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
    print("OMNIPARSER V2 FULL TEST (YOLO + Florence-2 on GPU)")
    print("=" * 60)
    
    # Check CUDA
    print(f"\n[1/5] Checking CUDA availability...")
    print(f"PyTorch version: {torch.__version__}")
    print(f"CUDA available: {torch.cuda.is_available()}")
    if torch.cuda.is_available():
        print(f"CUDA device: {torch.cuda.get_device_name(0)}")
    
    # Load YOLO model
    print("\n[2/5] Loading YOLO model...")
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
    
    # Load Florence-2 caption model
    print("\n[3/5] Loading Florence-2 caption model...")
    start_time = time.time()
    
    try:
        from util.utils import get_caption_model_processor
        caption_model_processor = get_caption_model_processor(
            model_name="florence2",
            model_name_or_path="D:/new_automation/OmniParser/weights/icon_caption_florence",
            device="cuda"
        )
        
        caption_time = time.time() - start_time
        print(f"[OK] Florence-2 loaded in {caption_time:.2f}s")
    except Exception as e:
        print(f"[ERROR] Failed to load Florence-2: {e}")
        import traceback
        traceback.print_exc()
        return
    
    # Capture screenshot
    print("\n[4/5] Capturing Notepad screenshot...")
    import pyautogui
    start_time = time.time()
    
    screenshot = pyautogui.screenshot()
    buffer = BytesIO()
    screenshot.save(buffer, format='JPEG', quality=85)
    screenshot_base64 = base64.b64encode(buffer.getvalue()).decode()
    
    capture_time = time.time() - start_time
    print(f"[OK] Screenshot captured in {capture_time:.2f}s")
    print(f"  Resolution: {screenshot.size[0]}x{screenshot.size[1]}")
    
    # Run OmniParser (YOLO + OCR + Florence-2)
    print("\n[5/5] Running OmniParser (YOLO + OCR + Florence-2)...")
    start_time = time.time()
    
    try:
        image_np = np.array(screenshot)
        
        # Use PaddleOCR for text detection
        print("  Running PaddleOCR for text detection...")
        from util.utils import check_ocr_box
        ocr_bbox_rslt, _ = check_ocr_box(
            image_np,
            display_img=False,
            output_bb_format='xyxy',
            use_paddleocr=True
        )
        text, ocr_bbox = ocr_bbox_rslt
        print(f"  OCR found {len(text)} text regions")
        
        # Run YOLO detection
        print("  Running YOLO detection...")
        results = yolo_model(image_np, conf=0.05, iou=0.1, imgsz=640)
        boxes = results[0].boxes.cpu().numpy()
        print(f"  YOLO found {len(boxes)} UI elements")
        
        # Run SOM labeled image generation (with Florence-2)
        print("  Running Florence-2 captioning...")
        from util.utils import get_som_labeled_img
        
        box_overlay_ratio = screenshot.size[0] / 3200
        draw_bbox_config = {
            'text_scale': 0.8 * box_overlay_ratio,
            'text_thickness': max(int(2 * box_overlay_ratio), 1),
            'text_padding': max(int(3 * box_overlay_ratio), 1),
            'thickness': max(int(3 * box_overlay_ratio), 1),
        }
        
        dino_labeled_img, label_coordinates, parsed_content_list = get_som_labeled_img(
            image_np,
            yolo_model,
            BOX_TRESHOLD=0.05,
            output_coord_in_ratio=True,
            ocr_bbox=ocr_bbox,
            draw_bbox_config=draw_bbox_config,
            caption_model_processor=caption_model_processor,
            ocr_text=text,
            iou_threshold=0.1,
            imgsz=640
        )
        
        parse_time = time.time() - start_time
        print(f"[OK] OmniParser completed in {parse_time:.2f}s")
        
        # Display results
        print("\n" + "=" * 60)
        print("RESULTS")
        print("=" * 60)
        print(f"Text regions found: {len(text)}")
        print(f"UI elements detected: {len(boxes)}")
        print(f"Elements captioned: {len(parsed_content_list)}")
        
        print(f"\nSample captions:")
        for i, caption in enumerate(parsed_content_list[:10], 1):
            print(f"  [{i}] {caption}")
        
        if len(parsed_content_list) > 10:
            print(f"  ... and {len(parsed_content_list) - 10} more")
        
        # Performance summary
        print("\n" + "=" * 60)
        print("PERFORMANCE SUMMARY")
        print("=" * 60)
        print(f"YOLO Model Load:        {yolo_time:.2f}s")
        print(f"Florence-2 Load:       {caption_time:.2f}s")
        print(f"Screenshot Capture:     {capture_time:.2f}s")
        print(f"OmniParser Processing:  {parse_time:.2f}s")
        print(f"Total Time:            {yolo_time + caption_time + capture_time + parse_time:.2f}s")
        print(f"Elements per Second:   {len(parsed_content_list) / parse_time:.1f}")
        print("=" * 60)
        
        print(f"\n[SUCCESS] OmniParser V2 is working on GPU!")
        print(f"Performance: {parse_time:.2f}s for complete UI analysis with {len(parsed_content_list)} captioned elements")
        
    except Exception as e:
        print(f"[ERROR] OmniParser failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
