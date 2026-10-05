import ctypes

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

hdesk = user32.OpenInputDesktop(0, False, 0x01FF)
err = kernel32.GetLastError()
print(f"OpenInputDesktop handle: {hdesk}, err: {err}")

if hdesk:
    name_buf = ctypes.create_unicode_buffer(256)
    needed = ctypes.c_ulong()
    res = user32.GetUserObjectInformationW(hdesk, 2, name_buf, 256*2, ctypes.byref(needed))
    print(f"Active Input Desktop Name: '{name_buf.value}' (res={res})")

# Also check GetProcessWindowStation
hwinsta = user32.GetProcessWindowStation()
name_buf = ctypes.create_unicode_buffer(256)
user32.GetUserObjectInformationW(hwinsta, 2, name_buf, 256*2, ctypes.byref(needed))
print(f"Process Window Station: '{name_buf.value}'")

# Check session ID
sess_id = ctypes.c_ulong()
kernel32.ProcessIdToSessionId(kernel32.GetCurrentProcessId(), ctypes.byref(sess_id))
print(f"Session ID: {sess_id.value}")
