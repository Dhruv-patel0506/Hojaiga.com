# Distributed Computing Setup for Windows AI Tutor

## 🚀 Distributed Computing Overview

Your holographic AI tutor can now automatically use better GPUs on your network when available, with LLaVA-LLaMA3 as backup!

## 🎯 How It Works

1. **Primary Model**: Qwen2.5-VL (recommended for your RTX 3050)
2. **Backup Model**: LLaVA-LLaMA3 (already downloaded)
3. **Auto-Fallback**: If primary fails, automatically uses backup
4. **Distributed Mode**: Uses network GPUs if they have more VRAM than your local

## 🔧 Setup Distributed Computing

### 1. Add Distributed Nodes

Edit `config/settings.json`:

```json
{
  "enable_distributed": true,
  "distributed_nodes": [
    "http://192.168.1.100:11434",
    "http://192.168.1.101:11434"
  ]
}
```

### 2. Configure Other Computers

Each distributed node needs:
- **Ollama installed**: `ollama pull qwen2.5-vl`
- **Ollama server running**: `ollama serve`
- **Health endpoint**: Simple Flask server that reports VRAM

### 3. Simple Health Endpoint Setup

On each distributed computer, create `health_server.py`:

```python
from flask import Flask, jsonify
import torch

app = Flask(__name__)

@app.route('/health')
def health():
    vram = torch.cuda.get_device_properties(0).total_memory / 1024**3
    return jsonify({
        "vram_available": round(vram, 2),
        "status": "healthy"
    })

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080)
```

Run: `python health_server.py`

## 🎮 Configuration Options

### Option 1: Local Only (Current Setup)
```json
{
  "backend": "ollama",
  "model": "qwen2.5-vl",
  "backup_model": "llava-llama3",
  "enable_distributed": false
}
```

### Option 2: Distributed Enabled
```json
{
  "backend": "distributed",
  "model": "qwen2.5-vl",
  "backup_model": "llava-llama3",
  "enable_distributed": true,
  "distributed_nodes": ["http://192.168.1.100:11434"]
}
```

### Option 3: Manual Backend Selection
```json
{
  "backend": "ollama",  // or "llamacpp" or "distributed"
  "model": "qwen2.5-vl",
  "backup_model": "llava-llama3"
}
```

## 📊 Decision Logic

The system automatically:
1. **Checks distributed nodes** if enabled
2. **Selects node with highest VRAM** (>6GB threshold)
3. **Falls back to local** if no better node available
4. **Auto-switches to backup model** if primary fails
5. **Notifies on node changes** via UI signal

## 🎯 Model Priority

1. **Qwen2.5-VL** (Primary) - Best for education
2. **LLaVA-LLaMA3** (Backup) - Already downloaded, reliable
3. **Network GPUs** (Optional) - If significantly better available

## 🚀 Quick Start with Distributed Computing

### Step 1: Start Local Ollama
```bash
ollama serve
```

### Step 2: Pull Both Models
```bash
ollama pull qwen2.5-vl
ollama pull llava-llama3  # Already done
```

### Step 3: (Optional) Set Up Distributed Nodes
- Follow instructions above to add network GPUs
- Enable distributed mode in config

### Step 4: Run Application
```bash
python src/core/app.py
```

## 🔥 Performance Benefits

### With Your RTX 3050 (6GB VRAM):
- **Local Qwen2.5-VL**: ~4GB VRAM, fast response
- **Network 12GB VRAM**: Even faster if available
- **Auto-switching**: Seamless use of best resources

### Resource Optimization:
- **No overload**: Only uses network GPUs if significantly better
- **Intelligent fallback**: Always has backup options
- **Local preference**: Uses local when sufficient

## 🎯 Current Recommendation

**For immediate use:**
- **Use Ollama + Qwen2.5-VL** (primary)
- **LLaVA-LLaMA3** as automatic backup
- **Distributed computing** optional for future

**Don't enable distributed computing yet** - your RTX 3050 is perfectly capable for Qwen2.5-VL. Add network GPUs later if you need more power!

## 📈 Monitoring

The application logs show:
- Which backend is being used
- Node selection process
- Fallback events
- VRAM availability

Check logs in the application window for distributed computing decisions.