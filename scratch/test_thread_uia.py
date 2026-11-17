import threading
import ctypes
import uiautomation as ua
import time

calc = ua.WindowControl(searchDepth=1, ClassName='ApplicationFrameWindow')
if not calc.Exists(0, 0):
    print("Calc window not found")
else:
    print("Found calc:", calc.Name)
    # Find Open Navigation
    btn = calc.ButtonControl(searchDepth=5, AutomationId='TogglePaneButton')
    if not btn.Exists(0, 0):
        print("TogglePaneButton not found")
    else:
        print("Found TogglePaneButton")
        # Test 1: with CoInitialize(None) (STA)
        def run_sta():
            ctypes.windll.ole32.CoInitialize(None)
            t0 = time.time()
            try:
                p = btn.GetPattern(ua.PatternId.InvokePattern)
                print(f"STA pattern get took {time.time()-t0:.3f}s: {p}")
            except Exception as e:
                print("STA error:", e)
            finally:
                ctypes.windll.ole32.CoUninitialize()

        t1 = threading.Thread(target=run_sta)
        t1.start()
        t1.join(3.0)
        print("STA thread is_alive:", t1.is_alive())

        # Test 2: with CoInitializeEx(None, 0) (MTA)
        def run_mta():
            ctypes.windll.ole32.CoInitializeEx(None, 0)
            t0 = time.time()
            try:
                p = btn.GetPattern(ua.PatternId.InvokePattern)
                print(f"MTA pattern get took {time.time()-t0:.3f}s: {p}")
            except Exception as e:
                print("MTA error:", e)
            finally:
                ctypes.windll.ole32.CoUninitialize()

        t2 = threading.Thread(target=run_mta)
        t2.start()
        t2.join(3.0)
        print("MTA thread is_alive:", t2.is_alive())
