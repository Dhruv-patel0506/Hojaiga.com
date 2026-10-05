import sys
sys.path.insert(0, r"D:\new_automation\All codes")
sys.path.insert(0, r"D:\new_automation\All codes\core_organs")

print("=" * 60)
print("TEST 1: YouTube Video Transcript Extraction")
print("=" * 60)

try:
    from core_organs.organ_10_agents import VideoIntelligenceHelper

    test_url = "https://www.youtube.com/watch?v=aircAruvnKk"
    print(f"Testing URL: {test_url}")
    print("Fetching transcript...")

    transcript = VideoIntelligenceHelper.fetch_transcript(test_url)

    if transcript:
        print(f"SUCCESS: Got transcript with {len(transcript)} segments")
        print("First 3 segments:")
        for seg in transcript[:3]:
            print(f"  [{seg.get('start', 0):.1f}s] {seg.get('text', '')[:80]}")

        normalized = VideoIntelligenceHelper.normalize_idioms(transcript[0].get("text", ""))
        print(f"Normalization OK")

        chunks = VideoIntelligenceHelper.process_and_chunk(transcript, chunk_duration_sec=300.0)
        print(f"Chunking OK: {len(transcript)} segments -> {len(chunks)} chunks")
        for i, chunk in enumerate(chunks[:2]):
            print(f"  Chunk {i+1}: {chunk['start_time']:.0f}s - {chunk['end_time']:.0f}s ({len(chunk['segments'])} segments)")

        print("RESULT: PASS")
    else:
        print("FAIL: No transcript returned")
        print("RESULT: FAIL")

except Exception as e:
    print(f"ERROR: {e}")
    import traceback
    traceback.print_exc()
    print("RESULT: FAIL")
