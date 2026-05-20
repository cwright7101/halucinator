"""Tests for RecordingPeripheral / AutoPeripheral (auto-modeling runtime)."""
import sqlite3

from halucinator.peripheral_models.auto_model import (
    AutoPeripheral, RecordingPeripheral,
)


def test_recording_logs_reads_and_writes():
    p = RecordingPeripheral("rec", 0x40000000, 0x1000)
    assert p.hw_read(0x10, 4, pc=0x800) == 0
    p.hw_write(0x20, 4, 0xDEAD, pc=0x804)
    assert len(p.trace) == 2
    seq, pc, addr, size, value, rw = p.trace[0]
    assert (addr, rw) == (0x40000010, "r")
    seq, pc, addr, size, value, rw = p.trace[1]
    assert (addr, value, rw) == (0x40000020, 0xDEAD, "w")


def test_recording_flush_to_sqlite(tmp_path):
    db = str(tmp_path / "t.sqlite")
    p = RecordingPeripheral("rec", 0x40000000, 0x1000, db_path=db)
    for _ in range(5):
        p.hw_read(0, 4, pc=0x1000)
    p.flush()
    conn = sqlite3.connect(db)
    n = conn.execute("SELECT COUNT(*) FROM mmio_trace").fetchone()[0]
    conn.close()
    assert n == 5


def test_auto_breaks_busy_wait():
    p = AutoPeripheral("auto", 0x40000000, 0x1000, stall_threshold=8)
    # Same pc reading the same addr in a tight loop -> escalates to all-ones.
    vals = [p.hw_read(0x0, 4, pc=0x8000) for _ in range(12)]
    assert vals[0] == 0          # not yet a detected stall
    assert vals[-1] == 0xFFFFFFFF  # busy-wait broken with all-ones


def test_auto_busy_wait_respects_size():
    p = AutoPeripheral("auto", 0x40000000, 0x1000, stall_threshold=4)
    vals = [p.hw_read(0x4, 2, pc=0x9000) for _ in range(8)]
    assert vals[-1] == 0xFFFF     # 2-byte read -> 16-bit all-ones


def test_auto_captures_uart_output(caplog):
    import logging
    p = AutoPeripheral("auto", 0x40000000, 0x1000)
    with caplog.at_level(logging.INFO):
        for ch in b"Grbl\n":
            p.hw_write(0x404, 1, ch, pc=0xA000)
    assert any("Grbl" in r.getMessage() for r in caplog.records)


def test_auto_distinct_reads_do_not_trigger_stall():
    p = AutoPeripheral("auto", 0x40000000, 0x1000, stall_threshold=8)
    # Alternating pcs => never a consecutive run => no all-ones.
    vals = []
    for i in range(20):
        vals.append(p.hw_read(0x0, 4, pc=0x8000 + (i % 2) * 4))
    assert all(v == 0 for v in vals)
