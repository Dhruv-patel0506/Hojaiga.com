import sys, asyncio, time, subprocess

start = time.time()
print(f"[{time.time()-start:.1f}s] Spawning organ_19...")

proc = subprocess.Popen(
    [sys.executable, r"D:\new_automation\All codes\core_organs\organ_19_chrome_cdp_runtime.py"],
    stdout=subprocess.PIPE, stderr=subprocess.PIPE
)

print(f"[{time.time()-start:.1f}s] organ_19 PID={proc.pid}, waiting for port 47619...")

async def wait_for_port(port, timeout=15):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            reader, writer = await asyncio.open_connection("127.0.0.1", port)
            writer.close()
            await writer.wait_closed()
            return True
        except Exception:
            await asyncio.sleep(0.3)
    return False

ready = asyncio.run(wait_for_port(47619, timeout=15))
elapsed = time.time() - start
print(f"[{elapsed:.1f}s] Port 47619 ready: {ready}")

if ready:
    from core_organs.organ_19_chrome_cdp_runtime import IPCFrame, Organ19OpCode, IPC_LENGTH_HEADER
    async def test_launch():
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
        print(f"[{time.time()-start:.1f}s] LAUNCH_BROWSER response: ok={response.payload.get('ok')}, error={response.payload.get('error')}")
        if response.payload.get("result"):
            r = response.payload["result"]
            print(f"  browser_id={r.get('browser_id')}, session_id={r.get('session_id')}")
        return response.payload.get("ok", False)
    
    launched = asyncio.run(test_launch())
    if launched:
        print(f"[{time.time()-start:.1f}s] Chrome launched successfully!")
        # Check if chrome.exe is running
        import subprocess as sp
        result = sp.run(["tasklist", "/FI", "IMAGENAME eq chrome.exe"], capture_output=True, text=True)
        chrome_count = result.stdout.count("chrome.exe")
        print(f"[{time.time()-start:.1f}s] Chrome processes running: {chrome_count}")
    else:
        print(f"[{time.time()-start:.1f}s] Chrome launch FAILED")
else:
    print(f"organ_19 did not start within 15s")

proc.terminate()
