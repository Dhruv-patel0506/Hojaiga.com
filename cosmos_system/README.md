# Cosmos System - Interactive Neural Web

A force-directed orbital canvas visualization with self-healing architecture.

## Features

- **Interactive Cosmos Canvas** - Force-directed graph with galactic clusters
- **Live Node Inspector** - Click any node to see real-time execution stream
- **Self-Healing Architecture** - "More it grows, more it self-heals"
- **WebSocket Backend** - Real-time telemetry and fault injection
- **Multiple Core Modes** - Bright Star, Black Hole, White Hole

## Quick Start

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Start the Backend Server

```bash
python server.py
```

The server will start on `http://localhost:8000`

### 3. Open the Frontend

Open `index.html` in any web browser (Chrome, Firefox, Edge).

## Usage

### Core Controls

- **Zoom** - Mouse wheel to zoom in/out
- **Pan** - Click and drag to move around
- **Inspect Node** - Click any dot to see live execution stream
- **Spawn Node** - Click "+ SPAWN NODE" to add new nodes (increases resilience)
- **Inject Fault** - Click "⚡ INJECT FAULT" to test self-healing

### Core Modes

- **Bright Star** - Normal operation mode
- **Black Hole** - Ingestion & Compression mode
- **White Hole** - Broadcast & Spawning mode

### Clusters

- **AUTOMATION CORE** (Yellow) - Central orchestration
- **AI TUTOR** (Blue) - Educational content generation
- **ANIMATION STUDIO** (Purple) - Visual rendering
- **PPT MAKER** (Orange) - Presentation synthesis
- **IMMUNE MESH** (Green) - Self-healing system

## Self-Healing Architecture

The system implements five self-healing mechanisms:

1. **Holographic State Sharding** - Neighbors store redundant state backups
2. **Cross-Cluster Synaptic Rerouting** - Automatic failover between domains
3. **Genetic Prompt Mutation** - Auto-debugging through parallel shadow testing
4. **Gravitational Load Balancing** - Dynamic resource distribution
5. **Autopoietic Skill Spawning** - Automatic new cluster creation

## API

### WebSocket Endpoint

`ws://localhost:8000/ws/cosmos`

### Actions

- `inspect_node` - Request live stream for a specific node
- `inject_fault` - Inject fault into a cluster to test self-healing

### Response Types

- `node_stream` - Real-time telemetry for a node
- `heartbeat` - System-wide health metrics
- `fault_alert` - Fault notification
- `heal_success` - Recovery notification

## Architecture

- **Frontend**: HTML5 Canvas + JavaScript
- **Backend**: FastAPI + WebSockets
- **Visualization**: Force-directed graph with orbital mechanics
- **State Management**: Real-time WebSocket communication

## Future Enhancements

- Vector embeddings for semantic clustering
- Distributed gossip protocol for mesh resilience
- Automated chaos testing and immune mutation
- Real worker node integration
- Persistent state storage