from __future__ import annotations

import ctypes
import ctypes.wintypes
import socket
import struct
import subprocess
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class PingResult:
    ip: str
    ok: bool
    rtt_ms: Optional[int]
    raw: str


# ---------------------------------------------------------------------------
# Windows IcmpSendEcho API (no subprocess – much lower CPU overhead)
# ---------------------------------------------------------------------------

_iphlpapi: Optional[ctypes.WinDLL] = None


def _get_icmp_lib() -> Optional[ctypes.WinDLL]:
    """Load iphlpapi.dll and annotate IcmpSendEcho once, then cache."""
    global _iphlpapi
    if _iphlpapi is not None:
        return _iphlpapi
    try:
        lib = ctypes.windll.iphlpapi  # type: ignore[attr-defined]
        lib.IcmpCreateFile.restype = ctypes.wintypes.HANDLE
        lib.IcmpCreateFile.argtypes = []
        lib.IcmpCloseHandle.restype = ctypes.wintypes.BOOL
        lib.IcmpCloseHandle.argtypes = [ctypes.wintypes.HANDLE]
        lib.IcmpSendEcho.restype = ctypes.wintypes.DWORD
        lib.IcmpSendEcho.argtypes = [
            ctypes.wintypes.HANDLE,  # IcmpHandle
            ctypes.wintypes.DWORD,   # DestinationAddress (IPv4 as ULONG)
            ctypes.c_void_p,         # RequestData
            ctypes.wintypes.WORD,    # RequestSize
            ctypes.c_void_p,         # RequestOptions (NULL)
            ctypes.c_void_p,         # ReplyBuffer
            ctypes.wintypes.DWORD,   # ReplySize
            ctypes.wintypes.DWORD,   # Timeout (ms)
        ]
        _iphlpapi = lib
        return lib
    except Exception:
        return None


def _ping_icmp(ip: str, timeout_ms: int) -> PingResult:
    """
    Ping using Windows IcmpSendEcho API.
    No subprocess – direct OS call, far lower CPU cost.

    ICMP_ECHO_REPLY layout (before any pointer field):
      offset 0 : Address       (DWORD, 4 bytes)
      offset 4 : Status        (ULONG, 4 bytes)  – 0 = IP_SUCCESS
      offset 8 : RoundTripTime (ULONG, 4 bytes)  – RTT in ms
    These offsets are stable across 32/64-bit because they precede all pointers.
    """
    lib = _get_icmp_lib()
    if lib is None:
        return _ping_subprocess(ip, timeout_ms)

    # Resolve hostname to IPv4 dotted-quad if needed
    try:
        ipv4 = socket.gethostbyname(ip)
        dest = struct.unpack("I", socket.inet_aton(ipv4))[0]
    except OSError:
        return PingResult(ip=ip, ok=False, rtt_ms=None, raw="Cannot resolve host")

    handle = lib.IcmpCreateFile()
    # INVALID_HANDLE_VALUE = -1 (may appear as large unsigned int on 64-bit)
    if handle is None or handle in (-1, 0, 0xFFFFFFFF, 0xFFFFFFFFFFFFFFFF):
        return _ping_subprocess(ip, timeout_ms)

    try:
        req_data = (ctypes.c_uint8 * 32)()
        # Reply buffer: ICMP_ECHO_REPLY (up to 40 bytes on 64-bit)
        #               + request size (32) + 8 bytes ICMP header padding
        reply_size = 128
        reply_buf = (ctypes.c_uint8 * reply_size)()

        ret = lib.IcmpSendEcho(
            handle,
            dest,
            req_data,
            ctypes.wintypes.WORD(32),
            None,
            reply_buf,
            ctypes.wintypes.DWORD(reply_size),
            ctypes.wintypes.DWORD(timeout_ms),
        )

        if ret > 0:
            status = struct.unpack_from("<I", bytes(reply_buf), 4)[0]
            rtt = struct.unpack_from("<I", bytes(reply_buf), 8)[0]
            ok = status == 0  # IP_SUCCESS
            return PingResult(
                ip=ip,
                ok=ok,
                rtt_ms=rtt if ok else None,
                raw=f"rtt={rtt}ms" if ok else f"icmp_status={status}",
            )
        return PingResult(ip=ip, ok=False, rtt_ms=None, raw="No reply")
    finally:
        lib.IcmpCloseHandle(handle)


# ---------------------------------------------------------------------------
# Subprocess fallback (original implementation, kept as safety net)
# ---------------------------------------------------------------------------

def _ping_subprocess(ip: str, timeout_ms: int) -> PingResult:
    """Original subprocess-based ping. Used only if IcmpSendEcho fails."""
    cmd = ["ping", "-n", "1", "-w", str(timeout_ms), ip]
    p = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    output = (p.stdout or "") + "\n" + (p.stderr or "")
    lower = output.lower()

    fail_markers = [
        "destination net unreachable",
        "destination host unreachable",
        "request timed out",
        "general failure",
        "could not find host",
        "transmit failed",
        "ttl expired",
    ]
    ok = (p.returncode == 0) and not any(m in lower for m in fail_markers)

    rtt: Optional[int] = None
    if ok:
        if "time=" in lower:
            try:
                part = lower.split("time=")[1]
                digits = ""
                for ch in part:
                    if ch.isdigit():
                        digits += ch
                    else:
                        break
                if digits:
                    rtt = int(digits)
            except Exception:
                rtt = None
        elif "time<" in lower:
            rtt = 1

    return PingResult(ip=ip, ok=ok, rtt_ms=rtt, raw=output.strip())


# ---------------------------------------------------------------------------
# Public API – always prefer the fast ICMP path
# ---------------------------------------------------------------------------

def ping_once_windows(ip: str, timeout_ms: int = 1000) -> PingResult:
    """
    Ping an IPv4 host.
    Uses Windows IcmpSendEcho (no subprocess) for low CPU overhead.
    Falls back to subprocess ping.exe if the API is unavailable.
    """
    return _ping_icmp(ip, timeout_ms)
