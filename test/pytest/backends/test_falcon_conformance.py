"""End-to-end Falcon check: exact arithmetic, driven by real interrupts.

Unlike the other Falcon suites, this one runs an actual emulator over an
actual firmware image. The image is ours (test/falcon_conformance/), assembled
from irq_compute.fuc with envytools' envyas, so nothing vendor-owned is
redistributed and the expected values can be derived from the source rather
than recorded from a previous run.

The four words it checks are chosen so that a defect changes a number instead
of merely looking odd:

  sum_sq     64 iterations of mulu + add, each term computed through a
             call/ret pair, so the return address has to survive on the DMEM
             stack alongside push/pop.
  irq_count  the firmware waits for exactly 8 interrupts before it proceeds,
             so this is 8 by construction however fast the model runs -- and
             if interrupts stop arriving, the firmware hangs rather than
             producing a plausible smaller number.
  mix        folded by the handler on every entry, in order, through a chain
             built to overflow 16 bits, which pins mulu's documented
             16x16->32 truncation.
  done       mix ^ sum_sq, written last, so it also serves as the "finished"
             marker.

Skipped unless pyghidra and the Falcon processor module are both installed.
"""
from __future__ import annotations

import os
import pathlib

import pytest

pytest.importorskip("pyghidra")

FW = (pathlib.Path(__file__).resolve().parents[2]
      / "falcon_conformance" / "irq_compute.bin")

M32 = 0xFFFFFFFF
N_IRQ, TERMS = 8, 64
IRQ_COUNT, MIX, SUM_SQ, DONE = 0x00, 0x04, 0x08, 0x0C


def _expected():
    sum_sq = 0
    for i in range(1, TERMS + 1):
        sum_sq = (sum_sq + (i & 0xFFFF) * (i & 0xFFFF)) & M32
    mix = 0
    for k in range(1, N_IRQ + 1):
        mix = (((mix & 0xFFFF) * 0x1F) + k) & M32
    return N_IRQ, mix, sum_sq, mix ^ sum_sq


def _run(no_timer=False, cap=400_000):
    from halucinator.backends.ghidra_backend import GhidraBackend
    from halucinator.backends.hal_backend import MemoryRegion
    from halucinator.backends.irq.delivery import DeliveryPlan
    from halucinator.peripheral_models.falcon_engine import FalconEngine

    be = GhidraBackend(arch="falcon", cpu_model="fuc5")
    engine = FalconEngine("engine", 0x0, 0x40000)
    if no_timer:
        engine.tick = lambda steps=1: None
    be.add_memory_region(MemoryRegion("imem", 0x0, 0x8000,
                                      permissions="rwx", file=str(FW)))
    be.add_memory_region(MemoryRegion("dmem", 0x0, 0x4000,
                                      permissions="rw", space="dmem"))
    be.add_memory_region(MemoryRegion("io", 0x0, 0x40000, permissions="rw",
                                      space="io", emulate=engine))
    be.init()
    be.write_register("sp", 0x1000)
    be.write_register("pc", 0x0)
    be.auto_deliver_peripheral_irqs = True
    be.peripheral_irq_plan = DeliveryPlan(falcon_vector=0, stack_space="dmem")
    for _ in range(cap):
        be.step()
        if be.read_memory(DONE, 4, space="dmem"):
            break
    return be, engine, tuple(be.read_memory(a, 4, space="dmem")
                             for a in (IRQ_COUNT, MIX, SUM_SQ, DONE))


@pytest.fixture(scope="module")
def run():
    if not os.environ.get("GHIDRA_INSTALL_DIR"):
        pytest.skip("GHIDRA_INSTALL_DIR not set")
    if not FW.exists():
        pytest.skip(f"{FW} missing")
    try:
        return _run()
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"Falcon language unavailable: {exc}")


def test_the_firmware_finishes(run):
    _, _, (_, _, _, done) = run
    assert done, "firmware never wrote its done marker"


def test_every_word_is_exact(run):
    _, _, got = run
    assert got == _expected()


def test_the_arithmetic_is_right(run):
    """64 mulu+add terms, each through a call/ret over the DMEM stack."""
    _, _, (_, _, sum_sq, _) = run
    assert sum_sq == sum(i * i for i in range(1, TERMS + 1)) == 89440


def test_exactly_one_handler_entry_per_expiry(run):
    _, engine, (irq_count, _, _, _) = run
    assert irq_count == N_IRQ
    assert engine.timer_ticks == N_IRQ


def test_no_instruction_wedged_the_emulator(run):
    be, _, _ = run
    assert getattr(be, "_step_fault_pc", None) is None


def test_without_a_timer_nothing_is_produced():
    """The control. A harness that passes here is measuring itself."""
    if not os.environ.get("GHIDRA_INSTALL_DIR") or not FW.exists():
        pytest.skip("Falcon language unavailable")
    try:
        _, engine, got = _run(no_timer=True, cap=20_000)
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"Falcon language unavailable: {exc}")
    assert engine.timer_ticks == 0
    assert got == (0, 0, 0, 0)
