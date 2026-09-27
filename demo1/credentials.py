"""可选的 Windows 凭据读取；其他平台直接配置 JEV_API_KEY。"""

from __future__ import annotations

import ctypes
import os
from ctypes import wintypes


def read_windows_credential(target: str) -> str:
    if os.name != "nt":
        raise RuntimeError("Windows 凭据模式仅适用于 Windows；其他平台请使用 JEV_AUTH=api-key。")

    class Credential(ctypes.Structure):
        _fields_ = [
            ("Flags", wintypes.DWORD), ("Type", wintypes.DWORD),
            ("TargetName", wintypes.LPWSTR), ("Comment", wintypes.LPWSTR),
            ("LastWritten", wintypes.FILETIME), ("CredentialBlobSize", wintypes.DWORD),
            ("CredentialBlob", ctypes.POINTER(ctypes.c_ubyte)), ("Persist", wintypes.DWORD),
            ("AttributeCount", wintypes.DWORD), ("Attributes", ctypes.c_void_p),
            ("TargetAlias", wintypes.LPWSTR), ("UserName", wintypes.LPWSTR),
        ]

    api = ctypes.WinDLL("advapi32", use_last_error=True)
    api.CredReadW.argtypes = [
        wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
        ctypes.POINTER(ctypes.POINTER(Credential)),
    ]
    api.CredReadW.restype = wintypes.BOOL
    api.CredFree.argtypes = [ctypes.c_void_p]
    api.CredFree.restype = None
    pointer = ctypes.POINTER(Credential)()
    if not api.CredReadW(target, 1, 0, ctypes.byref(pointer)):
        raise RuntimeError(
            f"无法读取指定的 JEV Windows 凭据（系统错误 {ctypes.get_last_error()}）；"
            "请检查凭据名称，或使用 JEV_AUTH=api-key。"
        )
    try:
        record = pointer.contents
        if not record.CredentialBlobSize or record.CredentialBlobSize % 2:
            raise RuntimeError("JEV Windows 凭据为空或编码无效。")
        return ctypes.wstring_at(
            ctypes.cast(record.CredentialBlob, wintypes.LPWSTR), record.CredentialBlobSize // 2
        )
    finally:
        api.CredFree(pointer)
