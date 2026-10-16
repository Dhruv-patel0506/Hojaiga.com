"""
harvest -- Checkpoint 3: the $0 data pipeline that feeds the federated RAG (rag/).

    free_master_harvester             1,000+ Windows apps (curated seed + the open Winget index) -> YouTube tutorial search (yt-dlp, no API key) -> timestamped transcripts (no video download) -> Excel sheets 1-2
    free_hotkeys_and_macros_harvester shortcut tables (robots.txt-respecting), tldr-pages CLI, built-in bpy / .scr / COM scripts, optional local-model fallback -> Excel sheets 3-4 + JSONL
    video_pipeline                    scene-change keyframes (OpenCV), action-moment clips (yt-dlp sections), CPU faster-whisper fallback, Set-of-Marks maps of frames (professor.sweeper.scan on a still)
    video_explain                     transcript + keyframes + SoM -> Sub-RAG 3 entries AND Unsloth-ready training pairs (no live window is ever touched)
    bridge                            workbook / JSON / JSONL -> the RAG tables (knowledge_chunks, procedures, fast_paths)

Everything is resumable, rate-limited, cached on disk under <storage root>/harvest/, and works offline against fixtures (the network is injected, never imported at call sites).
CLI:  python -m core_organs.harvest <apps|transcripts|hotkeys|ingest|video> [...]
"""
