#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
End-to-end test of OmniParser integration with TypeScript system
Tests the complete flow: TypeScript → Python OmniParser → JSON output
"""

import sys
import json
import base64
import time
from io import BytesIO
from PIL import Image
import pyautogui

sys.path.insert(0, 'D:/new_automation/final_hojaiga_tutor')
from omniparser_wrapper import OmniParserWrapper

def main():
    print("=" * 60)
    print("OMNIPARSER END-TO-END INTEGRATION TEST")
    print("=" * 60)
    
    # Initialize wrapper
    print("\n[1/3] Initializing OmniParser wrapper...")
    wrapper = OmniParserWrapper()
    
    # Capture screenshot
    print("\n[2/3] Capturing screenshot...")
    start_time = time.time()
    screenshot = pyautogui.screenshot()
    buffer = BytesIO()
    screenshot.save(buffer, format='JPEG', quality=85)
    screenshot_base64 = base64.b64encode(buffer.getvalue()).decode()
    capture_time = time.time() - start_time
    print(f"Screenshot captured in {capture_time:.2f}s")
    
    # Parse with OmniParser
    print("\n[3/3] Parsing with OmniParser...")
    start_time = time.time()
    result = wrapper.parse_screenshot(image_base64=screenshot_base64, use_ocr=False)
    parse_time = time.time() - start_time
    
    # Display results
    print("\n" + "=" * 60)
    print("RESULTS")
    print("=" * 60)
    print(f"Success: {result['success']}")
    print(f"Total elements: {result['total_elements']}")
    print(f"UI elements: {result['ui_elements_count']}")
    print(f"Text regions: {result['text_regions_count']}")
    print(f"Image size: {result['image_size']['width']}x{result['image_size']['height']}")
    print(f"Method: {result['method']}")
    print(f"Parse time: {parse_time:.2f}s")
    
    # Show sample elements
    print(f"\nSample UI elements (first 5):")
    for i, el in enumerate(result['ui_elements'][:5], 1):
        print(f"  [{i}] {el['label']} at {el['center']} (confidence: {el['confidence']:.2f})")
    
    # Save to file for TypeScript to read
    output_file = "D:/new_automation/final_hojaiga_tutor/omniparser_test_output.json"
    with open(output_file, 'w') as f:
        json.dump(result, f, indent=2)
    
    print(f"\nOutput saved to: {output_file}")
    print("\n" + "=" * 60)
    print("✅ OMNIPARSER INTEGRATION TEST COMPLETE")
    print("=" * 60)

if __name__ == "__main__":
    main()
