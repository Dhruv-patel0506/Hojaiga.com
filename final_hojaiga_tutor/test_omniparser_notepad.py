#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Test OmniParser on Notepad - Measure scan time and UI extraction quality
"""

import time
import sys
import json
import pyautogui
from PIL import Image
import base64
from io import BytesIO

# Add OmniParser to path
sys.path.insert(0, 'D:/new_automation/final_hojaiga_tutor')
from omniparser_wrapper import OmniParserWrapper

def main():
    print("=" * 60)
    print("OMNIPARSER V2 NOTEPAD TEST")
    print("=" * 60)
    
    # Step 1: Capture screenshot
    print("\n[1/4] Capturing Notepad screenshot...")
    start_time = time.time()
    
    screenshot = pyautogui.screenshot()
    buffer = BytesIO()
    screenshot.save(buffer, format='JPEG', quality=85)
    screenshot_base64 = base64.b64encode(buffer.getvalue()).decode()
    
    # Save for reference
    screenshot.save('D:/new_automation/final_hojaiga_tutor/notepad_test_screenshot.jpg')
    
    capture_time = time.time() - start_time
    print(f"[OK] Screenshot captured in {capture_time:.2f}s")
    print(f"  Resolution: {screenshot.size[0]}x{screenshot.size[1]}")
    
    # Step 2: Initialize OmniParser
    print("\n[2/4] Initializing OmniParser V2...")
    start_time = time.time()
    
    wrapper = OmniParserWrapper()
    
    init_time = time.time() - start_time
    print(f"[OK] OmniParser ready in {init_time:.2f}s")
    
    # Step 3: Parse screenshot
    print("\n[3/4] Parsing Notepad UI with OmniParser...")
    start_time = time.time()
    
    result = wrapper.parse_screenshot(image_base64=screenshot_base64)
    
    parse_time = time.time() - start_time
    print(f"[OK] UI parsed in {parse_time:.2f}s")
    
    # Step 4: Display results
    print("\n[4/4] Results:")
    print("=" * 60)
    
    print(f"\nSuccess: {result['success']}")
    print(f"Method: {result['method']}")
    print(f"Total Elements Found: {result['total_elements']}")
    
    if result['success'] and result['ui_elements']:
        print(f"\nUI Elements Extracted:")
        print("-" * 60)
        
        for i, element in enumerate(result['ui_elements'][:20], 1):  # Show first 20
            print(f"\n  [{i}] {element['label']}")
            print(f"      Type: {element['type']}")
            print(f"      Position: ({element['center'][0]}, {element['center'][1]})")
            print(f"      BBox: {element['bbox']}")
            print(f"      Confidence: {element['confidence']}")
        
        if len(result['ui_elements']) > 20:
            print(f"\n  ... and {len(result['ui_elements']) - 20} more elements")
    else:
        print(f"\nError: {result.get('error', 'Unknown error')}")
    
    # Summary
    print("\n" + "=" * 60)
    print("PERFORMANCE SUMMARY")
    print("=" * 60)
    print(f"Screenshot Capture:  {capture_time:.2f}s")
    print(f"OmniParser Init:     {init_time:.2f}s")
    print(f"UI Parsing:          {parse_time:.2f}s")
    print(f"Total Time:          {capture_time + init_time + parse_time:.2f}s")
    print(f"Elements per Second: {result['total_elements'] / parse_time:.1f}")
    print("=" * 60)
    
    # Save results to file
    with open('D:/new_automation/final_hojaiga_tutor/notepad_test_results.json', 'w') as f:
        json.dump(result, f, indent=2)
    
    print(f"\nResults saved to: notepad_test_results.json")
    print(f"Screenshot saved to: notepad_test_screenshot.jpg")

if __name__ == "__main__":
    main()
