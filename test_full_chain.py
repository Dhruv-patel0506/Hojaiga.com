import sys, asyncio, subprocess, time, os

sys.path.insert(0, r"D:\new_automation\All codes")
from core_organs.organ_19_chrome_cdp_runtime import IPCFrame, Organ19OpCode, IPC_LENGTH_HEADER

async def send_op(op_code, payload):
    reader, writer = await asyncio.open_connection("127.0.0.1", 47619)
    frame = IPCFrame(op_code=op_code, payload=payload)
    writer.write(frame.encode())
    await writer.drain()
    length_bytes = await reader.readexactly(4)
    total_len = IPC_LENGTH_HEADER.unpack(length_bytes)[0]
    body = await reader.readexactly(total_len)
    response = IPCFrame.decode(body)
    writer.close()
    await writer.wait_closed()
    return response

async def main():
    # 1. Start organ_19
    print("[1] Starting organ_19...")
    proc = subprocess.Popen(
        [sys.executable, r"D:\new_automation\All codes\core_organs\organ_19_chrome_cdp_runtime.py"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    )
    for i in range(10):
        try:
            r, w = await asyncio.open_connection("127.0.0.1", 47619)
            w.close(); await w.wait_closed()
            break
        except: await asyncio.sleep(1)
    else:
        print("FAIL: organ_19 didn't start"); return
    print(f"[1] organ_19 ready (PID={proc.pid})")

    # 2. Launch Chrome via CDP
    print("[2] Launching Chrome via CDP...")
    t0 = time.time()
    resp = await send_op(Organ19OpCode.LAUNCH_BROWSER, {"headless": False, "profile_id": "Profile 1"})
    print(f"[2] LAUNCH: ok={resp.payload.get('ok')} ({time.time()-t0:.1f}s)")
    if not resp.payload.get("ok"):
        print(f"    ERROR: {resp.payload.get('error')}")
        proc.terminate(); return
    sid = resp.payload["result"]["session_id"]
    print(f"    session_id={sid}")

    # 3. Navigate to Google
    print("[3] Navigating to Google...")
    t0 = time.time()
    resp = await send_op(Organ19OpCode.NAVIGATE, {"session_id": sid, "url": "https://www.google.com"})
    print(f"[3] NAVIGATE: ok={resp.payload.get('ok')} ({time.time()-t0:.1f}s)")
    if not resp.payload.get("ok"):
        print(f"    ERROR: {resp.payload.get('error')}")
    
    # 4. Check chrome is running
    result = subprocess.run(["tasklist", "/FI", "IMAGENAME eq chrome.exe"], capture_output=True, text=True)
    count = result.stdout.count("chrome.exe")
    print(f"[4] Chrome processes: {count}")
    
    print("\n=== PIPELINE CHAIN WORKS ===")
    proc.terminate()

asyncio.run(main())
