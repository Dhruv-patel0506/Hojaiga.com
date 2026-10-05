"""Real-time voice and synchronized annotation system.

Provides near-immediate feedback with streamed narration chunks synchronized
to visual annotations. Implements latency tracking and interruption support.
"""
from __future__ import annotations

import asyncio
import time
import threading
import queue
from dataclasses import dataclass, field
from typing import Any, Callable, Optional
from enum import Enum


class AudioState(Enum):
    """Audio playback states for synchronization."""
    IDLE = "idle"
    PLAYING = "playing"
    PAUSED = "paused"
    INTERRUPTED = "interrupted"
    COMPLETED = "completed"


@dataclass
class NarrationChunk:
    """A single chunk of streamed narration with linked annotations."""
    chunk_id: str
    text: str
    segment_id: str
    annotation_ids: list[str]
    start_time: float
    duration_ms: int
    priority: int = 0  # Higher priority chunks render first
    
    def __post_init__(self):
        if not self.chunk_id:
            self.chunk_id = f"chunk_{int(time.time() * 1000)}_{id(self)}"


@dataclass
class LatencyMetrics:
    """Latency measurements for performance tracking."""
    capture_time: float = 0.0
    reasoning_start: float = 0.0
    reasoning_end: float = 0.0
    first_audio_time: float = 0.0
    first_ink_time: float = 0.0
    full_scene_time: float = 0.0
    
    @property
    def reasoning_latency_ms(self) -> float:
        return (self.reasoning_end - self.reasoning_start) * 1000
    
    @property
    def first_audio_latency_ms(self) -> float:
        return (self.first_audio_time - self.capture_time) * 1000
    
    @property
    def first_ink_latency_ms(self) -> float:
        return (self.first_ink_time - self.capture_time) * 1000
    
    @property
    def total_latency_ms(self) -> float:
        return (self.full_scene_time - self.capture_time) * 1000
    
    def to_dict(self) -> dict[str, float]:
        return {
            "reasoning_ms": self.reasoning_latency_ms,
            "first_audio_ms": self.first_audio_latency_ms,
            "first_ink_ms": self.first_ink_latency_ms,
            "total_ms": self.total_latency_ms
        }


@dataclass
class SyncState:
    """Current synchronization state between audio and visuals."""
    current_chunk: Optional[NarrationChunk] = None
    pending_chunks: queue.Queue = field(default_factory=queue.Queue)
    rendered_annotations: set[str] = field(default_factory=set)
    audio_state: AudioState = AudioState.IDLE
    interruption_requested: bool = False
    last_update_time: float = field(default_factory=time.time)


class RealtimeVoiceSync:
    """Manages real-time voice streaming with synchronized annotation rendering.
    
    Implements near-immediate feedback through:
    - Streamed narration chunks instead of full responses
    - Segment-based annotation linking
    - Prioritized rendering for immediate visual feedback
    - Interruption support with state preservation
    - Comprehensive latency tracking
    """
    
    # Performance targets (in milliseconds)
    TARGET_CANVAS_RENDER_MS = 16.0
    TARGET_UI_ACK_MS = 100.0
    TARGET_FIRST_INK_MS = 50.0
    
    def __init__(self):
        self.sync_state = SyncState()
        self.latency_metrics = LatencyMetrics()
        self.annotation_renderer: Optional[Callable[[list[str]], None]] = None
        self.audio_player: Optional[Callable[[str], None]] = None
        self.is_running = False
        self.render_thread: Optional[threading.Thread] = None
        self.audio_thread: Optional[threading.Thread] = None
        self.chunk_queue: queue.Queue = queue.Queue(maxsize=100)
        self.lock = threading.Lock()
        
    def set_annotation_renderer(self, renderer: Callable[[list[str]], None]) -> None:
        """Set the callback for rendering annotations."""
        self.annotation_renderer = renderer
    
    def set_audio_player(self, player: Callable[[str], None]) -> None:
        """Set the callback for playing audio chunks."""
        self.audio_player = player
    
    def start(self) -> None:
        """Start the real-time synchronization system."""
        if self.is_running:
            return
        
        self.is_running = True
        self.sync_state.audio_state = AudioState.IDLE
        
        # Start render thread
        self.render_thread = threading.Thread(target=self._render_loop, daemon=True)
        self.render_thread.start()
        
        # Start audio thread
        self.audio_thread = threading.Thread(target=self._audio_loop, daemon=True)
        self.audio_thread.start()
    
    def stop(self) -> None:
        """Stop the real-time synchronization system."""
        self.is_running = False
        self.sync_state.interruption_requested = True
        
        if self.render_thread:
            self.render_thread.join(timeout=1.0)
        if self.audio_thread:
            self.audio_thread.join(timeout=1.0)
    
    def add_narration_chunk(self, chunk: NarrationChunk) -> None:
        """Add a narration chunk to the processing queue."""
        if not self.is_running:
            self.start()
        
        start_time = time.time()
        
        # Set latency metrics if this is the first chunk
        if self.latency_metrics.capture_time == 0.0:
            self.latency_metrics.capture_time = start_time
        
        with self.lock:
            self.chunk_queue.put(chunk)
            self.sync_state.last_update_time = start_time
    
    def interrupt(self) -> None:
        """Interrupt current playback and preserve completed state."""
        with self.lock:
            self.sync_state.interruption_requested = True
            self.sync_state.audio_state = AudioState.INTERRUPTED
            
            # Clear pending chunks but preserve rendered annotations
            while not self.chunk_queue.empty():
                try:
                    self.chunk_queue.get_nowait()
                except queue.Empty:
                    break
    
    def reset(self) -> None:
        """Reset the synchronization state for a new session."""
        with self.lock:
            self.sync_state = SyncState()
            self.latency_metrics = LatencyMetrics()
            
            # Clear queues
            while not self.chunk_queue.empty():
                try:
                    self.chunk_queue.get_nowait()
                except queue.Empty:
                    break
    
    def get_latency_report(self) -> dict[str, Any]:
        """Get current latency metrics and performance report."""
        return {
            "metrics": self.latency_metrics.to_dict(),
            "targets": {
                "canvas_render_ms": self.TARGET_CANVAS_RENDER_MS,
                "ui_ack_ms": self.TARGET_UI_ACK_MS,
                "first_ink_ms": self.TARGET_FIRST_INK_MS
            },
            "performance": {
                "canvas_target_met": self.latency_metrics.first_ink_latency_ms <= self.TARGET_FIRST_INK_MS,
                "ui_target_met": self.latency_metrics.first_audio_latency_ms <= self.TARGET_UI_ACK_MS
            },
            "sync_state": {
                "audio_state": self.sync_state.audio_state.value,
                "pending_chunks": self.chunk_queue.qsize(),
                "rendered_count": len(self.sync_state.rendered_annotations)
            }
        }
    
    def _render_loop(self) -> None:
        """Render loop for processing narration chunks and annotations."""
        while self.is_running:
            try:
                # Get next chunk with timeout
                chunk = self.chunk_queue.get(timeout=0.1)
                
                # Check for interruption
                if self.sync_state.interruption_requested:
                    self.sync_state.interruption_requested = False
                    self.sync_state.audio_state = AudioState.IDLE
                    continue
                
                # Process chunk
                self._process_chunk(chunk)
                
            except queue.Empty:
                continue
            except Exception as e:
                print(f"[VoiceSync] Render error: {e}")
    
    def _audio_loop(self) -> None:
        """Audio playback loop for synchronized narration."""
        while self.is_running:
            try:
                with self.lock:
                    chunk = self.sync_state.current_chunk
                    if chunk and self.sync_state.audio_state == AudioState.IDLE:
                        self.sync_state.audio_state = AudioState.PLAYING
                        
                        # Update latency metrics
                        if self.latency_metrics.first_audio_time == 0.0:
                            self.latency_metrics.first_audio_time = time.time()
                        
                        # Play audio
                        if self.audio_player:
                            self.audio_player(chunk.text)
                        
                        # Mark as completed
                        self.sync_state.audio_state = AudioState.COMPLETED
                        self.sync_state.current_chunk = None
                
                time.sleep(0.01)  # Small sleep to prevent busy waiting
                
            except Exception as e:
                print(f"[VoiceSync] Audio error: {e}")
    
    def _process_chunk(self, chunk: NarrationChunk) -> None:
        """Process a narration chunk with synchronized annotation rendering."""
        start_time = time.time()
        
        # Set current chunk for audio thread
        with self.lock:
            self.sync_state.current_chunk = chunk
            self.sync_state.audio_state = AudioState.IDLE
        
        # Update reasoning latency
        if self.latency_metrics.reasoning_start == 0.0:
            self.latency_metrics.reasoning_start = start_time
        self.latency_metrics.reasoning_end = start_time
        
        # Render annotations immediately for immediate visual feedback
        self._render_annotations_immediate(chunk)
        
        # Update first ink latency
        if self.latency_metrics.first_ink_time == 0.0:
            self.latency_metrics.first_ink_time = time.time()
        
        # Calculate render time
        render_time = (time.time() - start_time) * 1000
        
        # Log if render target not met
        if render_time > self.TARGET_CANVAS_RENDER_MS:
            print(f"[VoiceSync] Render target exceeded: {render_time:.2f}ms > {self.TARGET_CANVAS_RENDER_MS}ms")
    
    def _render_annotations_immediate(self, chunk: NarrationChunk) -> None:
        """Render annotations for immediate visual feedback."""
        if not self.annotation_renderer:
            return
        
        # Filter to only unrendered annotations
        new_annotations = [
            ann_id for ann_id in chunk.annotation_ids 
            if ann_id not in self.sync_state.rendered_annotations
        ]
        
        if new_annotations:
            # Mark as rendered
            with self.lock:
                self.sync_state.rendered_annotations.update(new_annotations)
            
            # Render immediately
            try:
                self.annotation_renderer(new_annotations)
            except Exception as e:
                print(f"[VoiceSync] Annotation render error: {e}")


class StreamedNarrationGenerator:
    """Generates streamed narration chunks from model responses.
    
    Simulates streaming behavior by breaking responses into chunks
    with appropriate timing and annotation linking.
    """
    
    def __init__(self, chunk_size: int = 50, chunk_delay_ms: int = 100):
        self.chunk_size = chunk_size
        self.chunk_delay_ms = chunk_delay_ms
    
    def generate_chunks(self, text: str, annotation_map: dict[str, list[str]]) -> list[NarrationChunk]:
        """Generate narration chunks from text with annotation mapping."""
        chunks = []
        words = text.split()
        current_text = ""
        current_annotations = set()
        chunk_id = 0
        
        for i, word in enumerate(words):
            current_text += " " + word if current_text else word
            
            # Check if this word triggers any annotations
            for ann_id, keywords in annotation_map.items():
                if any(keyword.lower() in word.lower() for keyword in keywords):
                    current_annotations.add(ann_id)
            
            # Create chunk when size reached or at sentence boundaries
            if (len(current_text.split()) >= self.chunk_size or 
                word.endswith(('.', '!', '?'))):
                
                chunk = NarrationChunk(
                    chunk_id=f"chunk_{chunk_id}",
                    text=current_text.strip(),
                    segment_id=f"segment_{chunk_id}",
                    annotation_ids=list(current_annotations),
                    start_time=time.time(),
                    duration_ms=self.chunk_delay_ms
                )
                chunks.append(chunk)
                
                current_text = ""
                current_annotations = set()
                chunk_id += 1
        
        # Add remaining text
        if current_text.strip():
            chunk = NarrationChunk(
                chunk_id=f"chunk_{chunk_id}",
                text=current_text.strip(),
                segment_id=f"segment_{chunk_id}",
                annotation_ids=list(current_annotations),
                start_time=time.time(),
                duration_ms=self.chunk_delay_ms
            )
            chunks.append(chunk)
        
        return chunks


class InterruptionHandler:
    """Handles user interruptions with state preservation."""
    
    def __init__(self, voice_sync: RealtimeVoiceSync):
        self.voice_sync = voice_sync
        self.saved_state: dict[str, Any] = {}
    
    def interrupt_and_save(self) -> dict[str, Any]:
        """Interrupt current session and save state."""
        # Save current state
        self.saved_state = {
            "rendered_annotations": set(self.voice_sync.sync_state.rendered_annotations),
            "latency_metrics": self.voice_sync.latency_metrics,
            "timestamp": time.time()
        }
        
        # Interrupt
        self.voice_sync.interrupt()
        
        return self.saved_state
    
    def restore_state(self, state: dict[str, Any]) -> None:
        """Restore previously saved state."""
        self.voice_sync.sync_state.rendered_annotations = state.get("rendered_annotations", set())
        self.voice_sync.latency_metrics = state.get("latency_metrics", LatencyMetrics())
    
    def clear_saved_state(self) -> None:
        """Clear saved state."""
        self.saved_state = {}