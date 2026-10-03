"""
HOJAIGA AUTOMATION ARCHITECTURE DOC

============================================================
1. MASTER ARCHITECTURE CONTEXT
============================================================
This component is part of the Hojaiga Automation Architecture.
Component Type: Core File
Name: test_voice_pipeline.py

============================================================
2. ORGAN/COMPONENT DIAGRAM
============================================================
```mermaid
graph TD
    classDef default fill:#1e1e1e,stroke:#333,stroke-width:2px,color:#d4d4d4;
    classDef component fill:#2d2d2d,stroke:#569cd6,stroke-width:2px,color:#d4d4d4;
    
    UPSTREAM[UPSTREAM INPUT]
    
    UPSTREAM -- event/socket --> COMPONENT
    
    subgraph COMPONENT [test_voice_pipeline.py]
        direction TB
        IN[Inputs] --> PROC[Processing]
        PROC --> OUT[Outputs]
    end
    
    COMPONENT -- event/socket --> DOWNSTREAM_A[CONSUMER A]
    COMPONENT -- event/socket --> DOWNSTREAM_B[CONSUMER B]
    
    class COMPONENT component;
```

Inputs: Discovered from runtime
Outputs: Discovered from runtime
Dependencies: user_io.local_stt_engine, speech_recognition, time, sys, logging...

============================================================
3. N8N-STYLE VISUAL WORKFLOW (MODEL)
============================================================
```mermaid
graph LR
    input([Input Node]) --> process([Code Node: test_voice_pipeline.py]) --> output([Output Node])
```
"""

"""
test_voice_pipeline.py
────────────────────────────────────────────────────────────────────────────
Five standalone diagnostic tests for the local voice capture pipeline.
Run this BEFORE wiring LocalSTTEngine into HojaigaVoiceInterface, to
confirm the microphone, capture levels, local transcription, latency,
and offline TTS all work without any external API.

Usage:
    python test_voice_pipeline.py            # runs all 5 tests
    python test_voice_pipeline.py --skip-mic  # skip tests needing a live mic
"""

import argparse
import logging
import sys
import time

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("voice_pipeline_tests")

RESULTS = []


def record(name: str, passed: bool, detail: str = ""):
    RESULTS.append((name, passed, detail))
    status = "PASS" if passed else "FAIL"
    logger.info("[%s] %s %s", status, name, f"- {detail}" if detail else "")


# ─────────────────────────────────────────────────────────────────────────
# Test 1 — Microphone device availability
# ─────────────────────────────────────────────────────────────────────────
def test_1_microphone_available():
    try:
        import speech_recognition as sr
        mic_list = sr.Microphone.list_microphone_names()
        if not mic_list:
            record("1. Microphone availability", False, "No input devices found")
            return
        record(
            "1. Microphone availability", True,
            f"{len(mic_list)} device(s) found, default index 0 = '{mic_list[0]}'",
        )
    except Exception as exc:
        record("1. Microphone availability", False, str(exc))


# ─────────────────────────────────────────────────────────────────────────
# Test 2 — Ambient noise / energy threshold calibration
# ─────────────────────────────────────────────────────────────────────────
def test_2_ambient_noise_calibration(skip_mic: bool):
    if skip_mic:
        record("2. Ambient noise calibration", True, "skipped (--skip-mic)")
        return
    try:
        import speech_recognition as sr
        recognizer = sr.Recognizer()
        with sr.Microphone() as source:
            recognizer.adjust_for_ambient_noise(source, duration=1.0)
        threshold = recognizer.energy_threshold
        sane = 50 <= threshold <= 4000
        record(
            "2. Ambient noise calibration", sane,
            f"energy_threshold={threshold:.1f} ({'within' if sane else 'outside'} sane range 50-4000)",
        )
    except Exception as exc:
        record("2. Ambient noise calibration", False, str(exc))


# ─────────────────────────────────────────────────────────────────────────
# Test 3 — Local STT round-trip (record a phrase, transcribe locally)
# ─────────────────────────────────────────────────────────────────────────
def test_3_local_stt_roundtrip(skip_mic: bool):
    try:
        from user_io.local_stt_engine import LocalSTTEngine
    except ImportError as exc:
        record("3. Local STT round-trip", False, f"local_stt_engine import failed: {exc}")
        return

    try:
        engine = LocalSTTEngine(model_size="small")
        engine.warm_up()

        if skip_mic:
            record("3. Local STT round-trip", True, "model loaded + warmed up (skipped live capture)")
            return

        import speech_recognition as sr
        recognizer = sr.Recognizer()
        with sr.Microphone() as source:
            recognizer.adjust_for_ambient_noise(source, duration=1.0)
            print("Speak a short phrase now (e.g. 'hojaiga is online')...")
            audio = recognizer.listen(source, timeout=5, phrase_time_limit=5)

        text = engine.transcribe(audio)
        passed = len(text.strip()) > 0
        record("3. Local STT round-trip", passed, f"heard: '{text}'" if passed else "empty transcript")
    except Exception as exc:
        record("3. Local STT round-trip", False, str(exc))


# ─────────────────────────────────────────────────────────────────────────
# Test 4 — Transcription latency benchmark (must stay usable on CPU)
# ─────────────────────────────────────────────────────────────────────────
def test_4_latency_benchmark():
    try:
        from user_io.local_stt_engine import LocalSTTEngine, _generate_silence_wav

        engine = LocalSTTEngine(model_size="small")
        engine.warm_up()

        start = time.time()
        engine.transcribe_wav_bytes(_generate_silence_wav(seconds=3.0))
        elapsed = time.time() - start

        passed = elapsed < 8.0  # generous ceiling for a 3s clip on i7 CPU
        record(
            "4. Latency benchmark", passed,
            f"{elapsed:.2f}s to process a 3s clip (threshold 8.0s)",
        )
    except Exception as exc:
        record("4. Latency benchmark", False, str(exc))


# ─────────────────────────────────────────────────────────────────────────
# Test 5 — Offline TTS output (no API key, no network)
# ─────────────────────────────────────────────────────────────────────────
def test_5_offline_tts():
    try:
        from user_io.local_stt_engine import LocalTTSEngine

        tts = LocalTTSEngine()
        voices = tts.list_voices()
        if not voices:
            record("5. Offline TTS", False, "no TTS voices registered on this system")
            return

        tts.speak("Hojaiga local voice pipeline test successful.")
        record("5. Offline TTS", True, f"{len(voices)} voice(s) available, playback attempted")
    except Exception as exc:
        record("5. Offline TTS", False, str(exc))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-mic", action="store_true", help="skip tests requiring a live microphone")
    args = parser.parse_args()

    test_1_microphone_available()
    test_2_ambient_noise_calibration(args.skip_mic)
    test_3_local_stt_roundtrip(args.skip_mic)
    test_4_latency_benchmark()
    test_5_offline_tts()

    print("\n──────── SUMMARY ────────")
    passed_count = sum(1 for _, p, _ in RESULTS if p)
    for name, passed, detail in RESULTS:
        print(f"{'✓' if passed else '✗'} {name}")
    print(f"\n{passed_count}/{len(RESULTS)} tests passed")

    sys.exit(0 if passed_count == len(RESULTS) else 1)


if __name__ == "__main__":
    main()
