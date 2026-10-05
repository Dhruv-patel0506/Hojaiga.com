# llama.cpp Setup for Windows AI Tutor

## Why llama.cpp?

**Better than Ollama for your use case:**
- **Direct GPU control**: Better utilization of your RTX 3050
- **Lower overhead**: More resources for AI processing
- **Faster inference**: Better real-time response
- **No background service**: Cleaner operation
- **Better performance**: Optimized for your hardware

## Model Choice: Qwen2.5-VL

**Recommended over LLaVA-LLaMA3 because:**
- Educational focus (better for teaching)
- Slightly faster performance
- Better vision understanding
- Optimized for your RTX 3050

## Installation Steps

### 1. Download llama.cpp

```bash
# Clone llama.cpp repository
git clone https://github.com/ggerganov/llama.cpp.git
cd llama.cpp

# Or download pre-built binaries for Windows
# Visit: https://github.com/ggerganov/llama.cpp/releases
```

### 2. Build llama.cpp (or use pre-built)

```bash
# If building from source
cmake -B build
cmake --build build --config Release
```

### 3. Download Qwen2.5-VL Model

```bash
# Download Qwen2.5-VL in GGUF format for llama.cpp
# Visit: https://huggingface.co/Qwen/Qwen2.5-VL
# Download the GGUF file (usually around 4-5GB)
```

### 4. Configure Windows AI Tutor for llama.cpp

The application will automatically detect and use llama.cpp if configured.

## Performance Comparison

| Method | VRAM Usage | Speed | Overhead | Control |
|--------|-----------|-------|----------|---------|
| **Ollama** | ~4GB | Good | Medium | Low |
| **llama.cpp** | ~3.5GB | Better | Low | High |

## Why NOT Run Both

**Your concern is valid - running both would:**
- Waste GPU resources (Ollama + llama.cpp)
- Cause CPU overhead
- Reduce overall performance
- Complicate setup

**Solution:** Use llama.cpp exclusively for better performance.

## Switching from Ollama to llama.cpp

1. Stop Ollama server
2. Start llama.cpp server
3. Update configuration
4. Restart application

The application includes automatic detection and switching.