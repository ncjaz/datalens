from __future__ import annotations

import os
import platform
import re
import subprocess
import sys
import threading
from dataclasses import replace

from datalens.core.logging import get_logger
from datalens.domain.system.system_info import GpuInfo, SystemInfoSnapshot

log = get_logger(__name__)


def _normalize_arch(machine: str) -> str:
    raw = (machine or "").strip().lower()
    if raw in {"x86_64", "amd64"}:
        return "x86_64"
    if raw in {"aarch64", "arm64"}:
        return "arm64"
    if raw.startswith("arm"):
        return "arm"
    if raw in {"i386", "i686", "x86"}:
        return "x86"
    return raw or "unknown"


def _total_ram_bytes() -> int | None:
    """
    Return total physical RAM bytes (best-effort, no third-party deps).
    """
    if sys.platform.startswith("win"):
        try:
            import ctypes

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

            stat = _MEMORYSTATUSEX()
            stat.dwLength = ctypes.sizeof(_MEMORYSTATUSEX)
            ok = ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat))
            if ok:
                return int(stat.ullTotalPhys)
        except Exception:
            log.debug("Failed to read total RAM on Windows (best-effort)", exc_info=True)
        return None

    # POSIX-like
    try:
        page_size = os.sysconf("SC_PAGE_SIZE")
        pages = os.sysconf("SC_PHYS_PAGES")
        if isinstance(page_size, int) and isinstance(pages, int):
            return int(page_size) * int(pages)
    except Exception:
        log.debug("Failed to read total RAM via sysconf (best-effort)", exc_info=True)
    return None


def collect_system_info_base() -> SystemInfoSnapshot:
    """
    Collect fast, dependency-free system info for gating/diagnostics.

    GPU/VRAM probing is intentionally excluded here; use `collect_gpu_info_async`.
    """
    os_name = platform.system() or "Unknown"
    os_release = platform.release() or ""
    os_version = platform.version() or ""
    machine = platform.machine() or ""
    cpu_arch = _normalize_arch(machine)
    cpu_bits = 64 if sys.maxsize > 2**32 else 32
    cpu_count = os.cpu_count()
    python_version = platform.python_version()
    ram = _total_ram_bytes()

    return SystemInfoSnapshot(
        os_name=os_name,
        os_release=os_release,
        os_version=os_version,
        machine=machine,
        cpu_arch=cpu_arch,
        cpu_bits=cpu_bits,
        cpu_count_logical=int(cpu_count) if isinstance(cpu_count, int) else None,
        python_version=python_version,
        ram_total_bytes=ram,
        gpus=(),
        gpu_probe_completed=False,
    )


def _parse_int(value: str) -> int | None:
    m = re.search(r"(\d+)", value or "")
    if not m:
        return None
    try:
        return int(m.group(1))
    except Exception:
        return None


def collect_gpu_info_best_effort(*, timeout_s: float = 1.5) -> tuple[GpuInfo, ...]:
    """
    Best-effort GPU/VRAM detection.

    This is intentionally conservative: it uses external tools when available but
    does not require any to exist. It should always return quickly or fail-safe.
    """
    # Nvidia (cross-platform where installed)
    try:
        proc = subprocess.run(
            ["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader,nounits"],
            capture_output=True,
            text=True,
            timeout=float(timeout_s),
            check=False,
        )
        if proc.returncode == 0 and proc.stdout.strip():
            out: list[GpuInfo] = []
            for line in proc.stdout.splitlines():
                parts = [p.strip() for p in line.split(",")]
                if not parts:
                    continue
                name = parts[0] or "NVIDIA GPU"
                vram_mb = _parse_int(parts[1]) if len(parts) > 1 else None
                out.append(GpuInfo(name=name, vram_total_bytes=(vram_mb * 1024 * 1024) if vram_mb else None))
            return tuple(out)
    except Exception:
        pass

    # Windows fallback: WMIC (deprecated but common). Best-effort only.
    if sys.platform.startswith("win"):
        try:
            proc = subprocess.run(
                ["wmic", "path", "win32_VideoController", "get", "Name,AdapterRAM", "/format:csv"],
                capture_output=True,
                text=True,
                timeout=float(timeout_s),
                check=False,
            )
            if proc.returncode == 0 and proc.stdout.strip():
                out: list[GpuInfo] = []
                for line in proc.stdout.splitlines():
                    if "," not in line or line.lower().startswith("node,"):
                        continue
                    parts = [p.strip() for p in line.split(",")]
                    if len(parts) < 3:
                        continue
                    name = parts[1]
                    vram = _parse_int(parts[2])
                    out.append(GpuInfo(name=name or "GPU", vram_total_bytes=vram))
                if out:
                    return tuple(out)
        except Exception:
            pass

    # macOS fallback: system_profiler
    if sys.platform == "darwin":
        try:
            proc = subprocess.run(
                ["system_profiler", "SPDisplaysDataType"],
                capture_output=True,
                text=True,
                timeout=float(timeout_s),
                check=False,
            )
            if proc.returncode == 0 and proc.stdout:
                # Extremely light parsing: capture "Chipset Model" and "VRAM".
                out: list[GpuInfo] = []
                current_name: str | None = None
                current_vram_bytes: int | None = None
                for line in proc.stdout.splitlines():
                    stripped = line.strip()
                    if stripped.startswith("Chipset Model:"):
                        current_name = stripped.split(":", 1)[1].strip()
                    if stripped.startswith("VRAM"):
                        # e.g. "VRAM (Dynamic, Max): 1536 MB"
                        v = _parse_int(stripped)
                        if v is not None:
                            current_vram_bytes = int(v) * 1024 * 1024
                    if current_name and current_vram_bytes is not None:
                        out.append(GpuInfo(name=current_name, vram_total_bytes=current_vram_bytes))
                        current_name = None
                        current_vram_bytes = None
                if out:
                    return tuple(out)
        except Exception:
            pass

    return ()


def collect_gpu_info_async(*, base: SystemInfoSnapshot, on_update) -> None:
    """
    Collect GPU info off the UI thread and call `on_update(updated_snapshot)`.
    """

    def _run() -> None:
        try:
            gpus = collect_gpu_info_best_effort()
            if gpus:
                on_update(replace(base, gpus=gpus))
        except Exception:
            log.debug("GPU probing failed (best-effort)", exc_info=True)

    threading.Thread(target=_run, name="SystemInfoGpuProbe", daemon=True).start()


__all__ = ["collect_system_info_base", "collect_gpu_info_best_effort", "collect_gpu_info_async"]
