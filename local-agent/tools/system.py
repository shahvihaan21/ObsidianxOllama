"""System information: CPU, memory, disk, time.

Uses only the standard library plus, on Windows, ``ctypes`` for the global
memory status. This is the cheapest way to know real RAM pressure, which matters
a great deal on an 8 GB machine.
"""

from __future__ import annotations

import ctypes
import datetime as dt
import logging
import os
import platform
import shutil
import sys
from typing import Any

from tools.registry import Level, Tool, ToolError

log = logging.getLogger(__name__)


class _MEMORYSTATUSEX(ctypes.Structure):
    _fields_ = [
        ("dwLength", ctypes.c_ulong),
        ("dwMemoryLoad", ctypes.c_ulong),
        ("ullTotalPhys", ctypes.c_ulonglong),
        ("ullAvailPhys", ctypes.c_ulonglong),
        ("ullTotalPageFile", ctypes.c_ulonglong),
        ("ullAvailPageFile", ctypes.c_ulonglong),
        ("ullTotalVirtual", ctypes.c_ulonglong),
        ("ullAvailVirtual", ctypes.c_ulonglong),
        ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
    ]


def memory_info() -> dict[str, Any]:
    """Return physical memory totals in MiB."""
    if os.name != "nt":
        return {"result": "Memory details are only implemented for Windows."}
    stat = _MEMORYSTATUSEX()
    stat.dwLength = ctypes.sizeof(_MEMORYSTATUSEX)
    if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat)):
        raise ToolError("Could not read memory status.", "not_supported")
    total = stat.ullTotalPhys / (1024 ** 2)
    avail = stat.ullAvailPhys / (1024 ** 2)
    used = total - avail
    return {
        "result": (
            f"RAM: {used:.0f} MiB used of {total:.0f} MiB "
            f"({stat.dwMemoryLoad}% load), {avail:.0f} MiB free."
        ),
        "total_mib": round(total),
        "available_mib": round(avail),
        "used_mib": round(used),
        "percent_used": int(stat.dwMemoryLoad),
    }


def read_system_info() -> dict[str, Any]:
    """Summarise the machine: OS, CPU, RAM, disks, Python."""
    mem = memory_info()
    info: dict[str, Any] = {
        "os": f"{platform.system()} {platform.release()} ({platform.version()})",
        "machine": platform.machine(),
        "processor": platform.processor(),
        "cpu_count": os.cpu_count(),
        "python": sys.version.split()[0],
        "time": dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "ram": mem.get("result", "unknown"),
    }

    drives: list[str] = []
    for letter in "CDEFGH":
        root = f"{letter}:\\"
        if os.path.exists(root):
            try:
                usage = shutil.disk_usage(root)
                drives.append(
                    f"{letter}: {usage.free / 1024**3:.1f} GB free "
                    f"of {usage.total / 1024**3:.1f} GB"
                )
            except OSError:
                continue
    info["disks"] = "; ".join(drives) if drives else "none detected"

    text = "\n".join(
        [
            f"OS:        {info['os']}",
            f"CPU:       {info['processor']} ({info['cpu_count']} logical cores)",
            f"RAM:       {info['ram']}",
            f"Disks:     {info['disks']}",
            f"Python:    {info['python']}",
            f"Local time:{info['time']}",
        ]
    )
    return {"result": text, **info}


def get_time() -> dict[str, str]:
    """Return the current local date and time."""
    now = dt.datetime.now()
    return {
        "result": now.strftime("%A, %d %B %Y at %H:%M"),
        "iso": now.isoformat(timespec="seconds"),
        "date": now.strftime("%Y-%m-%d"),
        "time": now.strftime("%H:%M"),
    }


def list_folders(path: str = "~") -> dict[str, Any]:
    """List the immediate children of a folder, plus the common user folders."""
    target = os.path.expanduser(path or "~")
    if not os.path.isdir(target):
        raise ToolError(f"{target!r} is not a folder.", "not_a_directory")

    entries = []
    try:
        with os.scandir(target) as it:
            for entry in it:
                if entry.name.startswith("."):
                    continue
                entries.append(entry.name + ("/" if entry.is_dir() else ""))
    except PermissionError as exc:
        raise ToolError(f"Cannot read {target!r}: permission denied.", "permission_denied") from exc

    common = {
        name: os.path.join(os.path.expanduser("~"), name)
        for name in ("Desktop", "Documents", "Downloads", "Pictures", "Videos", "Music")
        if os.path.isdir(os.path.join(os.path.expanduser("~"), name))
    }
    return {
        "result": f"{target} contains: " + (", ".join(sorted(entries)) or "(empty)"),
        "path": target,
        "entries": sorted(entries),
        "user_folders": common,
    }


TOOLS = [
    Tool(
        name="read_system_info",
        description=(
            "Report the operating system, CPU, memory, disk space, and current "
            "date and time of this computer."
        ),
        parameters={"type": "object", "properties": {}},
        handler=read_system_info,
        level=Level.SAFE,
        timeout=15.0,
        category="system",
    ),
    Tool(
        name="get_time",
        description="Get the current local date and time.",
        parameters={"type": "object", "properties": {}},
        handler=get_time,
        level=Level.SAFE,
        timeout=10.0,
        category="system",
    ),
    Tool(
        name="memory_info",
        description=(
            "Report how much RAM is in use and how much is free. Useful before "
            "starting anything memory-heavy on this 8 GB machine."
        ),
        parameters={"type": "object", "properties": {}},
        handler=memory_info,
        level=Level.SAFE,
        timeout=10.0,
        category="system",
    ),
    Tool(
        name="list_folders",
        description=(
            "List the contents of a folder and report the user's standard "
            "folders (Desktop, Documents, Downloads...)."
        ),
        parameters={
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Folder to list; defaults to the home folder",
                    "default": "~",
                },
            },
        },
        handler=list_folders,
        level=Level.SAFE,
        timeout=20.0,
        category="system",
    ),
]