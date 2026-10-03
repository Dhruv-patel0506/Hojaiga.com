"""
Buddy Audio Conversion Support - Audio Conversion Helpers (Clicky-style)

Shared audio conversion helpers for voice transcription providers.
Converted from BuddyAudioConversionSupport.swift to Windows Python.
"""

import struct
import wave
import io
import numpy as np
from typing import Optional

from ..utils.logger import setup_logger


class BuddyPCM16AudioConverter:
    """Converts audio buffers to PCM16 format."""

    def __init__(self, target_sample_rate: float = 16000.0):
        """
        Initialize the PCM16 audio converter.

        Args:
            target_sample_rate: Target sample rate in Hz
        """
        self.target_sample_rate = target_sample_rate
        self.logger = setup_logger("BuddyPCM16AudioConverter")

    def convert_to_pcm16_data(self, audio_data: bytes, source_sample_rate: float) -> Optional[bytes]:
        """
        Convert audio data to PCM16 format.

        Args:
            audio_data: Raw audio data
            source_sample_rate: Source sample rate in Hz

        Returns:
            PCM16 audio data or None if conversion fails
        """
        try:
            # If sample rates match, just convert to PCM16
            if source_sample_rate == self.target_sample_rate:
                return self._ensure_pcm16(audio_data)

            # Resample using numpy
            self.logger.info(f"Resampling from {source_sample_rate}Hz to {self.target_sample_rate}Hz")

            # Convert to numpy array
            audio_array = np.frombuffer(audio_data, dtype=np.int16)

            # Calculate resampling ratio
            ratio = self.target_sample_rate / source_sample_rate
            new_length = int(len(audio_array) * ratio)

            # Resample using linear interpolation
            resampled = np.interp(
                np.linspace(0, len(audio_array), new_length),
                np.arange(len(audio_array)),
                audio_array
            )

            # Convert back to bytes
            return resampled.astype(np.int16).tobytes()

        except Exception as e:
            self.logger.error(f"Error converting to PCM16: {e}")
            return None

    def _ensure_pcm16(self, audio_data: bytes) -> bytes:
        """Ensure audio data is in PCM16 format."""
        # If already 16-bit, return as-is
        if len(audio_data) % 2 == 0:
            return audio_data

        # Otherwise, pad to 16-bit alignment
        padding = 2 - (len(audio_data) % 2)
        return audio_data + b'\x00' * padding


class BuddyWAVFileBuilder:
    """Builds WAV file data from PCM16 audio."""

    @staticmethod
    def build_wav_data(
        pcm16_audio_data: bytes,
        sample_rate: int = 16000,
        channel_count: int = 1,
        bits_per_sample: int = 16
    ) -> bytes:
        """
        Build WAV file data from PCM16 audio.

        Args:
            pcm16_audio_data: PCM16 audio data
            sample_rate: Sample rate in Hz
            channel_count: Number of audio channels
            bits_per_sample: Bits per sample

        Returns:
            WAV file data as bytes
        """
        byte_rate = sample_rate * channel_count * bits_per_sample // 8
        block_align = channel_count * bits_per_sample // 8
        data_chunk_size = len(pcm16_audio_data)
        file_size = 36 + data_chunk_size

        # Build WAV header
        wav_data = io.BytesIO()

        # RIFF header
        wav_data.write(b'RIFF')
        wav_data.write(struct.pack('<I', file_size))
        wav_data.write(b'WAVE')

        # fmt chunk
        wav_data.write(b'fmt ')
        wav_data.write(struct.pack('<I', 16))  # Chunk size
        wav_data.write(struct.pack('<H', 1))   # Audio format (PCM)
        wav_data.write(struct.pack('<H', channel_count))
        wav_data.write(struct.pack('<I', sample_rate))
        wav_data.write(struct.pack('<I', byte_rate))
        wav_data.write(struct.pack('<H', block_align))
        wav_data.write(struct.pack('<H', bits_per_sample))

        # data chunk
        wav_data.write(b'data')
        wav_data.write(struct.pack('<I', data_chunk_size))
        wav_data.write(pcm16_audio_data)

        return wav_data.getvalue()

    @staticmethod
    def save_wav_file(
        pcm16_audio_data: bytes,
        file_path: str,
        sample_rate: int = 16000,
        channel_count: int = 1,
        bits_per_sample: int = 16
    ):
        """
        Save PCM16 audio data as a WAV file.

        Args:
            pcm16_audio_data: PCM16 audio data
            file_path: Path to save the WAV file
            sample_rate: Sample rate in Hz
            channel_count: Number of audio channels
            bits_per_sample: Bits per sample
        """
        try:
            with wave.open(file_path, 'wb') as wav_file:
                wav_file.setnchannels(channel_count)
                wav_file.setsampwidth(bits_per_sample // 8)
                wav_file.setframerate(sample_rate)
                wav_file.writeframes(pcm16_audio_data)
        except Exception as e:
            logger = setup_logger("BuddyWAVFileBuilder")
            logger.error(f"Error saving WAV file: {e}")
