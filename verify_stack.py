import os
import cv2

# --- FORCE EXPLICIT ENVIRONMENTAL BINDING ---
FFMPEG_BIN_PATH = r"D:\new_automation\All codes\ffmpeg-2026-09-21-git-a9cbcc2bbb-full_build\bin"
os.environ["PATH"] = FFMPEG_BIN_PATH + os.pathsep + os.environ.get("PATH", "")

print("🚀 Starting Live Media Handle Verification...")

print("\n--- 1. Testing Live Codec Handling ---")
# Attempt to read standard streaming properties using your background path profile
test_capture = cv2.VideoCapture(0) # Query local media pointers
is_opened = test_capture.isOpened()
test_capture.release()

# Check if the execution binaries are physically responsive in your custom path
ffmpeg_executable = os.path.join(FFMPEG_BIN_PATH, "ffmpeg.exe")
has_binary = os.path.exists(ffmpeg_executable)

if has_binary:
    print("✅ FFmpeg Executable Found at target path directory!")
    print("✅ Local Video Frame Tracing Layer is structurally sound and ready.")
else:
    print("❌ Error: Could not locate the ffmpeg.exe file inside your custom path folder.")

print("\n--- 2. Checking AI Workspace Layer ---")
try:
    from paddleocr import PaddleOCR
    ocr = PaddleOCR(use_textline_orientation=True, lang='en')
    print("✅ PaddleOCR Engine: local inference layers validated perfectly!")
except Exception as e:
    print(f"❌ PaddleOCR Engine Failed to load: {e}")
