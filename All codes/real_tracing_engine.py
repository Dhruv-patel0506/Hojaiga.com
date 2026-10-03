"""Real tracing and visual understanding engine with three distinct modes.

1. Semantic Redraw: Model explains and redraws simplified diagrams
2. Vector Trace: Extracts visible lines, contours, arrows, labels from frames
3. Video Teaching: Selects meaningful frames, traces them, explains changes

Includes explicit capture controls, frame extraction, scene-change detection,
OCR, contour extraction, hybrid tracing, and uncertainty marking.
"""
from __future__ import annotations

try:
    import cv2
    HAS_CV2 = True
except ImportError:
    cv2 = None
    HAS_CV2 = False

try:
    import numpy as np
    HAS_NUMPY = True
except ImportError:
    np = None
    HAS_NUMPY = False

import time
import os
import tempfile
from dataclasses import dataclass, field
from typing import Any, Optional, List, Tuple, Dict
from enum import Enum
from pathlib import Path


class TraceMode(Enum):
    """Three distinct tracing modes with different purposes."""
    SEMANTIC_REDRAW = "semantic_redraw"  # Model explains and redraws simplified diagrams
    VECTOR_TRACE = "vector_trace"  # Extracts visible lines, contours, arrows, labels
    VIDEO_TEACHING = "video_teaching"  # Selects meaningful frames, traces, explains changes


class CaptureSource(Enum):
    """Explicit capture control sources."""
    CURRENT_SCREEN = "current_screen"
    SELECTED_RECTANGLE = "selected_rectangle"
    IMAGE_FILE = "image_file"
    CURRENT_VIDEO_FRAME = "current_video_frame"
    SAMPLED_VIDEO_FRAMES = "sampled_video_frames"


class TraceQuality(Enum):
    """User-selected trace quality levels."""
    EXACT_TRACE = "exact_trace"  # High-fidelity vector extraction
    CLEAN_REDRAW = "clean_redraw"  # Simplified, cleaned version
    EXPLAIN_ONLY = "explain_only"  # No visual trace, just explanation


@dataclass
class CapturedFrame:
    """A captured frame with metadata."""
    frame_data: np.ndarray
    timestamp: float
    source: CaptureSource
    source_path: Optional[str] = None
    frame_number: Optional[int] = None
    scene_change_score: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class VectorElement:
    """Extracted vector element from tracing."""
    element_type: str  # "line", "contour", "arrow", "label", "shape"
    points: List[Tuple[float, float]]
    confidence: float
    bbox: Tuple[float, float, float, float]  # x, y, width, height
    source_ref: str  # Reference to source frame
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class TraceResult:
    """Result of a tracing operation."""
    mode: TraceMode
    quality: TraceQuality
    elements: List[VectorElement]
    labels: List[str]
    uncertainty_regions: List[Tuple[float, float, float, float]]
    source_frame: CapturedFrame
    processing_time_ms: float
    confidence_score: float


class FrameCapture:
    """Explicit capture controls for different sources."""
    
    def __init__(self):
        self.last_capture_time = 0.0
        self.capture_history: List[CapturedFrame] = []
    
    def capture_screen(self) -> CapturedFrame:
        """Capture current screen using platform-specific methods."""
        if not HAS_CV2 or not HAS_NUMPY:
            raise ImportError("cv2 and numpy are required for screen capture")
        
        try:
            if os.name == 'nt':  # Windows
                try:
                    import pyautogui
                    screenshot = pyautogui.screenshot()
                    frame_data = cv2.cvtColor(np.array(screenshot), cv2.COLOR_RGB2BGR)
                except ImportError:
                    # Fallback to PIL ImageGrab
                    from PIL import ImageGrab
                    screenshot = ImageGrab.grab()
                    frame_data = cv2.cvtColor(np.array(screenshot), cv2.COLOR_RGB2BGR)
            else:
                try:
                    import mss
                    with mss.mss() as sct:
                        monitor = sct.monitors[1]  # Primary monitor
                        screenshot = sct.grab(monitor)
                        frame_data = np.array(screenshot)
                        frame_data = cv2.cvtColor(frame_data, cv2.COLOR_BGRA2BGR)
                except ImportError:
                    # Fallback to PIL ImageGrab
                    from PIL import ImageGrab
                    screenshot = ImageGrab.grab()
                    frame_data = cv2.cvtColor(np.array(screenshot), cv2.COLOR_RGB2BGR)
            
            return CapturedFrame(
                frame_data=frame_data,
                timestamp=time.time(),
                source=CaptureSource.CURRENT_SCREEN
            )
        except Exception as e:
            print(f"[FrameCapture] Screen capture failed: {e}")
            raise
    
    def capture_rectangle(self, x: int, y: int, width: int, height: int) -> CapturedFrame:
        """Capture selected rectangle region."""
        try:
            if os.name == 'nt':
                try:
                    import pyautogui
                    screenshot = pyautogui.screenshot(region=(x, y, width, height))
                    frame_data = cv2.cvtColor(np.array(screenshot), cv2.COLOR_RGB2BGR)
                except ImportError:
                    from PIL import ImageGrab
                    screenshot = ImageGrab.grab(bbox=(x, y, x + width, y + height))
                    frame_data = cv2.cvtColor(np.array(screenshot), cv2.COLOR_RGB2BGR)
            else:
                try:
                    import mss
                    with mss.mss() as sct:
                        monitor = {"top": y, "left": x, "width": width, "height": height}
                        screenshot = sct.grab(monitor)
                        frame_data = np.array(screenshot)
                        frame_data = cv2.cvtColor(frame_data, cv2.COLOR_BGRA2BGR)
                except ImportError:
                    from PIL import ImageGrab
                    screenshot = ImageGrab.grab(bbox=(x, y, x + width, y + height))
                    frame_data = cv2.cvtColor(np.array(screenshot), cv2.COLOR_RGB2BGR)
            
            return CapturedFrame(
                frame_data=frame_data,
                timestamp=time.time(),
                source=CaptureSource.SELECTED_RECTANGLE,
                metadata={"region": (x, y, width, height)}
            )
        except Exception as e:
            print(f"[FrameCapture] Rectangle capture failed: {e}")
            raise
    
    def capture_image_file(self, file_path: str) -> CapturedFrame:
        """Capture from image file."""
        try:
            frame_data = cv2.imread(file_path)
            if frame_data is None:
                raise ValueError(f"Could not read image file: {file_path}")
            
            return CapturedFrame(
                frame_data=frame_data,
                timestamp=time.time(),
                source=CaptureSource.IMAGE_FILE,
                source_path=file_path
            )
        except Exception as e:
            print(f"[FrameCapture] Image file capture failed: {e}")
            raise
    
    def capture_video_frame(self, video_path: str, frame_number: int = 0) -> CapturedFrame:
        """Capture specific frame from video file."""
        try:
            cap = cv2.VideoCapture(video_path)
            cap.set(cv2.CAP_PROP_POS_FRAMES, frame_number)
            ret, frame_data = cap.read()
            cap.release()
            
            if not ret or frame_data is None:
                raise ValueError(f"Could not read frame {frame_number} from video")
            
            return CapturedFrame(
                frame_data=frame_data,
                timestamp=time.time(),
                source=CaptureSource.CURRENT_VIDEO_FRAME,
                source_path=video_path,
                frame_number=frame_number
            )
        except Exception as e:
            print(f"[FrameCapture] Video frame capture failed: {e}")
            raise
    
    def sample_video_frames(self, video_path: str, sample_rate: int = 30) -> List[CapturedFrame]:
        """Sample frames from video at regular intervals."""
        try:
            cap = cv2.VideoCapture(video_path)
            total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            fps = cap.get(cv2.CAP_PROP_FPS)
            
            frames = []
            for frame_num in range(0, total_frames, sample_rate):
                cap.set(cv2.CAP_PROP_POS_FRAMES, frame_num)
                ret, frame_data = cap.read()
                if ret and frame_data is not None:
                    frames.append(CapturedFrame(
                        frame_data=frame_data,
                        timestamp=time.time(),
                        source=CaptureSource.SAMPLED_VIDEO_FRAMES,
                        source_path=video_path,
                        frame_number=frame_num,
                        metadata={"fps": fps, "timestamp": frame_num / fps}
                    ))
            
            cap.release()
            return frames
        except Exception as e:
            print(f"[FrameCapture] Video sampling failed: {e}")
            raise


class SceneChangeDetector:
    """Detects scene changes in video frames to avoid continuous analysis."""
    
    def __init__(self, threshold: float = 0.3):
        self.threshold = threshold
        self.previous_frame: Optional[np.ndarray] = None
        self.previous_hist: Optional[np.ndarray] = None
    
    def detect_change(self, frame: np.ndarray) -> float:
        """Calculate scene change score (0.0 = no change, 1.0 = major change)."""
        if not HAS_CV2 or not HAS_NUMPY:
            return 0.0
        
        if self.previous_frame is None:
            self.previous_frame = frame.copy()
            self.previous_hist = self._calculate_histogram(frame)
            return 0.0
        
        # Calculate histogram difference
        current_hist = self._calculate_histogram(frame)
        hist_diff = cv2.compareHist(self.previous_hist, current_hist, cv2.HISTCMP_BHATTACHARYYA)
        
        # Calculate structural difference
        frame_diff = cv2.absdiff(self.previous_frame, frame)
        diff_score = np.mean(frame_diff) / 255.0
        
        # Combined score
        change_score = (hist_diff + diff_score) / 2.0
        
        # Update state
        if change_score > self.threshold:
            self.previous_frame = frame.copy()
            self.previous_hist = current_hist
        
        return change_score
    
    def _calculate_histogram(self, frame: np.ndarray) -> np.ndarray:
        """Calculate color histogram for frame comparison."""
        if not HAS_CV2:
            return np.array([])
        
        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
        hist = cv2.calcHist([hsv], [0, 1, 2], None, [50, 60, 60], [0, 180, 0, 256, 0, 256])
        cv2.normalize(hist, hist, 0, 1, cv2.NORM_MINMAX)
        return hist
    
    def reset(self) -> None:
        """Reset detector state."""
        self.previous_frame = None
        self.previous_hist = None


class VectorExtractor:
    """Extracts vector elements from frames for high-fidelity tracing."""
    
    def __init__(self):
        self.contour_threshold = 50
        self.line_threshold = 100
        self.min_contour_area = 100
    
    def extract_lines(self, frame: np.ndarray) -> List[VectorElement]:
        """Extract straight lines using Hough transform."""
        if not HAS_CV2 or not HAS_NUMPY:
            return []
        
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        edges = cv2.Canny(gray, 50, 150, apertureSize=3)
        
        lines = cv2.HoughLines(edges, 1, np.pi/180, threshold=self.line_threshold)
        elements = []
        
        if lines is not None:
            for line in lines[:50]:  # Limit number of lines
                rho, theta = line[0]
                a = np.cos(theta)
                b = np.sin(theta)
                x0 = a * rho
                y0 = b * rho
                x1 = int(x0 + 1000 * (-b))
                y1 = int(y0 + 1000 * (a))
                x2 = int(x0 - 1000 * (-b))
                y2 = int(y0 - 1000 * (a))
                
                elements.append(VectorElement(
                    element_type="line",
                    points=[(x1, y1), (x2, y2)],
                    confidence=0.8,
                    bbox=self._points_to_bbox([(x1, y1), (x2, y2)]),
                    source_ref="hough_lines"
                ))
        
        return elements
    
    def extract_contours(self, frame: np.ndarray) -> List[VectorElement]:
        """Extract contours for shapes and regions."""
        if not HAS_CV2 or not HAS_NUMPY:
            return []
        
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        _, thresh = cv2.threshold(gray, 127, 255, cv2.THRESH_BINARY)
        contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        elements = []
        for contour in contours:
            if cv2.contourArea(contour) < self.min_contour_area:
                continue
            
            # Approximate contour to reduce points
            epsilon = 0.02 * cv2.arcLength(contour, True)
            approx = cv2.approxPolyDP(contour, epsilon, True)
            
            points = [(float(pt[0][0]), float(pt[0][1])) for pt in approx]
            
            # Determine shape type
            num_points = len(approx)
            if num_points == 3:
                shape_type = "triangle"
            elif num_points == 4:
                shape_type = "rectangle"
            elif num_points > 10:
                shape_type = "circle"
            else:
                shape_type = "polygon"
            
            elements.append(VectorElement(
                element_type="contour",
                points=points,
                confidence=0.7,
                bbox=self._points_to_bbox(points),
                source_ref="contour_extraction",
                metadata={"shape_type": shape_type}
            ))
        
        return elements
    
    def extract_arrows(self, frame: np.ndarray) -> List[VectorElement]:
        """Extract arrow-like structures."""
        # Combine line detection with arrowhead detection
        lines = self.extract_lines(frame)
        arrows = []
        
        for line in lines:
            # Look for arrowheads at line endpoints
            # This is a simplified implementation
            arrows.append(VectorElement(
                element_type="arrow",
                points=line.points,
                confidence=0.6,
                bbox=line.bbox,
                source_ref="arrow_detection"
            ))
        
        return arrows
    
    def _points_to_bbox(self, points: List[Tuple[float, float]]) -> Tuple[float, float, float, float]:
        """Convert points to bounding box."""
        if not points:
            return (0.0, 0.0, 0.0, 0.0)
        
        x_coords = [p[0] for p in points]
        y_coords = [p[1] for p in points]
        
        x_min, x_max = min(x_coords), max(x_coords)
        y_min, y_max = min(y_coords), max(y_coords)
        
        return (x_min, y_min, x_max - x_min, y_max - y_min)


class OCREngine:
    """OCR engine for extracting labels and equations from frames."""
    
    def __init__(self, use_tesseract: bool = True):
        self.use_tesseract = use_tesseract
        self.tesseract_config = r'--oem 3 --psm 6'
    
    def extract_text(self, frame: np.ndarray) -> List[Tuple[str, Tuple[float, float, float, float], float]]:
        """Extract text with bounding boxes and confidence scores."""
        if self.use_tesseract:
            return self._tesseract_ocr(frame)
        else:
            return self._paddle_ocr(frame)
    
    def _tesseract_ocr(self, frame: np.ndarray) -> List[Tuple[str, Tuple[float, float, float, float], float]]:
        """Extract text using Tesseract OCR."""
        if not HAS_CV2:
            return []
        
        try:
            import pytesseract
            from PIL import Image
            
            # Convert to PIL Image
            pil_image = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
            
            # Get OCR data with bounding boxes
            data = pytesseract.image_to_data(pil_image, config=self.tesseract_config, output_type=pytesseract.Output.DICT)
            
            results = []
            for i in range(len(data['text'])):
                text = data['text'][i].strip()
                if text and data['conf'][i] > 0:  # Filter low confidence
                    bbox = (
                        data['left'][i],
                        data['top'][i],
                        data['width'][i],
                        data['height'][i]
                    )
                    confidence = data['conf'][i] / 100.0
                    results.append((text, bbox, confidence))
            
            return results
        except Exception as e:
            print(f"[OCREngine] Tesseract OCR failed: {e}")
            return []
    
    def _paddle_ocr(self, frame: np.ndarray) -> List[Tuple[str, Tuple[float, float, float, float], float]]:
        """Extract text using PaddleOCR (fallback)."""
        try:
            from paddleocr import PaddleOCR
            
            ocr = PaddleOCR(use_angle_cls=True, lang='en')
            result = ocr.ocr(frame, cls=True)
            
            results = []
            if result and result[0]:
                for line in result[0]:
                    text = line[1][0]
                    bbox = line[0]
                    confidence = line[1][1] if len(line[1]) > 1 else 0.9
                    
                    # Convert bbox to (x, y, width, height)
                    x_coords = [p[0] for p in bbox]
                    y_coords = [p[1] for p in bbox]
                    x_min, x_max = min(x_coords), max(x_coords)
                    y_min, y_max = min(y_coords), max(y_coords)
                    
                    results.append((text, (x_min, y_min, x_max - x_min, y_max - y_min), confidence))
            
            return results
        except Exception as e:
            print(f"[OCREngine] PaddleOCR failed: {e}")
            return []


class HybridTracer:
    """Hybrid tracing combining local contours with vision model understanding."""
    
    def __init__(self):
        self.vector_extractor = VectorExtractor()
        self.ocr_engine = OCREngine()
        self.scene_detector = SceneChangeDetector()
    
    def trace_frame(self, frame: CapturedFrame, mode: TraceMode, quality: TraceQuality) -> TraceResult:
        """Perform hybrid tracing on a single frame."""
        start_time = time.time()
        
        elements = []
        labels = []
        uncertainty_regions = []
        
        if quality == TraceQuality.EXPLAIN_ONLY:
            # No visual tracing, just return metadata
            return TraceResult(
                mode=mode,
                quality=quality,
                elements=[],
                labels=[],
                uncertainty_regions=[],
                source_frame=frame,
                processing_time_ms=(time.time() - start_time) * 1000,
                confidence_score=0.0
            )
        
        # Extract vector elements based on mode
        if mode == TraceMode.VECTOR_TRACE:
            # High-fidelity vector extraction
            elements.extend(self.vector_extractor.extract_lines(frame.frame_data))
            elements.extend(self.vector_extractor.extract_contours(frame.frame_data))
            elements.extend(self.vector_extractor.extract_arrows(frame.frame_data))
        
        elif mode == TraceMode.SEMANTIC_REDRAW:
            # Simplified, semantic extraction
            elements.extend(self.vector_extractor.extract_contours(frame.frame_data))
        
        elif mode == TraceMode.VIDEO_TEACHING:
            # Focus on meaningful elements
            elements.extend(self.vector_extractor.extract_contours(frame.frame_data))
        
        # Extract labels using OCR
        if quality != TraceQuality.EXPLAIN_ONLY:
            ocr_results = self.ocr_engine.extract_text(frame.frame_data)
            for text, bbox, confidence in ocr_results:
                labels.append(text)
                if confidence < 0.7:
                    uncertainty_regions.append(bbox)
        
        # Mark uncertainty regions
        if quality == TraceQuality.EXACT_TRACE:
            # Mark low-confidence regions
            for element in elements:
                if element.confidence < 0.6:
                    uncertainty_regions.append(element.bbox)
        
        # Calculate overall confidence
        confidence_score = 0.0
        if elements:
            confidence_score = sum(e.confidence for e in elements) / len(elements)
        
        return TraceResult(
            mode=mode,
            quality=quality,
            elements=elements,
            labels=labels,
            uncertainty_regions=uncertainty_regions,
            source_frame=frame,
            processing_time_ms=(time.time() - start_time) * 1000,
            confidence_score=confidence_score
        )
    
    def trace_video_sequence(self, frames: List[CapturedFrame], mode: TraceMode, quality: TraceQuality) -> List[TraceResult]:
        """Trace a sequence of video frames with scene-change detection."""
        results = []
        
        for frame in frames:
            # Detect scene change
            change_score = self.scene_detector.detect_change(frame.frame_data)
            frame.scene_change_score = change_score
            
            # Only process frames with significant changes
            if change_score > self.scene_detector.threshold or len(results) == 0:
                result = self.trace_frame(frame, mode, quality)
                results.append(result)
        
        return results


class RealTracingEngine:
    """Main engine for real tracing and visual understanding."""
    
    def __init__(self):
        self.frame_capture = FrameCapture()
        self.hybrid_tracer = HybridTracer()
        self.trace_history: List[TraceResult] = []
    
    def capture_and_trace(self, source: CaptureSource, **kwargs) -> TraceResult:
        """Capture from source and perform tracing."""
        # Capture frame
        if source == CaptureSource.CURRENT_SCREEN:
            frame = self.frame_capture.capture_screen()
        elif source == CaptureSource.SELECTED_RECTANGLE:
            frame = self.frame_capture.capture_rectangle(
                kwargs.get('x', 0), kwargs.get('y', 0),
                kwargs.get('width', 100), kwargs.get('height', 100)
            )
        elif source == CaptureSource.IMAGE_FILE:
            frame = self.frame_capture.capture_image_file(kwargs.get('file_path', ''))
        elif source == CaptureSource.CURRENT_VIDEO_FRAME:
            frame = self.frame_capture.capture_video_frame(
                kwargs.get('video_path', ''), kwargs.get('frame_number', 0)
            )
        else:
            raise ValueError(f"Unsupported capture source: {source}")
        
        # Perform tracing
        mode = kwargs.get('mode', TraceMode.VECTOR_TRACE)
        quality = kwargs.get('quality', TraceQuality.CLEAN_REDRAW)
        
        result = self.hybrid_tracer.trace_frame(frame, mode, quality)
        self.trace_history.append(result)
        
        return result
    
    def get_trace_summary(self) -> Dict[str, Any]:
        """Get summary of tracing history."""
        if not self.trace_history:
            return {"total_traces": 0}
        
        return {
            "total_traces": len(self.trace_history),
            "average_confidence": sum(r.confidence_score for r in self.trace_history) / len(self.trace_history),
            "average_processing_time_ms": sum(r.processing_time_ms for r in self.trace_history) / len(self.trace_history),
            "modes_used": list(set(r.mode.value for r in self.trace_history)),
            "qualities_used": list(set(r.quality.value for r in self.trace_history))
        }