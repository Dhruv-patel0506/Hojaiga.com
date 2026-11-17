import threading
import ctypes
import uiautomation as ua

def test():
    ret = ctypes.windll.ole32.CoInitializeEx(None, 0) # COINIT_MULTITHREADED
    print("CoInitializeEx MTA return:", hex(ret & 0xffffffff))
    ctypes.windll.ole32.CoUninitialize()

t = threading.Thread(target=test)
t.start()
t.join()
