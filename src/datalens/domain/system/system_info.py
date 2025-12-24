from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class GpuInfo:
    """
    Best-effort GPU information for diagnostics and feature gating.

    Notes:
    - This is not meant to be exhaustive or perfectly accurate across platforms.
    - Values may be `None` when not detectable without extra dependencies.
    """

    name: str
    vram_total_bytes: int | None = None


@dataclass(frozen=True, slots=True)
class SystemInfoSnapshot:
    """
    Snapshot of host system information (core-owned).

    Intended uses:
    - diagnostics (Help -> States…)
    - coarse feature gating (e.g. CPU arch, RAM availability)

    This is intentionally small and best-effort. It is not a hardware inventory.
    """

    os_name: str
    os_release: str
    os_version: str
    machine: str
    cpu_arch: str
    cpu_bits: int
    cpu_count_logical: int | None
    python_version: str
    ram_total_bytes: int | None
    gpus: tuple[GpuInfo, ...] = ()
    gpu_probe_completed: bool = False


__all__ = ["GpuInfo", "SystemInfoSnapshot"]
