# Copyright 2026 Christopher Wright
"""NVIDIA Falcon engine I/O space.

Models the parts of a Falcon engine's MMIO that its microcode actually touches
during bring-up, so a rehost does not need a harness poking registers from
outside. Three groups, each derived from a documented register map or from the
firmware's own code:

**Interrupt controller** (envytools ``docs/hw/falcon/intr.rst``) --
set/clear/status triples, implemented with their real aliasing semantics::

    I[0x00000] INTR_SET        write-only; 1 bits make lines pending
    I[0x00100] INTR_CLEAR      write-only; 1 bits acknowledge
    I[0x00200] INTR            status, read-only
    I[0x00400] INTR_EN_SET     write-only
    I[0x00500] INTR_EN_CLEAR   write-only
    I[0x00600] INTR_EN         status, read-only

Writes to SET/CLEAR for a line configured level-triggered are ignored, as on
hardware. (``FalconIrqController`` writes the status register directly instead;
that is deliberate -- it is an outside-in injection path, and this class is
where the hardware's aliasing actually belongs.)

**Engine status** -- the register the microcode polls for readiness. Which bits
mean "ready" is read off the firmware's own poll loops rather than assumed: a
loop of the shape ``iord`` / ``and`` or ``shr`` / branch-back states the value
needed to leave it. For GP102 FECS and GPCCS both, that is bits 0x40, 0x80 and
0x4000 of ``I[0x10000]``, and both images agree independently.

**Indirect-register mailbox** -- the microcode reaches registers outside its own
I/O window through a request/response pair, per its access helper::

    iowr I[0x1ca00] <address | flags>   submit
    poll I[0x1ca00] until bit31 clear   not busy
    poll I[0x10000] until bit6 set      result ready
    iord I[0x1cb00]                     take the value

``registers`` supplies values for those indirect addresses; anything not listed
reads as zero, which is the honest default for a register nothing has modelled.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from halucinator.peripherals.hal_peripheral import HalPeripheral as AvatarPeripheral

log = logging.getLogger(__name__)

# Interrupt controller
INTR_SET, INTR_CLEAR, INTR = 0x00000, 0x00100, 0x00200
INTR_EN_SET, INTR_EN_CLEAR, INTR_EN = 0x00400, 0x00500, 0x00600

# Engine status, and the mailbox pair
ENGINE_STATUS = 0x10000
MAILBOX_REQ, MAILBOX_RESP = 0x1CA00, 0x1CB00

# Bits of ENGINE_STATUS the GP102 graphics-block microcode waits on. Derived
# from its poll loops, not assumed: 0x80 at fecs:0x53b, 0x40 at fecs:0x6ce,
# 0x4000 at fecs:0xb9e -- and the same three in gpccs.
DEFAULT_READY_BITS = 0x40 | 0x80 | 0x4000        # == 0x40C0

# The request word carries the target address in its low bits and control in
# the top (the helper ORs in `r11` and `r12 << 26`).
REQ_ADDR_MASK = 0x03FFFFFF
BUSY_BIT = 1 << 31


class FalconEngine(AvatarPeripheral):
    """Falcon engine MMIO: interrupt controller, status, indirect mailbox."""

    def __init__(self, name: str, address: int, size: int,
                 registers: Optional[Dict[int, int]] = None,
                 ready_bits: int = DEFAULT_READY_BITS,
                 level_lines: int = 0,
                 **kwargs: Any) -> None:
        AvatarPeripheral.__init__(self, name, address, size)
        self.registers: Dict[int, int] = dict(registers or {})
        self.ready_bits = ready_bits
        # Lines wired level-triggered; SET/CLEAR writes to these are ignored.
        # Defaults match intr.rst: line 2 (FIFO) plus the engine-specific
        # 10..15 range.
        self.level_lines = level_lines or ((1 << 2) | (0x3F << 10))
        self.intr = 0
        self.intr_en = 0
        self._pending_req = 0
        self.read_handler[0:size] = self.hw_read
        self.write_handler[0:size] = self.hw_write
        log.info("%s: Falcon engine MMIO at 0x%08x (+0x%x), %d modelled "
                 "indirect registers", name, address, size, len(self.registers))

    def live_registers(self):
        """Offsets the backend should exchange with this model every step.

        Bounded on purpose: the I/O window is 256 KB and sweeping it per
        instruction would dominate the run. These are the registers the
        microcode actually polls or drives.
        """
        return (INTR, INTR_EN, ENGINE_STATUS, MAILBOX_REQ, MAILBOX_RESP,
                INTR_SET, INTR_CLEAR, INTR_EN_SET, INTR_EN_CLEAR)

    # -- interrupt lines ---------------------------------------------------

    def raise_line(self, num: int) -> None:
        """Make line `num` pending, as the engine's own hardware would."""
        self.intr |= 1 << num

    def pending_and_enabled(self) -> int:
        return self.intr & self.intr_en

    # -- MMIO --------------------------------------------------------------

    def hw_read(self, offset: int, size: int, pc: int = 0xBAADBAAD,
                **kwargs: Any) -> int:
        if offset == INTR:
            return self.intr
        if offset == INTR_EN:
            return self.intr_en
        if offset == ENGINE_STATUS:
            # Always ready: there is no modelled latency, and a poll that can
            # never succeed is indistinguishable from a hung rehost.
            return self.ready_bits
        if offset == MAILBOX_REQ:
            return 0                      # busy bit clear: the request is done
        if offset == MAILBOX_RESP:
            val = self.registers.get(self._pending_req, 0)
            log.debug("%s: mailbox read 0x%06x -> 0x%08x",
                      self.name, self._pending_req, val)
            return val
        if offset in (INTR_SET, INTR_CLEAR, INTR_EN_SET, INTR_EN_CLEAR):
            # Write-only on hardware; reads are undefined. Return 0 rather than
            # inventing a value, and say so once.
            log.debug("%s: read of write-only register 0x%05x", self.name, offset)
            return 0
        return self.registers.get(offset, 0)

    def hw_write(self, offset: int, size: int, value: int,
                 pc: int = 0xBAADBAAD, **kwargs: Any) -> bool:
        if offset == INTR_SET:
            self.intr |= value & ~self.level_lines
        elif offset == INTR_CLEAR:
            self.intr &= ~(value & ~self.level_lines)
        elif offset == INTR_EN_SET:
            self.intr_en |= value
        elif offset == INTR_EN_CLEAR:
            self.intr_en &= ~value
        elif offset == MAILBOX_REQ:
            self._pending_req = value & REQ_ADDR_MASK
            log.debug("%s: mailbox request 0x%06x (raw 0x%08x)",
                      self.name, self._pending_req, value)
        elif offset in (INTR, INTR_EN):
            log.debug("%s: ignoring write to read-only status 0x%05x",
                      self.name, offset)
        else:
            self.registers[offset] = value
        return True
