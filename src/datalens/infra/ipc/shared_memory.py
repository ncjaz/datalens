from __future__ import annotations

import struct
import uuid
from dataclasses import dataclass
from multiprocessing.shared_memory import SharedMemory
from typing import Final

MAGIC: Final[bytes] = b"DLIPC1\0\0"
VERSION: Final[int] = 1

_GLOBAL_STRUCT: Final[struct.Struct] = struct.Struct("<8sIIIQII")
_SLOT_STRUCT: Final[struct.Struct] = struct.Struct("<QII")


class SharedMemoryProtocolError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class SharedMemoryPointer:
    name: str
    slot: int
    seq: int
    length: int

    def to_dict(self) -> dict[str, int | str]:
        return {"name": self.name, "slot": self.slot, "seq": self.seq, "length": self.length}

    @staticmethod
    def from_dict(data: dict[str, object]) -> "SharedMemoryPointer":
        return SharedMemoryPointer(
            name=str(data["name"]),
            slot=int(data["slot"]),
            seq=int(data["seq"]),
            length=int(data["length"]),
        )


class SharedMemoryLatestBuffer:
    """
    A small shared-memory helper for “latest payload” semantics.

    This is intended as a fast path for high-rate binary payloads (frames):

    - the writer publishes bytes into shared memory
    - the writer sends a small IPC notification containing a `SharedMemoryPointer`
    - the reader uses the pointer to retrieve the bytes from shared memory

    Notes:
    - This does not guarantee delivery of every payload; it is “latest wins”.
    - Use a `slot_count` large enough to tolerate UI lag without reusing slots
      too quickly.
    """

    def __init__(self, shm: SharedMemory, *, slot_count: int, slot_bytes: int, creator: bool) -> None:
        self._shm = shm
        self._slot_count = slot_count
        self._slot_bytes = slot_bytes
        self._creator = creator

        self._global_size = _GLOBAL_STRUCT.size
        self._slot_header_size = _SLOT_STRUCT.size
        self._slot_size = self._slot_header_size + self._slot_bytes

    @property
    def name(self) -> str:
        return self._shm.name

    @property
    def slot_count(self) -> int:
        return self._slot_count

    @property
    def slot_bytes(self) -> int:
        return self._slot_bytes

    @staticmethod
    def _calc_size(slot_count: int, slot_bytes: int) -> int:
        return _GLOBAL_STRUCT.size + slot_count * (_SLOT_STRUCT.size + slot_bytes)

    @classmethod
    def create(cls, *, slot_count: int, slot_bytes: int, name: str | None = None) -> "SharedMemoryLatestBuffer":
        if slot_count <= 0:
            raise ValueError("slot_count must be > 0")
        if slot_bytes <= 0:
            raise ValueError("slot_bytes must be > 0")

        if name is None:
            name = f"datalens_shm_{uuid.uuid4().hex}"

        shm = SharedMemory(name=name, create=True, size=cls._calc_size(slot_count, slot_bytes))
        buf = cls(shm, slot_count=slot_count, slot_bytes=slot_bytes, creator=True)
        buf._write_global(current_seq=0, current_slot=0)
        for slot in range(slot_count):
            buf._write_slot_header(slot=slot, seq=0, length=0)
        return buf

    @classmethod
    def attach(cls, name: str) -> "SharedMemoryLatestBuffer":
        shm = SharedMemory(name=name, create=False)
        magic, version, slot_count, slot_bytes, current_seq, current_slot, _reserved = _GLOBAL_STRUCT.unpack_from(
            shm.buf, 0
        )
        if magic != MAGIC:
            shm.close()
            raise SharedMemoryProtocolError("Shared memory segment has unexpected magic")
        if version != VERSION:
            shm.close()
            raise SharedMemoryProtocolError(f"Unsupported shared memory version: {version}")
        if slot_count <= 0 or slot_bytes <= 0:
            shm.close()
            raise SharedMemoryProtocolError("Invalid shared memory header")
        return cls(shm, slot_count=int(slot_count), slot_bytes=int(slot_bytes), creator=False)

    def close(self) -> None:
        self._shm.close()
        if self._creator:
            try:
                self._shm.unlink()
            except FileNotFoundError:
                pass
            except OSError:
                pass

    def publish(self, payload: bytes) -> SharedMemoryPointer:
        if len(payload) > self._slot_bytes:
            raise ValueError(f"Payload too large for slot (len={len(payload)} > slot_bytes={self._slot_bytes})")

        _magic, _version, _slot_count, _slot_bytes, current_seq, current_slot, _reserved = self._read_global()
        next_seq = int(current_seq) + 1
        slot = next_seq % self._slot_count

        slot_offset = self._slot_offset(slot)
        data_offset = slot_offset + self._slot_header_size
        self._shm.buf[data_offset : data_offset + len(payload)] = payload

        self._write_slot_header(slot=slot, seq=next_seq, length=len(payload))
        self._write_global(current_seq=next_seq, current_slot=slot)

        return SharedMemoryPointer(name=self.name, slot=slot, seq=next_seq, length=len(payload))

    def read(self, pointer: SharedMemoryPointer) -> bytes:
        if pointer.name != self.name:
            raise ValueError("Pointer refers to a different shared memory segment")
        if pointer.slot < 0 or pointer.slot >= self._slot_count:
            raise ValueError("Pointer slot out of range")
        if pointer.length < 0 or pointer.length > self._slot_bytes:
            raise ValueError("Pointer length out of range")

        slot_seq, slot_len, _reserved = self._read_slot_header(pointer.slot)
        if int(slot_seq) != int(pointer.seq):
            raise SharedMemoryProtocolError("Requested slot has been overwritten")
        if int(slot_len) != int(pointer.length):
            raise SharedMemoryProtocolError("Requested slot length mismatch")

        slot_offset = self._slot_offset(pointer.slot)
        data_offset = slot_offset + self._slot_header_size
        return bytes(self._shm.buf[data_offset : data_offset + pointer.length])

    def latest_pointer(self) -> SharedMemoryPointer:
        _magic, _version, _slot_count, _slot_bytes, current_seq, current_slot, _reserved = self._read_global()
        slot_seq, slot_len, _reserved2 = self._read_slot_header(int(current_slot))
        if int(slot_seq) != int(current_seq):
            raise SharedMemoryProtocolError("Shared memory header points to an uncommitted slot")
        return SharedMemoryPointer(
            name=self.name,
            slot=int(current_slot),
            seq=int(current_seq),
            length=int(slot_len),
        )

    def _slot_offset(self, slot: int) -> int:
        return self._global_size + slot * self._slot_size

    def _read_global(self):
        return _GLOBAL_STRUCT.unpack_from(self._shm.buf, 0)

    def _write_global(self, *, current_seq: int, current_slot: int) -> None:
        _GLOBAL_STRUCT.pack_into(
            self._shm.buf,
            0,
            MAGIC,
            VERSION,
            self._slot_count,
            self._slot_bytes,
            int(current_seq),
            int(current_slot),
            0,
        )

    def _read_slot_header(self, slot: int):
        return _SLOT_STRUCT.unpack_from(self._shm.buf, self._slot_offset(slot))

    def _write_slot_header(self, *, slot: int, seq: int, length: int) -> None:
        _SLOT_STRUCT.pack_into(self._shm.buf, self._slot_offset(slot), int(seq), int(length), 0)
