#!/usr/bin/env python3
"""
Qwen2-VL-72B Server Launcher
Starts llama.cpp server with Qwen2-VL-72B for multimodal inference
"""

import subprocess
import time
import os
import sys

def start_llama_cpp_server():
    """Start llama.cpp server with Qwen2-VL-72B"""

    # Paths
    model_path = r"d:\new_automation\All codes\models\Qwen2-VL-72B-Instruct-Q4_K_M.gguf"
    llama_cpp_path = r"C:\Users\dhruv\llama.cpp\build\bin\Release\llama-server.exe"

    # Check if model exists
    if not os.path.exists(model_path):
        print(f"[ERROR] Model not found: {model_path}")
        print("Please download the model first using:")
        print("  python download_qwen2vl.py")
        sys.exit(1)

    # Check if llama.cpp exists
    if not os.path.exists(llama_cpp_path):
        print(f"[ERROR] llama.cpp not found: {llama_cpp_path}")
        print("Please install llama.cpp first:")
        print("  git clone https://github.com/ggerganov/llama.cpp")
        print("  cd llama.cpp")
        print("  cmake -B build")
        print("  cmake --build build --config Release")
        sys.exit(1)

    # Configuration optimized for RTX 3050 6GB
    # Qwen2-VL-72B Q4_K_M requires ~47GB RAM + 6GB VRAM
    # Will run primarily on CPU with some GPU offload
    config = {
        "model": model_path,
        "host": "localhost",
        "port": "8081",
        "ctx-size": "8192",  # Context window
        "n-gpu-layers": "0",  # 0 = CPU only (6GB VRAM not enough for 72B)
        "n-threads": "8",  # CPU threads
        "n-predict": "2048",  # Max tokens to predict
        "temp": "0.7",  # Temperature
        "top-p": "0.9",  # Top-p sampling
        "repeat-penalty": "1.1",  # Repetition penalty
        "image-min-tokens": "1024",  # Qwen-VL requires minimum 1024 image tokens for grounding tasks
        "verbose": "true",
    }

    # Build command
    cmd = [
        llama_cpp_path,
        "--model", config["model"],
        "--host", config["host"],
        "--port", config["port"],
        "--ctx-size", config["ctx-size"],
        "--n-gpu-layers", config["n-gpu-layers"],
        "--n-threads", config["n-threads"],
        "--n-predict", config["n-predict"],
        "--temp", config["temp"],
        "--top-p", config["top-p"],
        "--repeat-penalty", config["repeat-penalty"],
        "--image-min-tokens", config["image-min-tokens"],
        "--verbose" if config["verbose"] else "",
    ]

    print("[Qwen2-VL-72B] Starting llama.cpp server...")
    print(f"[Qwen2-VL-72B] Model: {model_path}")
    print(f"[Qwen2-VL-72B] Port: {config['port']}")
    print(f"[Qwen2-VL-72B] GPU Layers: {config['n-gpu-layers']} (CPU-only mode)")
    print(f"[Qwen2-VL-72B] CPU Threads: {config['n-threads']}")
    print("[Qwen2-VL-72B] Note: 72B model will run slowly on CPU. Expect 1-2 tokens/sec.")
    print("[Qwen2-VL-72B] Press Ctrl+C to stop the server")
    print()

    try:
        # Start server
        process = subprocess.Popen(cmd, shell=True)

        # Wait for server to start
        print("[Qwen2-VL-72B] Waiting for server to initialize...")
        time.sleep(5)

        print("[Qwen2-VL-72B] Server started successfully!")
        print(f"[Qwen2-VL-72B] API endpoint: http://{config['host']}:{config['port']}")
        print()

        # Keep process running
        process.wait()

    except KeyboardInterrupt:
        print("\n[Qwen2-VL-72B] Stopping server...")
        process.terminate()
        print("[Qwen2-VL-72B] Server stopped.")
    except Exception as e:
        print(f"[ERROR] Failed to start server: {e}")
        sys.exit(1)

if __name__ == "__main__":
    start_llama_cpp_server()
