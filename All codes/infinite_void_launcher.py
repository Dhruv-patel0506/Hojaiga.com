#!/usr/bin/env python3
"""
Infinite Void Lightboard Launcher
Opens the infinite void in default browser and starts WebSocket server
"""
import sys
import os
import subprocess
import webbrowser
import time

def start_void_server():
    """Start the infinite void WebSocket server"""
    server_path = os.path.join(os.path.dirname(__file__), "infinite_void_server.py")
    if os.path.exists(server_path):
        try:
            # Start server in background with no window
            if os.name == 'nt':  # Windows
                server_process = subprocess.Popen(
                    [sys.executable, server_path],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    creationflags=subprocess.CREATE_NO_WINDOW
                )
            else:  # Unix/Linux/Mac
                server_process = subprocess.Popen(
                    [sys.executable, server_path],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL
                )
            print(f"[Infinite Void] [OK] WebSocket server started (PID: {server_process.pid})")
            return server_process
        except Exception as e:
            print(f"[Infinite Void] [ERROR] Failed to start server: {e}")
            return None
    else:
        print(f"[Infinite Void] [ERROR] Server script not found: {server_path}")
        return None

def open_void_in_browser():
    """Open the infinite void HTML in default browser"""
    html_path = os.path.join(os.path.dirname(__file__), "infinite_void_react.html")
    if os.path.exists(html_path):
        # Convert to file:// URL
        file_url = f"file:///{html_path.replace(os.sep, '/')}"
        webbrowser.open(file_url)
        print(f"[Infinite Void] [OK] Opened in browser: {file_url}")
        return True
    else:
        print(f"[Infinite Void] [ERROR] HTML file not found: {html_path}")
        return False

def main():
    print("=" * 60)
    print("INFINITE VOID LIGHTBOARD LAUNCHER")
    print("=" * 60)
    print()

    # Start the WebSocket server
    print("[1/2] Starting WebSocket server...")
    server_process = start_void_server()

    if not server_process:
        print("[Infinite Void] [ERROR] Could not start server")
        input("Press Enter to exit...")
        sys.exit(1)

    # Give server time to start
    time.sleep(1)

    # Open the HTML in browser
    print("[2/2] Opening infinite void in browser...")
    if not open_void_in_browser():
        print("[Infinite Void] [ERROR] Could not open HTML")
        if server_process:
            server_process.terminate()
        input("Press Enter to exit...")
        sys.exit(1)

    print()
    print("=" * 60)
    print("[OK] INFINITE VOID IS READY!")
    print("=" * 60)
    print()
    print("Your browser should now show the infinite void.")
    print("Enter any topic and click 'Teach Me' to see diagrams.")
    print()
    print("Press Ctrl+C here to stop the server and exit.")
    print()

    try:
        # Keep running until user stops it
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print()
        print("[Infinite Void] Stopping server...")
        if server_process:
            server_process.terminate()
            server_process.wait()
        print("[Infinite Void] Server stopped. Goodbye!")
        sys.exit(0)

if __name__ == "__main__":
    main()
