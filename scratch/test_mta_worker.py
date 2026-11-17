import threading
import ctypes
import uiautomation as ua
import time

def test_mta_call():
    # Main thread initializes COM via uiautomation (MTA)
    root = ua.GetRootControl()
    children = root.GetChildren()
    print("Main thread got children:", len(children))
    first = children[0] if children else None
    if not first:
        print("No children")
        return

    result = {}
    def work():
        ret = ctypes.windll.ole32.CoInitializeEx(None, 0)
        try:
            t0 = time.time()
            # access first control
            name = first.Name
            result["name"] = name
            result["time"] = time.time() - t0
        finally:
            ctypes.windll.ole32.CoUninitialize()

    t = threading.Thread(target=work)
    t.start()
    t.join(2.0)
    print("Worker result:", result, "alive:", t.is_alive())

if __name__ == "__main__":
    test_mta_call()
