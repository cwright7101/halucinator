"""Recording + self-modeling peripherals.

`RecordingPeripheral` observes every MMIO access at the catch-all region
and logs (seq, pc, addr, size, value, rw) — to memory always, and to a
SQLite `mmio_trace` table when a db path is configured. It is the data
source for the offline synthesizer (tools/synthesize_model.py).

`AutoPeripheral` adds a runtime policy that lets unmodeled firmware boot
without hand-written intercepts:

  * Busy-wait breaker (uEmu-lite). Firmware routinely spins on a status
    bit — `while(!(REG & READY));` or `while(REG & BUSY);`. With a
    return-0 catch-all those loops never exit. We detect a stall (the
    same instruction reading the same address many times in a row) and
    escalate the returned value: first all-ones (breaks "wait for a bit
    to SET", the common case: HSERDY/PLLRDY/TXE/RXNE), then zero (breaks
    "wait while BUSY"); whichever ends the stall is cached for that
    (pc,addr).

  * Output capture. A register that receives a stream of byte writes
    whose low byte is printable ASCII is almost certainly a UART/data
    TX register; we accumulate and log it, surfacing the firmware's
    console (e.g. a GRBL banner) without knowing the driver function.

This is intentionally heuristic — it gets firmware booting and produces
a trace; the synthesizer (optionally LLM-assisted) turns the trace into a
reviewable, precise model.
"""
from __future__ import annotations

import logging
import sqlite3
import time
from typing import Any, Dict, List, Optional, Tuple

from .generic import GenericPeripheral
from .. import hal_log

log = logging.getLogger(__name__)
hlog = hal_log.getHalLogger()


class RecordingPeripheral(GenericPeripheral):
    """Catch-all that records every access. Reads still return 0."""

    # Flush to SQLite every this many accesses so the trace survives even a
    # hard kill (firmware that spins forever never lets a clean shutdown /
    # flush run, because the unicorn emu_start C loop doesn't return).
    FLUSH_EVERY = 4096      # accesses
    FLUSH_SECONDS = 2.0     # ...or wall-clock, whichever comes first

    def __init__(self, name: str, address: int, size: int,
                 db_path: Optional[str] = None, **kwargs: Any) -> None:
        super().__init__(name, address, size, **kwargs)
        self.db_path = db_path
        self._seq = 0
        self._flushed = 0
        self._conn: Optional[sqlite3.Connection] = None
        self._last_flush = time.monotonic()
        self.trace: List[Tuple[int, int, int, int, int, str]] = []

    def _record(self, pc: int, addr: int, size: int, value: int, rw: str) -> None:
        self.trace.append((self._seq, pc, addr, size, value, rw))
        self._seq += 1
        # Flush on either a count threshold (chatty firmware) or a wall-clock
        # interval (low-MMIO firmware that loops forever in compute) — the
        # emu_start C loop never returns so a clean-shutdown flush can't run.
        if self.db_path and (self._seq - self._flushed) >= self.FLUSH_EVERY:
            self.flush()
        elif self.db_path and (time.monotonic() - self._last_flush) >= self.FLUSH_SECONDS:
            self.flush()

    def hw_read(self, offset: int, size: int, pc: int = 0xBAADBAAD, **kwargs: Any) -> int:
        addr = self.address + offset
        self._record(pc, addr, size, 0, "r")
        return 0

    def hw_write(self, offset: int, size: int, value: int,
                 pc: int = 0xBAADBAAD, **kwargs: Any) -> bool:
        addr = self.address + offset
        self._record(pc, addr, size, value, "w")
        return True

    def flush(self) -> None:
        """Persist new trace rows to SQLite (incremental). Safe to call
        repeatedly; only rows since the last flush are written."""
        if not self.db_path:
            return
        if self._conn is None:
            self._conn = sqlite3.connect(self.db_path)
            self._conn.execute(
                "CREATE TABLE IF NOT EXISTS mmio_trace ("
                "id INTEGER PRIMARY KEY AUTOINCREMENT, region TEXT, seq INTEGER,"
                " pc INTEGER, addr INTEGER, size INTEGER, value INTEGER, rw TEXT)")
        new = self.trace[self._flushed:]
        if new:
            self._conn.executemany(
                "INSERT INTO mmio_trace(region, seq, pc, addr, size, value, rw)"
                " VALUES (?,?,?,?,?,?,?)",
                [(self.name, s, pc, a, sz, v, rw)
                 for (s, pc, a, sz, v, rw) in new])
            self._conn.commit()
            self._flushed = len(self.trace)
        self._last_flush = time.monotonic()
        # Drop the in-memory prefix we've persisted to bound memory on
        # long-running (looping) firmware, keeping seq numbers intact.
        if self._flushed > 200_000:
            self.trace = self.trace[self._flushed:]
            self._flushed = 0

    def shutdown(self) -> None:  # noqa: D401
        try:
            self.flush()
            if self._conn is not None:
                self._conn.close()
                self._conn = None
        except Exception:  # noqa: BLE001
            log.exception("RecordingPeripheral flush failed")
        super().shutdown() if hasattr(super(), "shutdown") else None


class AutoPeripheral(RecordingPeripheral):
    """RecordingPeripheral + busy-wait breaker + output capture."""

    def __init__(self, name: str, address: int, size: int,
                 db_path: Optional[str] = None,
                 stall_threshold: int = 16, **kwargs: Any) -> None:
        super().__init__(name, address, size, db_path=db_path, **kwargs)
        self.stall_threshold = stall_threshold
        # (pc, addr) -> consecutive repeat count
        self._repeat: Dict[Tuple[int, int], int] = {}
        self._last_key: Optional[Tuple[int, int]] = None
        # (pc, addr) -> cached value that broke the stall
        self._cached: Dict[Tuple[int, int], int] = {}
        # addr -> accumulated printable output bytes
        self._out: Dict[int, bytearray] = {}

    def _mask(self, size: int) -> int:
        return (1 << (8 * size)) - 1

    def hw_read(self, offset: int, size: int, pc: int = 0xBAADBAAD, **kwargs: Any) -> int:
        addr = self.address + offset
        self._record(pc, addr, size, 0, "r")
        key = (pc, addr)

        if key in self._cached:
            return self._cached[key]

        if key == self._last_key:
            self._repeat[key] = self._repeat.get(key, 0) + 1
        else:
            self._repeat[key] = 0
            self._last_key = key

        n = self._repeat[key]
        if n >= self.stall_threshold:
            # Escalate: all-ones first (wait-for-SET, the common case),
            # then zero (wait-while-BUSY) on a second stall window.
            if n < self.stall_threshold * 2:
                val = self._mask(size)
            else:
                val = 0
                self._cached[key] = val  # give up escalating; pin to 0
            hlog.info(
                "AutoPeripheral: busy-wait at pc=0x%08x addr=0x%08x -> 0x%x",
                pc, addr, val)
            return val
        return 0

    def hw_write(self, offset: int, size: int, value: int,
                 pc: int = 0xBAADBAAD, **kwargs: Any) -> bool:
        addr = self.address + offset
        self._record(pc, addr, size, value, "w")
        # Output capture: printable low byte => likely a data/TX register.
        low = value & 0xFF
        if size <= 4 and (low == 0x0A or low == 0x0D or 0x20 <= low < 0x7F):
            buf = self._out.setdefault(addr, bytearray())
            if low == 0x0A:  # newline -> emit the line
                line = buf.decode("latin-1").rstrip("\r")
                hlog.info("AutoPeripheral UART(0x%08x): %s", addr, line)
                buf.clear()
            elif low != 0x0D:
                buf.append(low)
        # A write to a polled status register usually clears the stall.
        self._last_key = None
        return True
