#!/usr/bin/env python3
"""
Check download progress of Qwen2-VL-72B model
"""

import os
import time

def check_download():
    model_path = r"d:\new_automation\All codes\models\Qwen2-VL-72B-Instruct-Q4_K_M.gguf"
    expected_size = 47.5 * 1024 * 1024 * 1024  # 47.5 GB in bytes

    if not os.path.exists(model_path):
        print(f"[Download] Model file not found: {model_path}")
        return

    current_size = os.path.getsize(model_path)
    progress = (current_size / expected_size) * 100
    current_size_gb = current_size / (1024 * 1024 * 1024)

    print(f"[Download Progress]")
    print(f"  Current: {current_size_gb:.2f} GB / 47.5 GB")
    print(f"  Progress: {progress:.2f}%")
    print(f"  Status: {'Downloading...' if progress < 100 else 'Complete!'}")

if __name__ == "__main__":
    check_download()
