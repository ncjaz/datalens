"""
IPC + worker-process helpers (V2).

This package provides a small, cross-platform wrapper around Qt local sockets
(`QLocalServer` / `QLocalSocket`) and worker process management (`QProcess`).

Design goals:

- keep the UI thread non-blocking (callbacks/signals; no `.result()` waits)
- make plugin worker processes easy to start and communicate with
- provide an optional shared-memory fast path for high-rate payloads (planned)
"""

__all__: list[str] = []

