"""
Audio Capture Manager - Microphone Audio Recording

This manages audio capture from the microphone for voice input.
Equivalent to BuddyDictationManager audio capture in Clicky.
"""

import asyncio
from typing import Optional, Callable
from PyQt5.QtCore import QObject, pyqtSignal
import pyaudio

from ..utils.logger import setup_logger


class AudioCaptureManager(QObject):
    """
    Manages audio capture from the microphone.
    Uses PyAudio for cross-platform audio capture.
    """

    # Signals
    audio_level_changed = pyqtSignal(float)  # Audio level (0.0 to 1.0)
    audio_data_available = pyqtSignal(bytes)  # Raw audio data
    error_occurred = pyqtSignal(str)  # Error message

    def __init__(self):
        """Initialize the audio capture manager."""
        super().__init__()

        self.logger = setup_logger("AudioCaptureManager")

        # Audio configuration
        self.sample_rate = 16000  # 16kHz for speech recognition
        self.channels = 1  # Mono
        self.chunk_size = 1024
        self.format = pyaudio.paInt16  # 16-bit PCM

        # PyAudio instance
        self.pyaudio: Optional[pyaudio.PyAudio] = None
        self.stream: Optional[pyaudio.Stream] = None

        # Capture state
        self._is_capturing = False
        self._capture_task: Optional[asyncio.Task] = None

        # Audio level calculation
        self._audio_level = 0.0
        self._level_calculation_interval = 0.05  # 50ms

        self.logger.info("Audio capture manager initialized")

    def start(self):
        """Start the audio capture manager."""
        self.logger.info("Starting audio capture manager...")
        # Initialize PyAudio
        try:
            self.pyaudio = pyaudio.PyAudio()
            self.logger.info("PyAudio initialized")
        except Exception as e:
            self.logger.error(f"Failed to initialize PyAudio: {e}")
            self.error_occurred.emit(f"Failed to initialize audio: {str(e)}")

    def stop(self):
        """Stop the audio capture manager."""
        self.logger.info("Stopping audio capture manager...")
        if self.stream:
            self.stream.stop_stream()
            self.stream.close()
            self.stream = None
        if self.pyaudio:
            self.pyaudio.terminate()
            self.pyaudio = None

    def start_recording(self):
        """Start recording audio."""
        self.logger.info("Starting audio recording...")
        if not self.pyaudio:
            self.start()

        try:
            self.stream = self.pyaudio.open(
                format=self.format,
                channels=self.channels,
                rate=self.sample_rate,
                input=True,
                frames_per_buffer=self.chunk_size,
                stream_callback=self._audio_callback
            )
            self.stream.start_stream()
            self._is_capturing = True
            self.logger.info("Audio recording started")
        except Exception as e:
            self.logger.error(f"Failed to start recording: {e}")
            self.error_occurred.emit(f"Failed to start recording: {str(e)}")

    def stop_recording(self):
        """Stop recording audio."""
        self.logger.info("Stopping audio recording...")
        if self.stream:
            self.stream.stop_stream()
            self.stream.close()
            self.stream = None
        self._is_capturing = False
        self.logger.info("Audio recording stopped")

    def get_audio_data(self) -> Optional[bytes]:
        """Get captured audio data."""
        # For now, return None - will implement buffer
        return None

    def _audio_callback(self, in_data, frame_count, time_info, status):
        """Audio stream callback."""
        # Calculate audio level without numpy
        import array
        audio_data = array.array('h', in_data)
        level = sum(abs(x) for x in audio_data) / (len(audio_data) * 32768.0)
        self._audio_level = level
        self.audio_level_changed.emit(level)

        return (in_data, pyaudio.paContinue)

        self.logger.info("Audio capture manager initialized")

    async def start_capture(self):
        """Start audio capture from the microphone."""
        if self._is_capturing:
            self.logger.warning("Audio capture already in progress")
            return

        try:
            # Initialize PyAudio
            self.pyaudio = pyaudio.PyAudio()

            # Open audio stream
            self.stream = self.pyaudio.open(
                format=self.format,
                channels=self.channels,
                rate=self.sample_rate,
                input=True,
                frames_per_buffer=self.chunk_size,
                stream_callback=self._audio_callback
            )

            # Start the stream
            self.stream.start_stream()

            self._is_capturing = True
            self.logger.info("Audio capture started")

            # Start audio level monitoring
            self._capture_task = asyncio.create_task(self._monitor_audio_level())

        except Exception as e:
            self.logger.error(f"Failed to start audio capture: {e}")
            self.error_occurred.emit(f"Failed to start audio capture: {str(e)}")
            await self.stop_capture()

    async def stop_capture(self):
        """Stop audio capture."""
        if not self._is_capturing:
            return

        try:
            # Stop the stream
            if self.stream:
                self.stream.stop_stream()
                self.stream.close()
                self.stream = None

            # Terminate PyAudio
            if self.pyaudio:
                self.pyaudio.terminate()
                self.pyaudio = None

            # Cancel monitoring task
            if self._capture_task:
                self._capture_task.cancel()
                self._capture_task = None

            self._is_capturing = False
            self.logger.info("Audio capture stopped")

        except Exception as e:
            self.logger.error(f"Error stopping audio capture: {e}")
            self.error_occurred.emit(f"Error stopping audio capture: {str(e)}")

    def _audio_callback(self, in_data, frame_count, time_info, status):
        """
        Audio stream callback function.

        Args:
            in_data: Raw audio data
            frame_count: Number of frames
            time_info: Timing information
            status: Stream status

        Returns:
            Tuple of (audio_data, pyaudio.paContinue)
        """
        if status:
            self.logger.warning(f"Audio callback status: {status}")

        # Emit audio data signal
        self.audio_data_available.emit(in_data)

        # Calculate audio level
        audio_level = self._calculate_audio_level(in_data)
        self._audio_level = audio_level
        self.audio_level_changed.emit(audio_level)

        return (in_data, pyaudio.paContinue)

    def _calculate_audio_level(self, audio_data: bytes) -> float:
        """
        Calculate audio level from raw audio data.

        Args:
            audio_data: Raw audio bytes

        Returns:
            Audio level between 0.0 and 1.0
        """
        try:
            # Convert bytes to numpy array
            audio_array = np.frombuffer(audio_data, dtype=np.int16)

            # Calculate RMS (root mean square)
            rms = np.sqrt(np.mean(audio_array.astype(np.float32) ** 2))

            # Normalize to 0.0-1.0 range
            # Assuming 16-bit audio, max value is 32768
            normalized_level = min(rms / 32768.0, 1.0)

            return normalized_level

        except Exception as e:
            self.logger.error(f"Error calculating audio level: {e}")
            return 0.0

    async def _monitor_audio_level(self):
        """Monitor and emit audio level updates."""
        while self._is_capturing:
            try:
                # The audio level is calculated in the callback
                # This task just ensures regular updates
                await asyncio.sleep(self._level_calculation_interval)

            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"Error monitoring audio level: {e}")
                break

    @property
    def is_capturing(self) -> bool:
        """Check if audio capture is active."""
        return self._is_capturing

    @property
    def current_audio_level(self) -> float:
        """Get current audio level."""
        return self._audio_level

    def cleanup(self):
        """Clean up resources."""
        if self._is_capturing:
            # This is a synchronous cleanup for shutdown
            try:
                if self.stream:
                    self.stream.stop_stream()
                    self.stream.close()
                    self.stream = None

                if self.pyaudio:
                    self.pyaudio.terminate()
                    self.pyaudio = None

                self._is_capturing = False

            except Exception as e:
                self.logger.error(f"Error during cleanup: {e}")

        self.logger.info("Audio capture manager cleaned up")