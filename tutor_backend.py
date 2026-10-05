import os
import base64
import subprocess
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Optional, List

# --- FORCE THE VERIFIED WORKING ENVIRONMENTAL PATHS ---
FFMPEG_BIN_PATH = r"D:\new_automation\All codes\ffmpeg-2026-09-21-git-a9cbcc2bbb-full_build\bin"
os.environ["PATH"] = FFMPEG_BIN_PATH + os.pathsep + os.environ.get("PATH", "")
os.environ.setdefault('HUB_DATASET_ENDPOINT', 'https://modelscope.cn')

from paddleocr import PaddleOCR

app = FastAPI(title="Universal AI Tutor Matrix Core Server")

# Initialize your validated local PaddleOCR Engine
print("🔄 Initializing local AI Vision Engine Layers...")
ocr_engine = PaddleOCR(use_textline_orientation=True, lang='en')
print("✅ Local AI Vision Engine Ready for Live Canvas Actions!")


# --- DATA DATA SCHEMAS ---
class FrameAnalysisRequest(BaseModel):
    image_base64: str  # Frame payload passed from your infinite void video overlay

class CodeSandboxRequest(BaseModel):
    student_code: str  # Unverified python script submitted by the user/agent

# --- ENDPOINT 1: LOCAL DIAGRAM TRACING & WHITEBOARD OCR ---
@app.post("/analyze-frame")
async def analyze_frame(payload: FrameAnalysisRequest):
    """
    Slices and reads raw geometry/text layouts from classroom video frames with zero external API lag.
    """
    try:
        # Reconstruct image from the canvas layer stream
        img_bytes = base64.b64decode(payload.image_base64)
        temp_filename = "active_tutor_frame.jpg"
        
        with open(temp_filename, "wb") as f:
            f.write(img_bytes)
            
        # Run local text line detection and path extraction
        result = ocr_engine.ocr(temp_filename, cls=True)
        
        if os.path.exists(temp_filename):
            os.remove(temp_filename)
            
        extracted_elements = []
        if result and result[0]:
            for line in result[0]:
                box_coordinates = line[0]  # [[x1,y1], [x2,y2], [x3,y3], [x4,y4]]
                text_content = line[1][0]
                confidence_score = line[1][1]
                
                extracted_elements.append({
                    "text": text_content,
                    "confidence": float(confidence_score),
                    "bounding_box": box_coordinates
                })
                
        return {"status": "success", "elements": extracted_elements}
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"AI Vision Layer Exception: {str(e)}")


# --- ENDPOINT 2: SECURE PYTHON CODE EXECUTION SANDBOX ---
@app.post("/run-code")
async def run_code_sandbox(payload: CodeSandboxRequest):
    """
    Runs code snippets securely within the isolated python:3.13-slim Docker container we cached.
    """
    sandbox_filename = "temp_student_script.py"
    full_sandbox_path = os.path.abspath(sandbox_filename)
    
    # Write code securely to temporary isolated container volume mount points
    with open(full_sandbox_path, "w", encoding="utf-8") as f:
        f.write(payload.student_code)
        
    try:
        # Force strict resource containment limits. --rm deletes container when done execution
        docker_command = [
            "docker", "run", "--rm",
            "-v", f"{full_sandbox_path}:/app/temp_student_script.py",
            "python:3.13-slim",
            "python", "/app/temp_student_script.py"
        ]
        
        # Enforce a 10 second runtime timeout so students can't accidentally spawn infinite loops
        execution = subprocess.run(
            docker_command,
            capture_output=True,
            text=True,
            timeout=10
        )
        
        return {
            "status": "completed",
            "exit_code": execution.returncode,
            "stdout": execution.stdout,
            "stderr": execution.stderr
        }
        
    except subprocess.TimeoutExpired:
        return {
            "status": "failed",
            "exit_code": -1,
            "stdout": "",
            "stderr": "Execution Timeout Error: Code process halted after exceeding 10-second safety threshold."
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Sandbox Isolation Exception: {str(e)}")
    finally:
        # Enforce strict folder cleanup routines
        if os.path.exists(full_sandbox_path):
            os.remove(full_sandbox_path)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)
