import sys, asyncio, subprocess, time, json

sys.path.insert(0, r"D:\new_automation\All codes")
from core_organs.organ_19_chrome_cdp_runtime import IPCFrame, Organ19OpCode, IPC_LENGTH_HEADER

async def send_op(op_code, payload, label=""):
    try:
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
        ok = response.payload.get("ok")
        err = response.payload.get("error")
        print(f"  {label}: ok={ok}" + (f" error={err}" if err else ""))
        if ok and response.payload.get("result"):
            r = response.payload["result"]
            if isinstance(r, dict):
                print(f"    keys={list(r.keys())}")
                if "nodes" in r:
                    print(f"    nodes_count={len(r['nodes'])}")
        return response
    except Exception as e:
        print(f"  {label}: EXCEPTION {e}")
        return None

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
    print(f"[1] organ_19 ready")

    # 2. Launch Chrome
    print("[2] Launch Chrome...")
    resp = await send_op(Organ19OpCode.LAUNCH_BROWSER, {"headless": False, "profile_id": "Profile 1"}, "LAUNCH")
    if not resp or not resp.payload.get("ok"):
        print("FAIL: Chrome didn't launch"); proc.terminate(); return
    sid = resp.payload["result"]["session_id"]
    print(f"    session_id={sid}")

    # 3. Navigate to Google
    print("[3] Navigate to Google...")
    resp = await send_op(Organ19OpCode.NAVIGATE, {"session_id": sid, "url": "https://www.google.com"}, "NAVIGATE")
    if not resp or not resp.payload.get("ok"):
        print("FAIL: Navigate didn't work"); proc.terminate(); return
    await asyncio.sleep(2)

    # 4. Try EXTRACT_DATA (GET_DOM_TREE)
    print("[4] EXTRACT_DATA (GET_DOM_TREE)...")
    resp = await send_op(Organ19OpCode.GET_DOM_TREE, {"session_id": sid, "pierce_shadow_dom": True}, "GET_DOM_TREE")
    
    # 5. Try GET_PAGE_STATE
    print("[5] GET_PAGE_STATE...")
    resp = await send_op(Organ19OpCode.GET_PAGE_STATE, {"session_id": sid}, "GET_PAGE_STATE")

    # 6. Try SCREENSHOT
    print("[6] SCREENSHOT...")
    resp = await send_op(Organ19OpCode.SCREENSHOT, {"session_id": sid}, "SCREENSHOT")

    proc.terminate()

asyncio.run(main())
