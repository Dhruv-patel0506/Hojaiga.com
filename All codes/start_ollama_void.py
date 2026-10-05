#!/usr/bin/env python3
"""
Launcher for Ollama-powered Infinite Void
Starts both Ollama server (if needed) and the WebSocket server
"""

import subprocess
import time
import sys
import os

def check_ollama():
    """Check if Ollama is running"""
    try:
        import requests
        response = requests.get("http://localhost:11434/api/tags", timeout=2)
        return response.status_code == 200
    except:
        return False

def start_ollama_server():
    """Start Ollama server in background"""
    print("[Launcher] Starting Ollama server...")
    try:
        subprocess.Popen(["ollama", "serve"], shell=True)
        time.sleep(3)
        return check_ollama()
    except:
        return False

def start_void_server():
    """Start the WebSocket server"""
    print("[Launcher] Starting Infinite Void server...")
    script_path = os.path.join(os.path.dirname(__file__), "infinite_void_server_ollama.py")
    subprocess.run([sys.executable, script_path])

def open_browser():
    """Open the React frontend"""
    html_path = os.path.join(os.path.dirname(__file__), "infinite_void_react_rough.html")
    print(f"[Launcher] Opening browser...")
    os.startfile(html_path)

def main():
    print("=" * 60)
    print("Ollama-Powered Infinite Void Launcher")
    print("=" * 60)

    # Check Ollama
    if not check_ollama():
        print("[Launcher] Ollama not running, starting it...")
        if not start_ollama_server():
            print("[ERROR] Failed to start Ollama. Please run: ollama serve")
            return

    print("[Launcher] Ollama is running ✓")

    # Check if model is downloaded
    try:
        import requests
        response = requests.get("http://localhost:11434/api/tags", timeout=5)
        models = response.json().get("models", [])
        model_names = [m.get("name", "") for m in models]

        if "llama3.1" not in model_names and "llama3.1:latest" not in model_names:
            print("[Launcher] Llama 3.1 not found. Downloading...")
            print("[Launcher] This may take 10-20 minutes (4.9GB)")
            subprocess.run(["ollama", "pull", "llama3.1"])
        else:
            print("[Launcher] Llama 3.1 found ✓")
    except:
        print("[Launcher] Could not check models, proceeding anyway...")

    # Open browser
    open_browser()

    # Start server
    start_void_server()

if __name__ == "__main__":
    main()
