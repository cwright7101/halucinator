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
        # (pc, addr) -> running value for free-running-counter registers
        self._counter: Dict[Tuple[int, int], int] = {}
        # Addresses explicitly modeled as free-running counters: every read
        # returns a monotonically increasing value (from the FIRST read, so a
        # `start=REG; while(REG-start < N)` calibrated delay sees a real delta
        # and elapses). Declare via HAL_AUTO_COUNTER_ADDRS=0xADDR[,0xADDR...]
        # — the generic spin heuristic can't catch a counter polled in a loop
        # that also reads other registers (the consecutive run keeps resetting).
        import os as _os
        self._counter_addrs = set()
        for tok in _os.environ.get("HAL_AUTO_COUNTER_ADDRS", "").split(","):
            tok = tok.strip()
            if tok:
                try:
                    self._counter_addrs.add(int(tok, 0))
                except ValueError:
                    log.warning("bad HAL_AUTO_COUNTER_ADDRS token %r", tok)
        self._free_counter: Dict[int, int] = {}   # addr -> running value
        self._counter_step = int(
            _os.environ.get("HAL_AUTO_COUNTER_STEP", "0x1000"), 0)
        if self._counter_addrs:
            hlog.info("AutoPeripheral: free-running counter regs: %s",
                      ", ".join("0x%08x" % a for a in sorted(self._counter_addrs)))
        # addr -> accumulated printable output bytes
        self._out: Dict[int, bytearray] = {}
        # HAL_MMIO_LOG=1: log the FIRST read of each (pc,addr) hardware register
        # and the value we hand back. These first-reads return 0 by default --
        # the suspects for "firmware needed a 1 here, got 0, took the wrong
        # branch". Diagnostic-only; deduped so it can't spam.
        self._mmio_log = _os.environ.get("HAL_MMIO_LOG") == "1"
        self._logged_reads: set = set()

    def _mask(self, size: int) -> int:
        return (1 << (8 * size)) - 1

    def hw_read(self, offset: int, size: int, pc: int = 0xBAADBAAD, **kwargs: Any) -> int:
        addr = self.address + offset
        self._record(pc, addr, size, 0, "r")
        key = (pc, addr)

        # Free-running counter register: monotonically increasing every read.
        if addr in self._counter_addrs:
            cur = self._free_counter.get(addr, 0) + self._counter_step
            self._free_counter[addr] = cur
            return cur & self._mask(size)

        if key in self._cached:
            return self._cached[key]

        if key == self._last_key:
            self._repeat[key] = self._repeat.get(key, 0) + 1
        else:
            self._repeat[key] = 0
            self._last_key = key

        n = self._repeat[key]
        if n >= self.stall_threshold:
            t = self.stall_threshold
            # Escalate through three tiers as the same read keeps spinning:
            #   1. all-ones  — breaks `while(!(REG & READY))` (wait-for-SET,
            #      the common case: HSERDY/PLLRDY/TXE/RXNE).
            #   2. zero      — breaks `while(REG & BUSY)` (wait-while-BUSY).
            #   3. monotonic counter — neither constant broke the stall, so
            #      the firmware is timing against a FREE-RUNNING COUNTER
            #      (`start=REG; while(REG-start < N)` calibrated delay). A
            #      constant can never satisfy it; return an ever-increasing
            #      value so the delay elapses. The step is large and grows
            #      with the spin so any finite threshold is crossed quickly.
            if n < t * 2:
                val = self._mask(size)
            elif n < t * 3:
                val = 0
            else:
                cur = self._counter.get(key, 0) + (n - t * 3 + 1) * 0x10000
                self._counter[key] = cur
                val = cur & self._mask(size)
            hlog.info(
                "AutoPeripheral: busy-wait at pc=0x%08x addr=0x%08x -> 0x%x",
                pc, addr, val)
            return val
        if self._mmio_log and key not in self._logged_reads:
            self._logged_reads.add(key)
            hlog.info("MMIO-READ pc=0x%08x addr=0x%08x size=%d -> 0x0 "
                      "(first read, default)", pc, addr, size)
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
