"""Windows pinned SBOM reader: open the *file handle*, reject reparse points.

This is deliberately Windows-specific. Only ordinary local files inside
trusted parent directories are supported. No network shares or directory
swap adversary guarantees are claimed.
"""
from __future__ import annotations
import ctypes
from ctypes import wintypes
import msvcrt
import os
from pathlib import Path
import stat

FILE_READ_DATA = 0x0001
FILE_READ_ATTRIBUTES = 0x0080
FILE_SHARE_READ = 0x00000001
OPEN_EXISTING = 3
FILE_FLAG_OPEN_REPARSE_POINT = 0x00200000
FILE_ATTRIBUTE_REPARSE_POINT = 0x00000400
FILE_ATTRIBUTE_DIRECTORY = 0x00000010
INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value


class BY_HANDLE_FILE_INFORMATION(ctypes.Structure):
    _fields_ = [
        ('dwFileAttributes', wintypes.DWORD),
        ('ftCreationTime', wintypes.FILETIME),
        ('ftLastAccessTime', wintypes.FILETIME),
        ('ftLastWriteTime', wintypes.FILETIME),
        ('dwVolumeSerialNumber', wintypes.DWORD),
        ('nFileSizeHigh', wintypes.DWORD),
        ('nFileSizeLow', wintypes.DWORD),
        ('nNumberOfLinks', wintypes.DWORD),
        ('nFileIndexHigh', wintypes.DWORD),
        ('nFileIndexLow', wintypes.DWORD),
    ]


def _key(info):
    ft=info.ftLastWriteTime
    return (info.dwVolumeSerialNumber,
            info.nFileIndexHigh, info.nFileIndexLow,
            info.nFileSizeHigh, info.nFileSizeLow,
            ft.dwHighDateTime, ft.dwLowDateTime,
            info.dwFileAttributes, info.nNumberOfLinks)


def read_single_regular_file(path: Path, limit: int) -> bytes:
    if os.name != 'nt':
        raise OSError('Windows-only reader')
    if not path.is_absolute():
        path=Path(os.path.abspath(path))
    # OPEN_REPARSE_POINT is essential: a symlink *itself* is opened,
    # not followed to another file. An existing directory symlink in a
    # parent path is outside this reader's trusted-parent assumption.
    dll=ctypes.WinDLL('kernel32',use_last_error=True)
    CreateFileW=dll.CreateFileW
    CreateFileW.argtypes=[wintypes.LPCWSTR,wintypes.DWORD,wintypes.DWORD,
                          ctypes.c_void_p,wintypes.DWORD,wintypes.DWORD,wintypes.HANDLE]
    CreateFileW.restype=wintypes.HANDLE
    GetFileInformationByHandle=dll.GetFileInformationByHandle
    GetFileInformationByHandle.argtypes=[wintypes.HANDLE,ctypes.POINTER(BY_HANDLE_FILE_INFORMATION)]
    GetFileInformationByHandle.restype=wintypes.BOOL
    CloseHandle=dll.CloseHandle
    CloseHandle.argtypes=[wintypes.HANDLE]
    CloseHandle.restype=wintypes.BOOL
    handle=CreateFileW(str(path),FILE_READ_DATA|FILE_READ_ATTRIBUTES,
                       FILE_SHARE_READ,None,OPEN_EXISTING,
                       FILE_FLAG_OPEN_REPARSE_POINT,None)
    if handle in (None, INVALID_HANDLE_VALUE):
        raise ctypes.WinError(ctypes.get_last_error())
    owned=True
    try:
        first=BY_HANDLE_FILE_INFORMATION()
        if not GetFileInformationByHandle(handle,ctypes.byref(first)):
            raise ctypes.WinError(ctypes.get_last_error())
        if (first.dwFileAttributes & (FILE_ATTRIBUTE_REPARSE_POINT|FILE_ATTRIBUTE_DIRECTORY)
                or first.nNumberOfLinks != 1):
            raise ValueError('reparse point, directory, or hardlinked file rejected')
        file_size=(first.nFileSizeHigh << 32)|first.nFileSizeLow
        if file_size < 1 or file_size > limit:
            raise ValueError('file outside size limit')
        # CRT file descriptor takes handle ownership on success.
        fd=msvcrt.open_osfhandle(handle, os.O_RDONLY | os.O_BINARY)
        owned=False
        try:
            stat_before=os.fstat(fd)
            if not stat.S_ISREG(stat_before.st_mode):
                raise ValueError('only regular files allowed')
            parts=[]
            total=0
            while total<=limit:
                buf=os.read(fd,min(65536,limit+1-total))
                if not buf:
                    break
                parts.append(buf)
                total+=len(buf)
            last=BY_HANDLE_FILE_INFORMATION()
            if not GetFileInformationByHandle(msvcrt.get_osfhandle(fd),ctypes.byref(last)):
                raise ctypes.WinError(ctypes.get_last_error())
            stat_after=os.fstat(fd)
            if (_key(first)!=_key(last) or total!=file_size or total>limit or
                (stat_before.st_size,stat_before.st_mtime_ns,stat_before.st_ctime_ns)
                !=(stat_after.st_size,stat_after.st_mtime_ns,stat_after.st_ctime_ns)):
                raise ValueError('file changed during read')
            return b''.join(parts)
        finally:
            os.close(fd)
    finally:
        if owned:
            CloseHandle(handle)
