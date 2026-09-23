"""Falcon engine MMIO model: interrupt aliasing, status, indirect mailbox."""
from __future__ import annotations

import pytest

from halucinator.peripheral_models.falcon_engine import (
    DEFAULT_READY_BITS, ENGINE_STATUS, FalconEngine, INTR, INTR_CLEAR,
    INTR_EN, INTR_EN_CLEAR, INTR_EN_SET, INTR_SET, MAILBOX_REQ, MAILBOX_RESP,
)


@pytest.fixture
def eng():
    return FalconEngine("eng", 0x0, 0x40000, registers={0x122234: 0x1E})


# -- interrupt controller aliasing ---------------------------------------

def test_set_makes_an_edge_line_pending(eng):
    eng.hw_write(INTR_SET, 4, 1 << 3)          # 3 = CHSW, edge
    assert eng.hw_read(INTR, 4) == 1 << 3


def test_clear_acknowledges_an_edge_line(eng):
    eng.hw_write(INTR_SET, 4, 1 << 3)
    eng.hw_write(INTR_CLEAR, 4, 1 << 3)
    assert eng.hw_read(INTR, 4) == 0


def test_set_is_ignored_for_a_level_line(eng):
    """intr.rst: "Attempts to SET or CLEAR level-triggered interrupts are
    ignored." Line 2 (FIFO) is level."""
    eng.hw_write(INTR_SET, 4, 1 << 2)
    assert eng.hw_read(INTR, 4) == 0


def test_hardware_can_still_raise_a_level_line(eng):
    """SET being ignored is about the register alias, not the wire."""
    eng.raise_line(2)
    assert eng.hw_read(INTR, 4) == 1 << 2


def test_enable_set_and_clear(eng):
    eng.hw_write(INTR_EN_SET, 4, (1 << 2) | (1 << 3))
    assert eng.hw_read(INTR_EN, 4) == (1 << 2) | (1 << 3)
    eng.hw_write(INTR_EN_CLEAR, 4, 1 << 2)
    assert eng.hw_read(INTR_EN, 4) == 1 << 3


def test_pending_and_enabled_is_the_intersection(eng):
    eng.hw_write(INTR_EN_SET, 4, 1 << 3)
    eng.raise_line(3)
    eng.raise_line(4)                           # pending but not enabled
    assert eng.pending_and_enabled() == 1 << 3


def test_status_registers_ignore_writes(eng):
    eng.raise_line(3)
    eng.hw_write(INTR, 4, 0)                    # read-only on hardware
    assert eng.hw_read(INTR, 4) == 1 << 3


# -- engine status --------------------------------------------------------

def test_status_reports_ready(eng):
    """The bits the GP102 microcode's poll loops wait on."""
    assert eng.hw_read(ENGINE_STATUS, 4) == DEFAULT_READY_BITS
    for bit in (0x40, 0x80, 0x4000):
        assert eng.hw_read(ENGINE_STATUS, 4) & bit


# -- indirect mailbox -----------------------------------------------------

def test_mailbox_serves_a_modelled_register(eng):
    eng.hw_write(MAILBOX_REQ, 4, 0x122234)
    assert eng.hw_read(MAILBOX_RESP, 4) == 0x1E


def test_mailbox_masks_the_control_bits_off_the_request(eng):
    """The helper ORs flags into the top of the request word."""
    eng.hw_write(MAILBOX_REQ, 4, 0x122234 | (0x2 << 26))
    assert eng.hw_read(MAILBOX_RESP, 4) == 0x1E


def test_unmodelled_indirect_register_reads_zero(eng):
    eng.hw_write(MAILBOX_REQ, 4, 0x409604)
    assert eng.hw_read(MAILBOX_RESP, 4) == 0


def test_request_register_reads_back_not_busy(eng):
    """The microcode polls bit 31 of the request register for "not busy"."""
    eng.hw_write(MAILBOX_REQ, 4, 0x122234)
    assert eng.hw_read(MAILBOX_REQ, 4) & (1 << 31) == 0
