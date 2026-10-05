#!/usr/bin/env python3
"""
Simple launcher for Infinite Void
Starts server and opens browser
"""
import sys
import os
import subprocess
import webbrowser
import time

print("=" * 60)
print("INFINITE VOID LAUNCHER")
print("=" * 60)
print()

# Start server
print("[1/2] Starting WebSocket server...")
server_path = os.path.join(os.path.dirname(__file__), "infinite_void_server.py")
server_process = subprocess.Popen(
    [sys.executable, server_path],
    stdout=subprocess.DEVNULL,
    stderr=subprocess.DEVNULL,
    creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
)
print(f"[OK] Server started (PID: {server_process.pid})")

# Wait for server to start
time.sleep(2)

# Open browser
print("[2/2] Opening browser...")
html_path = os.path.join(os.path.dirname(__file__), "infinite_void_react.html")
file_url = f"file:///{html_path.replace(os.sep, '/')}"
webbrowser.open(file_url)
print(f"[OK] Browser opened")

print()
print("=" * 60)
print("INFINITE VOID IS READY!")
print("=" * 60)
print()
print("Enter any topic in the browser and click 'Teach Me'")
print("Press Ctrl+C here to stop the server")
print()

try:
    while True:
        time.sleep(1)
except KeyboardInterrupt:
    print()
    print("Stopping server...")
    server_process.terminate()
    print("Server stopped. Goodbye!")
