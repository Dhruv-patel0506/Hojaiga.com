"""Production-only local vision, code-tutor, and localhost bridge services.

All expensive work stays outside the Qt GUI thread.  Results are plain scene
payloads; the existing OmniSketch validator remains the sole drawing gate.
"""
from __future__ import annotations

import asyncio
import base64
import json
import os
import queue
import shutil
import subprocess
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Callable, Optional

import cv2
import numpy as np
import requests
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
import uvicorn
from PyQt5.QtCore import QObject, pyqtSignal

try:
    from app import TutorExtensions
except Exception:
    TutorExtensions = None


PROJECT_ROOT = Path(__file__).resolve().parent.parent
FFMPEG_BIN = PROJECT_ROOT / "All codes" / "ffmpeg-2026-09-21-git-a9cbcc2bbb-full_build" / "bin"
OLLAMA_GENERATE_URL = os.getenv("OMNITUTOR_OLLAMA_URL", "http://localhost:11434/api/generate")
VISION_MODEL = os.getenv("OMNITUTOR_VISION_MODEL", "llama3.2-vision:latest")
CODE_MODEL = os.getenv("OMNITUTOR_CODE_MODEL", "qwen2.5-coder:7b")


def configure_local_runtime() -> None:
    """Bind verified local assets before PaddleOCR/FFmpeg are first used."""
    os.environ.setdefault("HUB_DATASET_ENDPOINT", "https://modelscope.cn")
    if FFMPEG_BIN.is_dir():
        current = os.environ.get("PATH", "")
        if str(FFMPEG_BIN) not in current.split(os.pathsep):
            os.environ["PATH"] = str(FFMPEG_BIN) + os.pathsep + current


configure_local_runtime()


class OllamaLocalClient:
    """Small JSON-only client for the verified local Ollama server."""
    def __init__(self, endpoint: str = OLLAMA_GENERATE_URL) -> None:
        self.endpoint = endpoint

    @staticmethod
    def _decode_object(raw: str) -> dict[str, Any]:
        decoder = json.JSONDecoder()
        for index, char in enumerate(raw or ""):
            if char != "{":
                continue
            try:
                value, _ = decoder.raw_decode(raw[index:])
            except json.JSONDecodeError:
                continue
            if isinstance(value, dict):
                return value
        raise ValueError("local model did not return a JSON object")

    def generate_json(self, model: str, prompt: str, image_bgr: Optional[np.ndarray] = None,
                      timeout: int = 120) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": model,
            "prompt": prompt,
            "format": "json",
            "stream": False,
            "options": {"temperature": 0.1},
        }
        if image_bgr is not None:
            ok, encoded = cv2.imencode(".jpg", image_bgr, [cv2.IMWRITE_JPEG_QUALITY, 88])
            if not ok:
                raise ValueError("could not encode vision frame")
            payload["images"] = [base64.b64encode(encoded.tobytes()).decode("ascii")]
        response = requests.post(self.endpoint, json=payload, timeout=timeout)
        response.raise_for_status()
        return self._decode_object(str(response.json().get("response", "")))


class PaddleSemanticTracer:
    """Lazy local OCR + vector extraction; no cloud image upload."""
    def __init__(self) -> None:
        self._ocr: Any = None
        self._lock = threading.Lock()

    def _engine(self) -> Any:
        with self._lock:
            if self._ocr is None:
                configure_local_runtime()
                from paddleocr import PaddleOCR  # Lazy: model startup stays off the GUI thread.
                self._ocr = PaddleOCR(
                    lang="en",
                    use_doc_orientation_classify=False,
                    use_doc_unwarping=False,
                    use_textline_orientation=False,
                )
            return self._ocr

    @staticmethod
    def _mapping(result: Any) -> dict[str, Any]:
        if isinstance(result, dict):
            return result
        for attr in ("to_dict", "json"):
            candidate = getattr(result, attr, None)
            try:
                value = candidate() if callable(candidate) else candidate
                if isinstance(value, dict):
                    return value
                if isinstance(value, str):
                    decoded = json.loads(value)
                    if isinstance(decoded, dict):
                        return decoded
            except Exception:
                pass
        return {}

    def analyze(self, frame_bgr: np.ndarray, source_id: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
        if frame_bgr is None or frame_bgr.size == 0:
            raise ValueError("empty frame")
        height, width = frame_bgr.shape[:2]
        text_blocks: list[dict[str, Any]] = []
        for result in self._engine().predict(frame_bgr):
            data = self._mapping(result)
            texts = data.get("rec_texts", []) or []
            scores = data.get("rec_scores", []) or []
            polygons = data.get("rec_polys", []) or data.get("rec_boxes", []) or []
            for text, score, polygon in zip(texts, scores, polygons):
                try:
                    points = np.asarray(polygon, dtype=float).reshape(-1, 2)
                    x0, y0 = points.min(axis=0)
                    x1, y1 = points.max(axis=0)
                    confidence = float(score)
                except Exception:
                    continue
                if not str(text).strip() or confidence < 0.45:
                    continue
                text_blocks.append({
                    "text": str(text)[:300], "confidence": round(confidence, 3),
                    "bbox": [round(float(x0) / width, 5), round(float(y0) / height, 5),
                             round(float(x1) / width, 5), round(float(y1) / height, 5)],
                })

        gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)
        edges = cv2.Canny(cv2.GaussianBlur(gray, (3, 3), 0), 45, 130)
        contours, _ = cv2.findContours(edges, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
        contours = sorted(contours, key=cv2.contourArea, reverse=True)
        trace_actions: list[dict[str, Any]] = []
        for index, contour in enumerate(contours[:36]):
            if cv2.contourArea(contour) < max(20, width * height * 0.00012):
                continue
            epsilon = max(1.0, cv2.arcLength(contour, False) * 0.008)
            points = cv2.approxPolyDP(contour, epsilon, False).reshape(-1, 2)
            if len(points) < 2:
                continue
            trace_actions.append({
                "id": f"trace-{index}", "kind": "trace", "start_ms": min(1600, index * 45),
                "duration_ms": 240, "style": {"color": "#fbbf24", "width": 2.2, "opacity": 0.92},
                "data": {"points": [[round(float(x) / width, 5), round(float(y) / height, 5)] for x, y in points],
                         "source_id": source_id, "source_size": [width, height]},
            })
        return trace_actions, text_blocks, {"width": width, "height": height, "source_id": source_id}


def extract_video_frame(path: str, seconds: float = 0.0) -> np.ndarray:
    """Use the verified FFmpeg binary first; fall back to OpenCV decoding."""
    target = Path(path).expanduser().resolve()
    if not target.is_file():
        raise FileNotFoundError(target)
    ffmpeg = FFMPEG_BIN / "ffmpeg.exe"
    if ffmpeg.is_file():
        command = [str(ffmpeg), "-v", "error", "-ss", str(max(0.0, seconds)), "-i", str(target),
                   "-frames:v", "1", "-f", "image2pipe", "-vcodec", "png", "pipe:1"]
        result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=25, check=False)
        if result.returncode == 0 and result.stdout:
            frame = cv2.imdecode(np.frombuffer(result.stdout, np.uint8), cv2.IMREAD_COLOR)
            if frame is not None:
                return frame
    capture = cv2.VideoCapture(str(target))
    try:
        capture.set(cv2.CAP_PROP_POS_MSEC, max(0.0, seconds) * 1000.0)
        ok, frame = capture.read()
        if not ok or frame is None:
            raise RuntimeError("could not decode requested video frame")
        return frame
    finally:
        capture.release()


class SecureCodeTutor:
    """Diagnostic and execution layer: code never runs on the Windows host."""
    def __init__(self, ollama: OllamaLocalClient, timeout_seconds: float = 4.0) -> None:
        self.ollama = ollama
        self.timeout_seconds = max(1.0, min(15.0, float(timeout_seconds)))

    @staticmethod
    def _diagnostics(filename: str, source: str) -> list[dict[str, Any]]:
        pyright = shutil.which("pyright") or shutil.which("pyright.cmd")
        if pyright:
            with tempfile.TemporaryDirectory(prefix="omnitutor_diagnostics_") as directory:
                target = Path(directory) / Path(filename).name
                target.write_text(source, encoding="utf-8")
                completed = subprocess.run([pyright, "--outputjson", str(target)], capture_output=True, text=True, timeout=20, check=False)
                try:
                    return list(json.loads(completed.stdout).get("generalDiagnostics", []))
                except (json.JSONDecodeError, AttributeError):
                    pass
        try:
            compile(source, filename, "exec")
            return []
        except SyntaxError as error:
            line = max(0, (error.lineno or 1) - 1)
            column = max(0, (error.offset or 1) - 1)
            return [{"severity": "error", "message": error.msg, "range": {"start": {"line": line, "character": column}, "end": {"line": line, "character": column + 1}}}]

    def _execute(self, source: str) -> dict[str, Any]:
        with tempfile.TemporaryDirectory(prefix="omnitutor_sandbox_") as directory:
            script = Path(directory) / "submission.py"
            script.write_text(source, encoding="utf-8")
            command = [
                "docker", "run", "--rm", "--network", "none", "--read-only", "--cap-drop", "ALL",
                "--security-opt", "no-new-privileges", "--pids-limit", "64", "--memory", "128m", "--cpus", "0.5",
                "--tmpfs", "/tmp:rw,noexec,nosuid,size=16m", "-e", "PYTHONDONTWRITEBYTECODE=1",
                "-v", f"{directory}:/workspace:ro", "-w", "/workspace", "python:3.13-slim", "python", "submission.py",
            ]
            try:
                run = subprocess.run(command, capture_output=True, text=True, timeout=self.timeout_seconds, check=False)
                return {"status": "completed", "exit_code": run.returncode, "stdout": run.stdout[-12000:], "stderr": run.stderr[-12000:]}
            except subprocess.TimeoutExpired:
                return {"status": "failed", "error_reason": "TIMEOUT_LIMIT_EXCEEDED", "stdout": "", "stderr": "Execution exceeded the safe time limit."}
            except FileNotFoundError:
                return {"status": "failed", "error_reason": "DOCKER_UNAVAILABLE", "stdout": "", "stderr": "Docker Desktop is unavailable."}

    def review(self, filename: str, source: str) -> dict[str, Any]:
        diagnostics = self._diagnostics(filename, source)
        execution = self._execute(source)
        prompt = f"""You are a Socratic code tutor. Do not provide a full solution unless the learner asks.
Return ONLY valid JSON with title, narration, writing_lines, and scene.
Each scene action uses normalized coordinates. Use text/highlight/arrow actions to mark the most relevant line in a code-review panel, not an external editor.
Give 1-3 hints, identify evidence from diagnostics/runtime, and ask one question.
FILE: {filename}
DIAGNOSTICS: {json.dumps(diagnostics, ensure_ascii=False)[:8000]}
EXECUTION: {json.dumps(execution, ensure_ascii=False)[:8000]}
CODE CONTEXT:\n{TutorExtensions.code_context(source) if TutorExtensions else source[:18000]}"""
        lesson = self.ollama.generate_json(CODE_MODEL, prompt, timeout=120)
        lesson.setdefault("title", f"Code review: {Path(filename).name}")
        lesson.setdefault("narration", "I reviewed the evidence and prepared a guided hint.")
        lesson.setdefault("writing_lines", [])
        lesson.setdefault("scene", [])
        lesson["code_evidence"] = {"filename": filename, "diagnostics": diagnostics, "execution": execution}
        return lesson


class ProductionLayerBridge(QObject):
    """Thread-safe boundary: workers emit data only; Qt owns canvas mutation."""
    scene_ready = pyqtSignal(object)
    code_ready = pyqtSignal(object)
    telemetry_ready = pyqtSignal(object)

    def __init__(self) -> None:
        super().__init__()
        self.ollama = OllamaLocalClient()
        self.tracer = PaddleSemanticTracer()
        self.code_tutor = SecureCodeTutor(self.ollama)
        self.pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="omnitutor")

    def _telemetry(self, event: str, **details: Any) -> None:
        self.telemetry_ready.emit({"event": event, "timestamp": time.time(), **details})

    def submit_frame(self, frame_bgr: np.ndarray, source_id: str, intent: str = "Explain and annotate this reference.") -> None:
        copied = frame_bgr.copy()
        self.pool.submit(self._run_frame, copied, source_id, intent)

    def submit_video(self, path: str, seconds: float = 0.0, intent: str = "Explain and annotate this lecture frame.") -> None:
        self.pool.submit(self._run_video, path, seconds, intent)

    def submit_code(self, filename: str, source: str) -> None:
        self.pool.submit(self._run_code, filename, source)

    def shutdown(self) -> None:
        """Cancel queued jobs; a running local model request ends at its configured timeout."""
        self.pool.shutdown(wait=False, cancel_futures=True)

    def _run_video(self, path: str, seconds: float, intent: str) -> None:
        started = time.perf_counter()
        try:
            self._run_frame(extract_video_frame(path, seconds), f"video:{Path(path).name}@{seconds:.2f}s", intent)
        except Exception as error:
            self._telemetry("video_trace_failed", error=str(error), latency_ms=round((time.perf_counter() - started) * 1000, 2))

    def _run_frame(self, frame_bgr: np.ndarray, source_id: str, intent: str) -> None:
        started = time.perf_counter()
        try:
            trace_actions, text_blocks, source = self.tracer.analyze(frame_bgr, source_id)
            prompt = f"""Analyze this lecture/reference frame for a tutor. Return ONLY JSON: title, narration, writing_lines, scene.
Scene actions use normalized 0..1 coordinates and only: stroke, arrow, shape, text, highlight, function_plot.
Use the supplied OCR text and local trace evidence. Draw a clean teaching redraw, not decoration. Link spoken ideas with segment_id when practical.
INTENT: {intent}
OCR: {json.dumps(text_blocks, ensure_ascii=False)[:10000]}
LOCAL_TRACE_COUNT: {len(trace_actions)}
SOURCE: {json.dumps(source)}"""
            semantic = self.ollama.generate_json(VISION_MODEL, prompt, image_bgr=frame_bgr, timeout=180)
            semantic.setdefault("title", "Visual explanation")
            semantic.setdefault("narration", "I traced and annotated the visible reference.")
            semantic.setdefault("writing_lines", [])
            semantic["scene"] = trace_actions + list(semantic.get("scene", []))
            semantic["trace_provenance"] = {"source": source, "ocr": text_blocks}
            self.scene_ready.emit(semantic)
            self._telemetry("frame_trace_completed", source_id=source_id, ocr_blocks=len(text_blocks), trace_actions=len(trace_actions), latency_ms=round((time.perf_counter() - started) * 1000, 2))
        except Exception as error:
            self._telemetry("frame_trace_failed", source_id=source_id, error=str(error), latency_ms=round((time.perf_counter() - started) * 1000, 2))

    def _run_code(self, filename: str, source: str) -> None:
        started = time.perf_counter()
        try:
            result = self.code_tutor.review(filename, source)
            self.code_ready.emit(result)
            self._telemetry("code_review_completed", filename=filename, latency_ms=round((time.perf_counter() - started) * 1000, 2))
        except Exception as error:
            self._telemetry("code_review_failed", filename=filename, error=str(error), latency_ms=round((time.perf_counter() - started) * 1000, 2))


class LocalOmniApi:
    """Optional localhost-only FastAPI + WebSocket control plane."""
    def __init__(self, bridge: ProductionLayerBridge, host: str = "127.0.0.1", port: int = 8765) -> None:
        self.bridge, self.host, self.port = bridge, host, int(port)
        self.app = FastAPI(title="Omnitutor local bridge", docs_url=None, redoc_url=None)
        self._events: queue.Queue[dict[str, Any]] = queue.Queue(maxsize=256)
        self._server: Optional[uvicorn.Server] = None
        self._thread: Optional[threading.Thread] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._clients: set[WebSocket] = set()
        self._client_lock = threading.Lock()
        bridge.telemetry_ready.connect(self.publish)
        self._routes()

    def publish(self, event: dict[str, Any]) -> None:
        """Keep HTTP polling and active local WebSocket clients in sync."""
        normalized = dict(event)
        try:
            self._events.put_nowait(normalized)
        except queue.Full:
            try: self._events.get_nowait()
            except queue.Empty: pass
            try: self._events.put_nowait(normalized)
            except queue.Full: pass
        if self._loop and self._loop.is_running():
            try:
                asyncio.run_coroutine_threadsafe(self._broadcast(normalized), self._loop)
            except RuntimeError:
                pass

    async def _broadcast(self, event: dict[str, Any]) -> None:
        with self._client_lock:
            clients = tuple(self._clients)
        stale: list[WebSocket] = []
        for client in clients:
            try:
                await client.send_json({"type": "telemetry", "data": event})
            except Exception:
                stale.append(client)
        if stale:
            with self._client_lock:
                for client in stale:
                    self._clients.discard(client)

    def _routes(self) -> None:
        @self.app.on_event("startup")
        async def remember_loop() -> None:
            self._loop = asyncio.get_running_loop()

        @self.app.on_event("shutdown")
        async def forget_loop() -> None:
            self._loop = None
        @self.app.get("/health")
        async def health() -> dict[str, Any]:
            return {"status": "ok", "host": self.host, "port": self.port}

        @self.app.get("/events")
        async def events() -> list[dict[str, Any]]:
            values: list[dict[str, Any]] = []
            while len(values) < 100:
                try: values.append(self._events.get_nowait())
                except queue.Empty: break
            return values

        @self.app.websocket("/ws")
        async def websocket_control(ws: WebSocket) -> None:
            await ws.accept()
            with self._client_lock:
                self._clients.add(ws)
            try:
                while True:
                    message = await ws.receive_json()
                    kind = str(message.get("type", ""))
                    if kind == "trace_video":
                        self.bridge.submit_video(str(message.get("path", "")), float(message.get("seconds", 0.0)), str(message.get("intent", "Explain this frame.")))
                    elif kind == "code_review":
                        self.bridge.submit_code(str(message.get("filename", "submission.py")), str(message.get("source", "")))
                    elif kind != "ping":
                        await ws.send_json({"status": "error", "error": "unsupported message type"})
                        continue
                    await ws.send_json({"status": "queued" if kind != "ping" else "pong", "type": kind})
            except WebSocketDisconnect:
                pass
            finally:
                with self._client_lock:
                    self._clients.discard(ws)

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        config = uvicorn.Config(self.app, host=self.host, port=self.port, log_level="warning", access_log=False)
        self._server = uvicorn.Server(config)
        self._thread = threading.Thread(target=self._server.run, daemon=True, name="omnitutor-local-api")
        self._thread.start()

    def stop(self) -> None:
        if self._server:
            self._server.should_exit = True
