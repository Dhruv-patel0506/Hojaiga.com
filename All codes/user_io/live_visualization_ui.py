"""
HOJAIGA AUTOMATION ARCHITECTURE DOC

============================================================
1. MASTER ARCHITECTURE CONTEXT
============================================================
This component is part of the Hojaiga Automation Architecture.
Component Type: Core File
Name: live_visualization_ui.py

============================================================
2. ORGAN/COMPONENT DIAGRAM
============================================================
```mermaid
graph TD
    classDef default fill:#1e1e1e,stroke:#333,stroke-width:2px,color:#d4d4d4;
    classDef component fill:#2d2d2d,stroke:#569cd6,stroke-width:2px,color:#d4d4d4;
    
    UPSTREAM[UPSTREAM INPUT]
    
    UPSTREAM -- event/socket --> COMPONENT
    
    subgraph COMPONENT [live_visualization_ui.py]
        direction TB
        IN[Inputs] --> PROC[Processing]
        PROC --> OUT[Outputs]
    end
    
    COMPONENT -- event/socket --> DOWNSTREAM_A[CONSUMER A]
    COMPONENT -- event/socket --> DOWNSTREAM_B[CONSUMER B]
    
    class COMPONENT component;
```

Inputs: Discovered from runtime
Outputs: Discovered from runtime
Dependencies: socketserver, websockets, socket, json, webbrowser...

============================================================
3. N8N-STYLE VISUAL WORKFLOW (MODEL)
============================================================
```mermaid
graph LR
    input([Input Node]) --> process([Code Node: live_visualization_ui.py]) --> output([Output Node])
```
"""

import asyncio
import socket
import json
import threading
import http.server
import socketserver
import webbrowser
import os
import websockets

# --- HTTP Server for Frontend ---
HTTP_PORT = 8080
HTML_FILE = "visualizer_frontend.html"

class CustomHandler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        if self.path == '/':
            self.path = '/' + HTML_FILE
        return http.server.SimpleHTTPRequestHandler.do_GET(self)

def start_http_server():
    # Change directory to where the script is located to serve the HTML file
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    with socketserver.TCPServer(("", HTTP_PORT), CustomHandler) as httpd:
        print(f"HTTP Server serving on http://localhost:{HTTP_PORT}")
        httpd.serve_forever()

# --- WebSocket Server ---
WS_PORT = 9998
connected_clients = set()

async def ws_handler(websocket, path=None):
    connected_clients.add(websocket)
    try:
        async for message in websocket:
            # Forward incoming WS messages from UI to system_boot via UDP
            try:
                msg_dict = json.loads(message)
                # Send to CNS via UDP
                udp_out = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                udp_out.sendto(message.encode('utf-8'), ('127.0.0.1', 9997))
                udp_out.close()
            except Exception as e:
                print(f"Failed to forward message from UI: {e}")
    except websockets.exceptions.ConnectionClosed:
        pass
    finally:
        connected_clients.remove(websocket)

async def broadcast_to_clients(message: str):
    if connected_clients:
        await asyncio.gather(
            *[client.send(message) for client in connected_clients],
            return_exceptions=True
        )

# --- UDP Listener (from legacy system) ---
UDP_PORT = 9999

async def udp_listener_loop():
    loop = asyncio.get_running_loop()
    
    class UDPProtocol(asyncio.DatagramProtocol):
        def datagram_received(self, data, addr):
            try:
                msg_str = data.decode('utf-8')
                # Parse to ensure it's valid JSON
                json.loads(msg_str)
                # Broadcast asynchronously
                asyncio.create_task(broadcast_to_clients(msg_str))
            except Exception as e:
                print(f"Error handling UDP packet: {e}")

    transport, protocol = await loop.create_datagram_endpoint(
        lambda: UDPProtocol(),
        local_addr=('127.0.0.1', UDP_PORT)
    )
    print(f"UDP Listener active on port {UDP_PORT}")
    
    try:
        await asyncio.sleep(3600*24) # keep running
    finally:
        transport.close()

async def main():
    print("Starting Web-Based Visualizer...")
    
    # Start HTTP Server in background thread
    threading.Thread(target=start_http_server, daemon=True).start()
    
    # Open browser automatically
    webbrowser.open(f"http://localhost:{HTTP_PORT}")
    
    # Start WebSocket Server
    async with websockets.serve(ws_handler, "127.0.0.1", WS_PORT):
        print(f"WebSocket Server active on ws://127.0.0.1:{WS_PORT}")
        
        # Start UDP listener
        await udp_listener_loop()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Shutting down visualizer...")
