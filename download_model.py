"""Download Qwen2.5-VL-7B-Instruct Q4_K_M GGUF model in background."""
import sys
sys.stdout.reconfigure(encoding='utf-8')
print("Starting download of Qwen2.5-VL-7B-Instruct Q4_K_M.gguf (~4.8GB)...")
print("This may take 10-30 minutes depending on network speed.")

from huggingface_hub import hf_hub_download
import os

path = hf_hub_download(
    repo_id='bartowski/Qwen_Qwen2.5-VL-7B-Instruct-GGUF',
    filename='Qwen_Qwen2.5-VL-7B-Instruct-Q4_K_M.gguf',
    local_dir='D:/new_automation/models'
)
print(f"Download complete: {path}")
print(f"File size: {os.path.getsize(path) / 1e9:.2f} GB")
