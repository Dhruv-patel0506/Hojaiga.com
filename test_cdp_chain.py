import sys, asyncio, subprocess, time

sys.path.insert(0, r"D:\new_automation\All codes")
from core_organs.organ_19_chrome_cdp_runtime import IPCFrame, Organ19OpCode, IPC_LENGTH_HEADER

async def test():
    # Check if organ_19 is already running
    try:
        reader, writer = await asyncio.open_connection("127.0.0.1", 47619)
        writer.close()
        await writer.wait_closed()
        print("organ_19 already running on 47619")
    except Exception:
        print("organ_19 not running, starting it...")
        proc = subprocess.Popen(
            [sys.executable, r"D:\new_automation\All codes\core_organs\organ_19_chrome_cdp_runtime.py"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
        await asyncio.sleep(2)
        print(f"organ_19 started PID={proc.pid}")

    # Send NAVIGATE directly (without launching browser first)
    print("\n--- Sending NAVIGATE without LAUNCH_BROWSER ---")
    reader, writer = await asyncio.open_connection("127.0.0.1", 47619)
    frame = IPCFrame(op_code=Organ19OpCode.NAVIGATE, payload={"url": "https://www.google.com"})
    writer.write(frame.encode())
    await writer.drain()
    length_bytes = await reader.readexactly(4)
    total_len = IPC_LENGTH_HEADER.unpack(length_bytes)[0]
    body = await reader.readexactly(total_len)
    response = IPCFrame.decode(body)
    writer.close()
    await writer.wait_closed()
    print(f"NAVIGATE response: ok={response.payload.get('ok')}, error={response.payload.get('error')}")

    # Now send LAUNCH_BROWSER
    print("\n--- Sending LAUNCH_BROWSER ---")
    reader, writer = await asyncio.open_connection("127.0.0.1", 47619)
    frame = IPCFrame(op_code=Organ19OpCode.LAUNCH_BROWSER, payload={"headless": False, "profile_id": "Profile 1"})
    writer.write(frame.encode())
    await writer.drain()
    length_bytes = await reader.readexactly(4)
    total_len = IPC_LENGTH_HEADER.unpack(length_bytes)[0]
    body = await reader.readexactly(total_len)
    response = IPCFrame.decode(body)
    writer.close()
    await writer.wait_closed()
    print(f"LAUNCH_BROWSER response: ok={response.payload.get('ok')}, error={response.payload.get('error')}")
    if response.payload.get("result"):
        r = response.payload["result"]
        print(f"  browser_id={r.get('browser_id')}, session_id={r.get('session_id')}")

    # Now send NAVIGATE again (should work)
    print("\n--- Sending NAVIGATE after LAUNCH ---")
    reader, writer = await asyncio.open_connection("127.0.0.1", 47619)
    frame = IPCFrame(op_code=Organ19OpCode.NAVIGATE, payload={"url": "https://www.google.com"})
    writer.write(frame.encode())
    await writer.drain()
    length_bytes = await reader.readexactly(4)
    total_len = IPC_LENGTH_HEADER.unpack(length_bytes)[0]
    body = await reader.readexactly(total_len)
    response = IPCFrame.decode(body)
    writer.close()
    await writer.wait_closed()
    print(f"NAVIGATE response: ok={response.payload.get('ok')}, error={response.payload.get('error')}")

asyncio.run(test())
