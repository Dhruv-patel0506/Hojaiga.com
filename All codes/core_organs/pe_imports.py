"""
pe_imports.py -- the function NAMES a PE image imports (import + delay-import name tables), read from the bytes.

preload_sources needs this to tell a plugin's own request-name table ('GetSceneList', 'StartRecord') from the operating-system calls the same
binary makes ('CreateFile', 'GetProcAddress'): both are CamelCase Verb+Words strings. Anything the image IMPORTS is not its own vocabulary.
"""

from __future__ import annotations

import struct
from typing import Set


def imported_function_names(data: bytes) -> Set[str]:
    out: Set[str] = set()
    try:
        if data[:2] != b"MZ":
            return out
        pe = struct.unpack_from("<I", data, 0x3C)[0]
        if data[pe:pe + 4] != b"PE\x00\x00":
            return out
        nsec = struct.unpack_from("<H", data, pe + 6)[0]
        opt_size = struct.unpack_from("<H", data, pe + 20)[0]
        opt = pe + 24
        is64 = struct.unpack_from("<H", data, opt)[0] == 0x20B
        dd = opt + (112 if is64 else 96)
        secs = []
        sec0 = opt + opt_size
        for i in range(nsec):
            o = sec0 + 40 * i
            vsize, va, rsize, raw = struct.unpack_from("<IIII", data, o + 8)
            secs.append((va, max(vsize, rsize), raw))

        def off(rva: int) -> int:
            for va, sz, raw in secs:
                if va <= rva < va + sz:
                    return raw + (rva - va)
            return -1

        step = 8 if is64 else 4
        ord_flag = 1 << (63 if is64 else 31)
        for idx, desc_size in ((1, 20), (13, 32)):
            rva, _size = struct.unpack_from("<II", data, dd + 8 * idx)
            o = off(rva) if rva else -1
            n = 0
            while o >= 0 and n < 500:
                if idx == 1:
                    oft, _t, _f, name_rva, ft = struct.unpack_from("<IIIII", data, o)
                    thunk = oft or ft
                else:
                    _attrs, name_rva, _m, _iat, thunk = struct.unpack_from("<IIIII", data, o)
                if not name_rva:
                    break
                to = off(thunk)
                k = 0
                while to >= 0 and k < 20000:
                    val = int.from_bytes(data[to + k * step:to + (k + 1) * step], "little")
                    if not val:
                        break
                    if not val & ord_flag:                                   # imported by name (not by ordinal)
                        no = off(val & 0x7FFFFFFF)
                        if no >= 0:
                            end = data.find(b"\x00", no + 2)
                            out.add(data[no + 2:end].decode("ascii", "ignore"))
                    k += 1
                o += desc_size
                n += 1
    except Exception:  # noqa: BLE001
        pass
    return out
