import sys, asyncio
sys.path.insert(0, r'D:\new_automation\All codes')
from core_organs.organ_19_chrome_cdp_runtime import IPCFrame, Organ19OpCode, IPC_LENGTH_HEADER

async def test():
    try:
        reader, writer = await asyncio.open_connection('127.0.0.1', 47619)
        frame = IPCFrame(op_code=Organ19OpCode.LAUNCH_BROWSER, payload={'headless': False, 'profile_id': 'Profile 1'})
        writer.write(frame.encode())
        await writer.drain()
        length_bytes = await reader.readexactly(4)
        total_len = IPC_LENGTH_HEADER.unpack(length_bytes)[0]
        body = await reader.readexactly(total_len)
        response = IPCFrame.decode(body)
        writer.close()
        await writer.wait_closed()
        ok = response.payload.get("ok")
        result = response.payload.get("result")
        print("ok:", ok)
        if isinstance(result, dict):
            print("browser_id:", result.get("browser_id", "N/A"))
            print("session_id:", result.get("session_id", "N/A"))
            print("ws_url:", result.get("ws_url", "N/A"))
        else:
            print("result:", result)
        print("error:", response.payload.get("error"))
    except ConnectionRefusedError:
        print("ERROR: organ_19 not listening on port 47619")
    except Exception as e:
        print(f"ERROR: {e}")

asyncio.run(test())
