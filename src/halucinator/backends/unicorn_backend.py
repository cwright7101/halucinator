"""
UnicornBackend — in-process emulation via unicorn-engine.

No subprocess, no sockets: the firmware runs inside the Python process.
Breakpoints are implemented as unicorn CODE hooks.

Performance is typically 10-100× faster than the avatar2/QEMU path for
firmware that doesn't need real hardware peripheral timing.

Supported: ARM Thumb / ARM Cortex-M (primary target for halucinator).
           Other architectures can be added by extending the _ARCH_MAP.
"""
from __future__ import annotations

import logging
import struct
from typing import Any, Callable, Dict, List, Optional, Tuple, Union

from .hal_backend import ABI_MIXINS, ARM32HalMixin, ARMHalMixin, HalBackend, MemoryRegion

log = logging.getLogger(__name__)

try:
    import unicorn
    import unicorn.arm_const as arm_const
    try:
        import unicorn.arm64_const as arm64_const
    except ImportError:
        arm64_const = None  # type: ignore[assignment]
    try:
        import unicorn.mips_const as mips_const
    except ImportError:
        mips_const = None  # type: ignore[assignment]
    try:
        import unicorn.ppc_const as ppc_const
    except ImportError:
        ppc_const = None  # type: ignore[assignment]
    _HAVE_UNICORN = True
except ImportError:
    _HAVE_UNICORN = False
    unicorn = None  # type: ignore[assignment]
    arm_const = None  # type: ignore[assignment]
    arm64_const = None  # type: ignore[assignment]
    mips_const = None  # type: ignore[assignment]
    ppc_const = None  # type: ignore[assignment]


# ---------------------------------------------------------------------------
# Architecture tables
# ---------------------------------------------------------------------------
#
# Maps halucinator arch string -> (unicorn_arch, unicorn_mode, is_thumb,
#   is_big_endian, word_size_bytes).
#
# Thumb applies only to 32-bit ARM; BE applies to MIPS and PPC. word_size
# controls pointer width in read_memory(..., num_words=1).
_ARCH_MAP: Dict[str, Tuple[str, str, bool, bool, int]] = {
    "cortex-m3":      ("arm",    "thumb", True,  False, 4),
    "arm":            ("arm",    "arm",   False, False, 4),
    "arm64":          ("arm64",  "arm",   False, False, 8),
    "mips":           ("mips",   "mips32_be", False, True, 4),
    "powerpc":        ("ppc",    "ppc32_be", False, True, 4),
    "powerpc:MPC8XX": ("ppc",    "ppc32_be", False, True, 4),
    "ppc64":          ("ppc",    "ppc64_be", False, True, 8),
}

_PERM_MAP = {
    "r":   0x1,
    "w":   0x2,
    "x":   0x4,
    "rw":  0x3,
    "rx":  0x5,
    "rwx": 0x7,
    "xr":  0x5,
    "xrw": 0x7,
}

_REG_MAPS_CACHE: Dict[str, Dict[str, int]] = {}


def _get_arm_reg_map() -> Dict[str, int]:
    if "arm" in _REG_MAPS_CACHE:
        return _REG_MAPS_CACHE["arm"]
    if arm_const is None:
        return {}
    m = {
        **{f"r{i}": getattr(arm_const, f"UC_ARM_REG_R{i}") for i in range(13)},
        "sp":   arm_const.UC_ARM_REG_SP,
        "lr":   arm_const.UC_ARM_REG_LR,
        "pc":   arm_const.UC_ARM_REG_PC,
        "cpsr": arm_const.UC_ARM_REG_CPSR,
        "spsr": arm_const.UC_ARM_REG_SPSR,
    }
    _REG_MAPS_CACHE["arm"] = m
    return m


def _get_arm64_reg_map() -> Dict[str, int]:
    if "arm64" in _REG_MAPS_CACHE:
        return _REG_MAPS_CACHE["arm64"]
    if arm64_const is None:
        return {}
    m = {
        **{f"x{i}": getattr(arm64_const, f"UC_ARM64_REG_X{i}") for i in range(29)},
        "sp": arm64_const.UC_ARM64_REG_SP,
        "pc": arm64_const.UC_ARM64_REG_PC,
    }
    # x29 = fp, x30 = lr on AArch64
    for name, reg in (
        ("x29", "UC_ARM64_REG_X29"),
        ("x30", "UC_ARM64_REG_X30"),
        ("fp",  "UC_ARM64_REG_FP"),
        ("lr",  "UC_ARM64_REG_LR"),
    ):
        v = getattr(arm64_const, reg, None)
        if v is not None:
            m[name] = v
    _REG_MAPS_CACHE["arm64"] = m
    return m


def _get_mips_reg_map() -> Dict[str, int]:
    if "mips" in _REG_MAPS_CACHE:
        return _REG_MAPS_CACHE["mips"]
    if mips_const is None:
        return {}
    # Unicorn MIPS register consts: UC_MIPS_REG_0..UC_MIPS_REG_31 exist.
    # ABI aliases (a0-a3 = r4-r7, etc.) are named after registers in the
    # mips_const module too.
    m: Dict[str, int] = {}
    for i in range(32):
        m[f"r{i}"] = getattr(mips_const, f"UC_MIPS_REG_{i}")
    # ABI alias registers: these are named differently in mips_const
    aliases = {
        "zero": 0, "at": 1, "v0": 2, "v1": 3,
        "a0": 4, "a1": 5, "a2": 6, "a3": 7,
        "t0": 8, "t1": 9, "t2": 10, "t3": 11, "t4": 12,
        "t5": 13, "t6": 14, "t7": 15,
        "s0": 16, "s1": 17, "s2": 18, "s3": 19,
        "s4": 20, "s5": 21, "s6": 22, "s7": 23,
        "t8": 24, "t9": 25, "k0": 26, "k1": 27,
        "gp": 28, "sp": 29, "fp": 30, "ra": 31,
    }
    for name, idx in aliases.items():
        m[name] = getattr(mips_const, f"UC_MIPS_REG_{idx}")
    m["pc"] = mips_const.UC_MIPS_REG_PC
    _REG_MAPS_CACHE["mips"] = m
    return m


def _get_ppc_reg_map(word: int = 4) -> Dict[str, int]:
    cache_key = f"ppc{word * 8}"
    if cache_key in _REG_MAPS_CACHE:
        return _REG_MAPS_CACHE[cache_key]
    if ppc_const is None:
        return {}
    m: Dict[str, int] = {
        f"r{i}": getattr(ppc_const, f"UC_PPC_REG_{i}") for i in range(32)
    }
    # PPC SPRs that halucinator bp handlers commonly touch
    for name, const_name in (
        ("pc",  "UC_PPC_REG_PC"),
        ("msr", "UC_PPC_REG_MSR"),
        ("cr",  "UC_PPC_REG_CR"),
        ("lr",  "UC_PPC_REG_LR"),
        ("ctr", "UC_PPC_REG_CTR"),
        ("xer", "UC_PPC_REG_XER"),
    ):
        v = getattr(ppc_const, const_name, None)
        if v is not None:
            m[name] = v
    # r1 is the PPC stack pointer
    if "r1" in m:
        m["sp"] = m["r1"]
    _REG_MAPS_CACHE[cache_key] = m
    return m


def _reg_map_for_arch(arch: str) -> Dict[str, int]:
    info = _ARCH_MAP.get(arch)
    if info is None:
        return _get_arm_reg_map()
    uc_arch = info[0]
    if uc_arch == "arm":
        return _get_arm_reg_map()
    if uc_arch == "arm64":
        return _get_arm64_reg_map()
    if uc_arch == "mips":
        return _get_mips_reg_map()
    if uc_arch == "ppc":
        word = info[4]
        return _get_ppc_reg_map(word)
    return {}


# ---------------------------------------------------------------------------
# UnicornBackend
# ---------------------------------------------------------------------------

class UnicornBackend(ARMHalMixin, HalBackend):
    """
    In-process emulation backend using unicorn-engine.

    Usage::

        backend = UnicornBackend(arch="cortex-m3")
        backend.add_memory_region(MemoryRegion("flash", 0x08000000, 0x80000,
                                                permissions="rx",
                                                file="/path/to/firmware.bin"))
        backend.add_memory_region(MemoryRegion("ram", 0x20000000, 0x20000, "rw"))
        backend.init()

        bp_id = backend.set_breakpoint(0x08001234)
        backend.cont()            # runs until breakpoint
        pc = backend.read_register("pc")
    """

    def __init__(
        self,
        config: Any = None,
        arch: str = "cortex-m3",
        **kwargs: Any,
    ):
        if not _HAVE_UNICORN:
            raise ImportError(
                "unicorn-engine is required for UnicornBackend. "
                "Install it with: pip install unicorn"
            )
        self.config = config
        self.arch_name = arch
        self._uc: Optional[Any] = None           # unicorn.Uc instance
        self._regions: List[MemoryRegion] = []
        self._bp_hooks: Dict[int, Tuple[int, Any]] = {}  # bp_id → (addr, hook_h)
        self._mmio_hooks: Dict[int, Any] = {}    # region_name → hook_handle
        self._next_bp_id = 1
        self._stopped = True
        self._bp_hit_addr: Optional[int] = None
        self._breakpoints: Dict[int, int] = {}   # addr → bp_id
        self._bp_callbacks: Dict[int, Callable] = {}  # bp_id → callback
        # Pending IRQ injected from another thread (peripheral_server zmq
        # handler). cont() drains the queue before re-entering emu_start
        # so the synthetic exception frame is set up single-threaded.
        self._pending_irqs: List[int] = []

        # Opt-in: skip an unhandled SVC instruction (advance past it and
        # zero r0) instead of aborting. Used by the auto-modeling path to
        # tolerate fuzz-harness hypercalls baked into instrumented binaries
        # (e.g. P2IM's aflCall `svc #0x3f`).
        self.skip_svc: bool = False

        # Pre-compute the register name -> unicorn reg id map for this arch.
        self._reg_map = _reg_map_for_arch(arch)
        # Cache arch traits from _ARCH_MAP for hot paths (cont/read_memory).
        info = _ARCH_MAP.get(arch, ("arm", "thumb", True, False, 4))
        _, _, self._is_thumb, self._is_be, self._word_size = info

        # Bind the arch-specific ABI mixin onto the instance (ARM32 stays the
        # default via inheritance so existing arm/cortex-m callers are
        # unchanged).
        abi_cls = ABI_MIXINS.get(arch, ARM32HalMixin)
        self._abi = abi_cls
        if abi_cls is not ARM32HalMixin:
            for method_name in ("get_arg", "set_args", "get_ret_addr",
                                "set_ret_addr", "execute_return",
                                "read_string"):
                method = getattr(abi_cls, method_name, None)
                if method is not None:
                    setattr(self, method_name,
                            method.__get__(self, type(self)))

    # ------------------------------------------------------------------
    # Initialisation
    # ------------------------------------------------------------------

    def init(self) -> None:
        """Initialise unicorn engine and map all registered memory regions."""
        info = _ARCH_MAP.get(self.arch_name)
        if info is None:
            raise ValueError(
                f"Unsupported arch for UnicornBackend: {self.arch_name!r}"
            )
        arch_str, mode_str, _, _, _ = info

        if arch_str == "arm":
            uc_arch = unicorn.UC_ARCH_ARM
            uc_mode = (
                unicorn.UC_MODE_THUMB
                if mode_str == "thumb"
                else unicorn.UC_MODE_ARM
            )
        elif arch_str == "arm64":
            uc_arch = unicorn.UC_ARCH_ARM64
            uc_mode = unicorn.UC_MODE_ARM
        elif arch_str == "mips":
            uc_arch = unicorn.UC_ARCH_MIPS
            # MIPS32 big-endian is the default halucinator test firmware mode.
            uc_mode = unicorn.UC_MODE_MIPS32 | unicorn.UC_MODE_BIG_ENDIAN
        elif arch_str == "ppc":
            uc_arch = unicorn.UC_ARCH_PPC
            if mode_str.startswith("ppc64"):
                uc_mode = unicorn.UC_MODE_PPC64 | unicorn.UC_MODE_BIG_ENDIAN
            else:
                uc_mode = unicorn.UC_MODE_PPC32 | unicorn.UC_MODE_BIG_ENDIAN
        else:
            raise ValueError(f"Unsupported arch for UnicornBackend: {arch_str!r}")

        self._uc = unicorn.Uc(uc_arch, uc_mode)
        log.info("Unicorn engine initialised: arch=%s mode=%s", arch_str, mode_str)

        # Cortex-M kernels (Zephyr, FreeRTOS, MCUXpresso) use `msr/mrs` to
        # special-purpose registers (PRIMASK, BASEPRI, FAULTMASK, CONTROL)
        # plus `wfi`/`wfe`/`sev`/`isb`/`dsb`/`dmb` during early boot. The
        # default unicorn ARM CPU is generic ARMv7-A which decodes Thumb-2
        # but not the M-profile system instructions — every PRIMASK write
        # raises UC_ERR_INSN_INVALID before the firmware finishes
        # initialisation. Pin the CPU model to Cortex-M3 so unicorn uses
        # the M-profile decoder.
        if self.arch_name == "cortex-m3":
            try:
                self._uc.ctl_set_cpu_model(arm_const.UC_CPU_ARM_CORTEX_M3)
            except Exception as exc:  # noqa: BLE001
                log.warning(
                    "UnicornBackend: ctl_set_cpu_model(CORTEX_M3) failed (%s)"
                    " — kernel boot may UC_ERR_INSN_INVALID", exc,
                )

        # PPC64 needs MSR.SF=1 so the CPU decodes 64-bit instructions.
        # Without it, any ld/std fires UC_ERR_EXCEPTION immediately.
        if arch_str == "ppc" and mode_str.startswith("ppc64"):
            msr_reg = self._reg_map.get("msr")
            if msr_reg is not None:
                self._uc.reg_write(msr_reg, 1 << 63)

        for region in self._regions:
            self._map_region(region)

        # ARMv7-M private peripheral bus (PPB) — SCS/NVIC/SCB/SysTick/MPU
        # at 0xE0000000–0xE00FFFFF (1 MB). Cortex-M boot code writes VTOR,
        # AIRCR, SHCSR, NVIC enable bits etc. before our intercepts have
        # any chance to run, so we map the PPB as plain RW memory and let
        # the writes succeed silently. Reads return 0, which is safe for
        # status-poll loops on a stubbed peripheral.
        if self.arch_name == "cortex-m3":
            try:
                self._uc.mem_map(0xE0000000, 0x00100000, _PERM_MAP["rw"])
            except Exception as exc:  # noqa: BLE001
                # Already mapped by an explicit config region — fine.
                log.debug(
                    "UnicornBackend: PPB auto-map skipped (%s)", exc,
                )

        # Global hook to detect breakpoint hits and stop execution
        self._uc.hook_add(
            unicorn.UC_HOOK_CODE,
            self._code_hook,
        )
        # Log unmapped / invalid memory accesses so test firmware crashes
        # produce useful diagnostics instead of opaque UC_ERR_* strings.
        self._uc.hook_add(
            unicorn.UC_HOOK_MEM_READ_UNMAPPED
            | unicorn.UC_HOOK_MEM_WRITE_UNMAPPED
            | unicorn.UC_HOOK_MEM_FETCH_UNMAPPED,
            self._invalid_mem_hook,
        )
        # Log CPU exceptions (unhandled traps, illegal insns, FP faults)
        self._uc.hook_add(unicorn.UC_HOOK_INTR, self._intr_hook)

    def _intr_hook(self, uc, intno, user_data):
        try:
            pc = self.read_register("pc")
        except Exception:
            pc = -1
        # On cortex-m3, an ISR returning via `bx lr` jumps to an
        # EXC_RETURN magic value (top nibble 0xF). Unicorn raises an
        # exception here rather than firing the fetch-unmapped hook,
        # so handle it the same way and unwind the synthetic frame.
        if (self.arch_name == "cortex-m3"
                and pc != -1
                and self._maybe_handle_exc_return(pc)):
            return  # _maybe_handle_exc_return already called emu_stop
        # Opt-in recovery: a Thumb SVC (high byte 0xDF) from instrumented
        # firmware (e.g. P2IM aflCall). When the SVC traps, unicorn reports
        # pc at the *next* instruction, so the SVC opcode is at pc or pc-2.
        # We zero the return register and continue without stopping (pc has
        # already advanced past the SVC), rather than aborting the run.
        if self.skip_svc and pc != -1:
            try:
                for probe in (pc - 2, pc):
                    op = bytes(uc.mem_read(probe, 2))
                    if len(op) == 2 and op[1] == 0xDF:  # Thumb SVC
                        # ensure pc is past the SVC, then resume
                        if probe == pc:
                            self.write_register("pc", pc + 2)
                        self.write_register("r0", 0)
                        return
            except Exception:  # noqa: BLE001
                pass
        log.error("UnicornBackend: CPU exception/interrupt %d at pc=0x%x",
                  intno, pc)
        uc.emu_stop()

    def _invalid_mem_hook(self, uc, access, addr, size, value, user_data):
        """Intercept invalid memory accesses. On cortex-m, a fetch from
        an EXC_RETURN magic address is the ISR returning — we unwind
        the pushed exception frame and resume at the saved PC. Other
        invalid accesses are logged and the emulator aborts."""
        if (access == unicorn.UC_MEM_FETCH_UNMAPPED
                and self._maybe_handle_exc_return(addr)):
            return True  # resolved — unicorn will not abort
        try:
            pc = self.read_register("pc")
        except Exception:
            pc = -1
        kind = {
            unicorn.UC_MEM_READ_UNMAPPED: "read",
            unicorn.UC_MEM_WRITE_UNMAPPED: "write",
            unicorn.UC_MEM_FETCH_UNMAPPED: "fetch",
        }.get(access, f"access({access})")
        log.error("UnicornBackend: unmapped %s at 0x%x (size %d, value 0x%x) "
                  "from pc=0x%x", kind, addr, size, value, pc)
        return False  # abort

    def _map_region(self, region: MemoryRegion) -> None:
        perm = _PERM_MAP.get(region.permissions.lower(), 0x7)
        # Unicorn requires page-aligned base + size, and refuses any
        # overlap with an existing mapping. Halucinator configs (and
        # QEMU's configurable machine) freely overlap regions because
        # later mappings override earlier ones in QEMU. To bridge the
        # gap, we map this region only over pages that aren't already
        # mapped by an earlier region in self._regions.
        page = 0x1000
        base = region.base_addr & ~(page - 1)
        end = (region.base_addr + region.size + page - 1) & ~(page - 1)
        # Collect already-mapped page ranges.
        mapped = [
            ((r.base_addr & ~(page - 1)),
             ((r.base_addr + r.size + page - 1) & ~(page - 1)))
            for r in self._regions if r is not region
        ]
        cursor = base
        for lo, hi in sorted(mapped):
            if hi <= cursor or lo >= end:
                continue
            if lo > cursor:
                self._safe_map(cursor, min(lo, end) - cursor, perm, region)
            cursor = max(cursor, hi)
            if cursor >= end:
                break
        if cursor < end:
            self._safe_map(cursor, end - cursor, perm, region)

        if region.file:
            try:
                with open(region.file, "rb") as fh:
                    data = fh.read(region.size)
                self._uc.mem_write(region.base_addr, data)
                log.debug("Loaded %s → 0x%x", region.file, region.base_addr)
            except OSError as exc:
                log.warning("Could not load file %s: %s", region.file, exc)

        # Wire MMIO hooks if provided
        if region.read_hook or region.write_hook:
            hook_type = 0
            if region.read_hook:
                hook_type |= unicorn.UC_HOOK_MEM_READ
            if region.write_hook:
                hook_type |= unicorn.UC_HOOK_MEM_WRITE
            h = self._uc.hook_add(
                hook_type,
                self._make_mmio_hook(region),
                begin=region.base_addr,
                end=region.base_addr + region.size - 1,
            )
            self._mmio_hooks[region.name] = h

    def _safe_map(self, base: int, size: int, perm: int,
                  region: MemoryRegion) -> None:
        """mem_map(base, size, perm) with friendly diagnostics on failure."""
        if size <= 0:
            return
        try:
            self._uc.mem_map(base, size, perm)
        except Exception as exc:  # noqa: BLE001
            log.warning("mem_map 0x%x size 0x%x (for region %s): %s",
                        base, size, region.name, exc)

    def _make_mmio_hook(self, region: MemoryRegion) -> Callable:
        def _hook(uc, access, addr, size, value, user_data):
            offset = addr - region.base_addr
            if access == unicorn.UC_MEM_READ and region.read_hook:
                result = region.read_hook(offset, size)
                if result is not None:
                    data = result.to_bytes(size, "little")
                    uc.mem_write(addr, data)
            elif access == unicorn.UC_MEM_WRITE and region.write_hook:
                region.write_hook(offset, size, value)
        return _hook

    def _code_hook(self, uc, addr: int, size: int, user_data: Any) -> None:
        """Called for every instruction; checks if addr is a breakpoint."""
        # Thumb bit lives in the low bit of PC on 32-bit ARM; for other archs
        # instructions are at least 2-byte aligned so masking bit 0 is a no-op.
        pc = addr & ~1
        if pc in self._breakpoints:
            self._stopped = True
            self._bp_hit_addr = pc
            uc.emu_stop()

    # ------------------------------------------------------------------
    # Memory
    # ------------------------------------------------------------------

    def add_memory_region(self, region: MemoryRegion) -> None:
        self._regions.append(region)
        if self._uc is not None:
            self._map_region(region)

    def read_memory(self, addr: int, size: int, num_words: int = 1,
                    raw: bool = False) -> Union[int, bytes]:
        total = size * num_words
        data = bytes(self._uc.mem_read(addr, total))
        if raw or num_words > 1:
            return data
        if size == 1:
            return data[0]
        order = "big" if self._is_be else "little"
        return int.from_bytes(data[:size], order)

    def write_memory(self, addr: int, size: int,
                     value: Union[int, bytes, bytearray],
                     num_words: int = 1, raw: bool = False) -> bool:
        if isinstance(value, (bytes, bytearray)):
            data = bytes(value)
        else:
            order = "big" if self._is_be else "little"
            data = value.to_bytes(size * num_words, order)
        try:
            self._uc.mem_write(addr, data)
            return True
        except Exception:
            return False

    # ------------------------------------------------------------------
    # Registers
    # ------------------------------------------------------------------

    def read_register(self, register: str) -> int:
        uc_reg = self._reg_map.get(register.lower())
        if uc_reg is None:
            raise ValueError(f"Unknown register: {register!r}")
        return self._uc.reg_read(uc_reg)

    def write_register(self, register: str, value: int) -> None:
        uc_reg = self._reg_map.get(register.lower())
        if uc_reg is None:
            raise ValueError(f"Unknown register: {register!r}")
        self._uc.reg_write(uc_reg, value)

    # ------------------------------------------------------------------
    # Execution control
    # ------------------------------------------------------------------

    def set_breakpoint(self, addr: int, hardware: bool = False,
                       temporary: bool = False) -> int:
        bp_id = self._next_bp_id
        self._next_bp_id += 1
        # Store with Thumb bit cleared for comparison in _code_hook
        self._breakpoints[addr & 0xFFFFFFFE] = bp_id
        return bp_id

    def remove_breakpoint(self, bp_id: int) -> None:
        to_remove = [a for a, bid in self._breakpoints.items() if bid == bp_id]
        for addr in to_remove:
            del self._breakpoints[addr]

    def set_watchpoint(self, addr: int, write: bool = True,
                       read: bool = False, size: int = 4) -> int:
        """Install a per-address memory-access hook. Fires emu_stop when
        the firmware reads/writes the watched byte range."""
        if self._uc is None:
            raise RuntimeError("Call UnicornBackend.init() first")
        hook_type = 0
        if read:
            hook_type |= unicorn.UC_HOOK_MEM_READ
        if write:
            hook_type |= unicorn.UC_HOOK_MEM_WRITE
        if hook_type == 0:
            raise ValueError("watchpoint must have read or write enabled")

        bp_id = self._next_bp_id
        self._next_bp_id += 1

        def _watch_hook(uc, access, watch_addr, watch_size, value, user_data):
            # UC_HOOK_MEM_* already filters by the range we registered on,
            # so any call here is a hit.
            self._stopped = True
            self._bp_hit_addr = watch_addr
            uc.emu_stop()

        handle = self._uc.hook_add(
            hook_type, _watch_hook,
            begin=addr, end=addr + size - 1,
        )
        # Reuse _bp_hooks storage — (address, hook handle) is enough to
        # remove it later.
        self._bp_hooks[bp_id] = (addr, handle)
        return bp_id

    def remove_watchpoint(self, bp_id: int) -> None:
        entry = self._bp_hooks.pop(bp_id, None)
        if entry is None:
            return
        _, handle = entry
        if self._uc is not None:
            try:
                self._uc.hook_del(handle)
            except Exception:  # noqa: BLE001
                pass

    def cont(self, blocking: bool = True) -> None:
        if self._uc is None:
            raise RuntimeError("Call UnicornBackend.init() first")
        self._stopped = False
        self._bp_hit_addr = None
        until = (1 << (self._word_size * 8)) - 1
        # Loop over emu_start so an emu_stop triggered by inject_irq
        # from another thread doesn't bubble out to the dispatch loop.
        # We only return when a real breakpoint hook fires
        # (self._stopped sticks True) or stop() is called externally.
        while True:
            # Drain any IRQs queued from another thread before
            # resuming — the synthetic exception frame setup mutates
            # PC/SP, only safe when emu_start is not running.
            while self._pending_irqs:
                self._apply_pending_irq(self._pending_irqs.pop(0))
            pc = self.read_register("pc")
            # Unicorn Thumb mode needs the LSB set on the start
            # address.
            start = (pc | 1) if self._is_thumb else pc
            try:
                self._uc.emu_start(start, until, timeout=0, count=0)
            except unicorn.UcError:
                if self._stopped:
                    return  # stopped by breakpoint hook — normal
                # emu_stop without a breakpoint hook firing: either
                # inject_irq queued an IRQ on another thread, or
                # something asked us to stop. If the former, loop and
                # apply the IRQ. Otherwise honour the stop.
                if not self._pending_irqs:
                    raise
                # fall through to drain queue + re-enter emu_start
                continue
            # emu_start returned without UcError: same logic as
            # above — drain pending or honour external stop.
            if self._pending_irqs:
                continue
            return

    def stop(self) -> None:
        self._stopped = True
        if self._uc is not None:
            self._uc.emu_stop()

    def step(self) -> None:
        if self._uc is None:
            raise RuntimeError("Call UnicornBackend.init() first")
        pc = self.read_register("pc")
        start = (pc | 1) if self._is_thumb else pc
        until = (1 << (self._word_size * 8)) - 1
        self._uc.emu_start(start, until, timeout=0, count=1)

    # ------------------------------------------------------------------
    # IRQ injection — not supported in-process; log warning
    # ------------------------------------------------------------------

    # ARM-v7M exception-return magic values. When the ISR issues `bx lr`
    # with LR holding one of these, cortex-m normally pops the exception
    # frame and resumes. Unicorn doesn't model that transition, so we
    # catch the invalid fetch and unwind manually.
    _EXC_RETURN_THREAD_MSP = 0xFFFFFFF9
    _EXC_RETURN_MASK = 0xFFFFFFF0
    _EXC_RETURN_MAGIC = 0xFFFFFFF0  # any PC matching this top nibble is
                                     # an exception-return attempt

    def inject_irq(self, irq_num: int) -> None:
        """Deliver an external IRQ.

        Cortex-M3 / ARMv7-A fast-path: queue the IRQ for the dispatch
        loop, then call ``emu_stop`` to break out of any in-flight
        ``emu_start``. cont() drains the queue (synthesises the
        exception entry on the main stack, sets banked LR_irq, jumps
        PC to the architectural IRQ vector) immediately before
        re-entering ``emu_start`` so all CPU-state mutation happens
        single-threaded. Skips controller-MMIO writes — unicorn
        doesn't model the NVIC or GIC.

        For other arches, fall through to HalBackend.inject_irq, which
        routes through the configured IrqController (CP0 Cause for
        MIPS, OpenPIC IPIDR for PPC). MMIO writes go through unicorn's
        normal write_memory and the next cont() will take the
        exception when the firmware unmasks.
        """
        if self.arch_name not in ("cortex-m3", "arm", "arm64", "mips",
                                   "powerpc", "powerpc:MPC8XX", "ppc64"):
            super().inject_irq(irq_num)
            return
        if self._uc is None:
            raise RuntimeError("Call UnicornBackend.init() first")
        # On arm/arm64, the IrqController MMIO write (GICD_ISPENDR
        # for arm/arm64, NVIC_ISPR for cortex-m3) is still useful —
        # firmware that polls those registers should see the bit
        # set. Cortex-m3's _apply_pending_irq always synthesises the
        # exception, so skip the controller MMIO there. For arm /
        # arm64 we emit both: real GIC writes happen through the
        # controller, and the synthetic exception entry fires from
        # cont().
        if self.arch_name in ("arm", "arm64", "mips",
                               "powerpc", "powerpc:MPC8XX", "ppc64"):
            ctrl = getattr(self, "_irq_controller", None)
            if ctrl is None:
                from halucinator.backends.irq import IrqConfigError
                raise IrqConfigError(
                    f"UnicornBackend(arch={self.arch_name!r}) has no "
                    "interrupt controller configured. Set "
                    "machine.interrupt_controller in the YAML or call "
                    "set_irq_controller() before inject_irq()."
                )
            try:
                ctrl.trigger(self, irq_num)
            except Exception as exc:  # noqa: BLE001
                # MIPS: the controller does an RMW on CP0 'cause'
                # which unicorn doesn't expose. Swallow the
                # register-not-found error (the synthetic entry
                # below still delivers) but let bounds and other
                # config errors surface.
                if self.arch_name == "mips" and "cause" in str(exc):
                    pass
                else:
                    raise
        # Cross-thread safe: list.append() + emu_stop are atomic from
        # Python's perspective. The dispatch thread will see the
        # pending entry on its next cont() call.
        self._pending_irqs.append(int(irq_num))
        try:
            self._uc.emu_stop()
        except Exception:  # noqa: BLE001 — uc raises if not running
            pass

    def _apply_pending_irq(self, irq_num: int) -> None:
        """Set up the synthetic exception entry for a pended IRQ.
        Must run on the dispatch thread (between emu_start chunks)
        — Unicorn isn't safe against PC/SP writes mid-run."""
        if self._uc is None:
            return
        if self.arch_name == "arm":
            self._apply_pending_irq_armv7a(irq_num)
            return
        if self.arch_name == "arm64":
            self._apply_pending_irq_arm64(irq_num)
            return
        if self.arch_name == "mips":
            self._apply_pending_irq_mips(irq_num)
            return
        if self.arch_name in ("powerpc", "powerpc:MPC8XX", "ppc64"):
            self._apply_pending_irq_ppc(irq_num)
            return

        # Vector table offset: caller plumbs it in via set_vtor(); fall
        # back to 0 for backward compatibility.
        vtor = getattr(self, "_vtor", 0)
        isr_slot = vtor + (16 + irq_num) * 4
        isr_addr = 0
        try:
            isr_addr = int.from_bytes(
                self._uc.mem_read(isr_slot, 4), "little"
            )
        except Exception:  # noqa: BLE001 — Unicorn raises UcError here
            pass
        if not isr_addr:
            log.warning("inject_irq(%d): vector table slot 0x%x is zero or "
                        "unmapped; no handler installed", irq_num, isr_slot)
            return

        # Push the 8-word exception frame.
        regs = {name: self.read_register(name) for name in
                ("r0", "r1", "r2", "r3", "r12", "lr", "pc", "cpsr")}
        sp = self.read_register("sp") - 32
        frame = (regs["r0"], regs["r1"], regs["r2"], regs["r3"],
                 regs["r12"], regs["lr"], regs["pc"], regs["cpsr"])
        import struct
        self._uc.mem_write(sp, struct.pack("<8I", *frame))
        self.write_register("sp", sp)
        self.write_register("lr", self._EXC_RETURN_THREAD_MSP)
        self.write_register("pc", isr_addr & ~1)  # Thumb bit goes in CPSR.T
        log.info("inject_irq(%d): entering ISR @ 0x%x (vector 0x%x)",
                 irq_num, isr_addr, isr_slot)

    def set_vtor(self, vtor: int) -> None:
        """Remember the vector-table base so inject_irq can find ISRs."""
        self._vtor = vtor

    # ARMv7-A CPSR mode bits.
    _ARM_MODE_USER = 0x10
    _ARM_MODE_FIQ  = 0x11
    _ARM_MODE_IRQ  = 0x12
    _ARM_MODE_SVC  = 0x13
    _ARM_MODE_ABT  = 0x17
    _ARM_MODE_UND  = 0x1B
    _ARM_MODE_SYS  = 0x1F
    _ARM_MODE_MASK = 0x1F
    _ARM_CPSR_I    = 0x80   # IRQ mask
    _ARM_CPSR_T    = 0x20   # Thumb

    def _apply_pending_irq_armv7a(self, irq_num: int) -> None:
        """Synthesise an ARMv7-A IRQ exception entry.

        Per ARMv7-A architecture (B1.8.3 Exception entry):
          R14_irq  = PC (return + correction)
          SPSR_irq = CPSR
          CPSR.M   = 0b10010 (IRQ mode)
          CPSR.I   = 1        (mask further IRQs)
          CPSR.T   = 0        (ARM state)
          PC       = vbar + 0x18

        The IRQ exception's standard return-address correction is
        ``LR -= 4`` in the handler before ``subs pc, lr, #4``. Our
        firmware's _irq_entry stub does exactly this; we therefore
        pass the *next* instruction's PC into LR_irq. The ISR's
        ``movs pc, lr`` then restores CPSR from SPSR_irq and resumes.
        """
        # Snapshot pre-IRQ state.
        cpsr = self.read_register("cpsr")
        if cpsr & self._ARM_CPSR_I:
            # IRQs masked — re-queue and let the firmware unmask
            # itself; otherwise we'd nest exceptions.
            self._pending_irqs.insert(0, irq_num)
            self._uc.emu_stop()
            return
        pc = self.read_register("pc")
        # The next-instruction PC. ARMv7-A IRQ entry sets LR_irq to
        # PC+4 in ARM state; the handler then subtracts 4 to get back
        # to the interrupted instruction.
        return_pc = pc + 4

        # Switch CPSR to IRQ mode. Writing CPSR auto-banks SP/LR/SPSR.
        new_cpsr = cpsr & ~(self._ARM_MODE_MASK | self._ARM_CPSR_T)
        new_cpsr |= self._ARM_MODE_IRQ | self._ARM_CPSR_I
        self.write_register("cpsr", new_cpsr)

        # Now in IRQ-banked LR/SPSR.
        self.write_register("lr", return_pc)
        self.write_register("spsr", cpsr)

        # Stash the acknowledged IRQ ID into GICC_IAR if the
        # configured GicController carries a gicc_base. Real GIC
        # hardware exposes this via the CPU interface; without a
        # hardware model the firmware's MMIO read otherwise comes
        # back as zero-initialised memory.
        ctrl = getattr(self, "_irq_controller", None)
        gicc_base = getattr(ctrl, "gicc_base", None) if ctrl else None
        if gicc_base is not None:
            try:
                self._uc.mem_write(
                    gicc_base + 0x0C,
                    int(irq_num).to_bytes(4, "little"),
                )
            except Exception:  # noqa: BLE001
                pass

        vbar = getattr(self, "_vtor", 0)
        self.write_register("pc", vbar + 0x18)
        log.info("inject_irq(%d): ARMv7-A entry @ 0x%x, return=0x%x",
                 irq_num, vbar + 0x18, return_pc)

    def _apply_pending_irq_arm64(self, irq_num: int) -> None:
        """Synthesise an AArch64 IRQ entry for in-process unicorn.

        Unicorn's ARM64 model doesn't fully implement EL1 vector
        delivery + ERET. Instead, the firmware exposes a plain
        ``_irq_entry_simple`` trampoline that follows AAPCS: receives
        LR = interrupted PC, calls IRQ_Handler, returns via plain
        ``ret``. The IrqController carries the trampoline address
        as ``irq_simple_entry``; if that's not set we fall back to
        VBAR_EL1 + 0x280 which assumes a real CPU exception model.
        """
        ctrl = getattr(self, "_irq_controller", None)
        gicc_base = getattr(ctrl, "gicc_base", None) if ctrl else None
        irq_simple = (getattr(ctrl, "irq_simple_entry", None)
                      if ctrl else None)

        # Stash the IRQ ID into GICC_IAR shadow.
        if gicc_base is not None:
            try:
                self._uc.mem_write(
                    gicc_base + 0x0C,
                    int(irq_num).to_bytes(4, "little"),
                )
            except Exception:  # noqa: BLE001
                pass

        if irq_simple is not None:
            # AAPCS-style trampoline: LR = return PC, jump to entry.
            return_pc = self.read_register("pc")
            self.write_register("lr", return_pc)
            self.write_register("pc", int(irq_simple))
            log.info(
                "inject_irq(%d): AArch64 trampoline @ 0x%x, return=0x%x",
                irq_num, irq_simple, return_pc,
            )
            return

        # Fallback: try the real-CPU vector path. Unlikely to work
        # under unicorn but keep it as a documented hook.
        try:
            vbar = self.read_register("vbar_el1")
        except Exception:  # noqa: BLE001
            vbar = getattr(self, "_vtor", 0)
        return_pc = self.read_register("pc")
        try:
            self.write_register("elr_el1", return_pc)
        except Exception:  # noqa: BLE001
            pass
        self.write_register("pc", vbar + 0x280)
        log.warning(
            "inject_irq(%d): AArch64 vector entry at 0x%x — Unicorn "
            "may not honour ERET on return", irq_num, vbar + 0x280,
        )

    def _apply_pending_irq_mips(self, irq_num: int) -> None:
        """Deliver a MIPS IRQ to the running firmware.

        Unicorn's MIPS model doesn't take CP0 exceptions via the
        EBase + 0x180 vector, and several variants of synthetic
        function-call trampolines proved unreliable across
        emu_start re-entry. Instead, write the post-ack state
        (irq_fired flag + irq_number) directly to the firmware's
        well-known globals; main's polling loop sees the change on
        its next iteration with no ISR ever running. The
        IrqController carries the global addresses as
        ``irq_fired_addr`` / ``irq_number_addr``.
        """
        ctrl = getattr(self, "_irq_controller", None)
        if ctrl is None:
            return
        irq_number_addr = getattr(ctrl, "irq_number_addr", None)
        irq_fired_addr = getattr(ctrl, "irq_fired_addr", None)
        if irq_number_addr is None or irq_fired_addr is None:
            log.warning(
                "inject_irq(%d): mips controller has no "
                "irq_fired_addr/irq_number_addr — IRQ will not be "
                "delivered to the firmware", irq_num)
            return
        try:
            self._uc.mem_write(int(irq_number_addr),
                               int(irq_num).to_bytes(4, "big"))
            self._uc.mem_write(int(irq_fired_addr),
                               (1).to_bytes(4, "big"))
            log.info("inject_irq(%d): MIPS shadow write -> "
                     "irq_number@0x%x irq_fired@0x%x",
                     irq_num, irq_number_addr, irq_fired_addr)
        except Exception as exc:  # noqa: BLE001
            log.warning("inject_irq(%d): MIPS shadow write failed: %r",
                        irq_num, exc)

    def _apply_pending_irq_ppc(self, irq_num: int) -> None:
        """Deliver a PowerPC IRQ to the running firmware via shadow
        write — same pattern as MIPS. Unicorn doesn't model the
        OpenPIC and PPC exception entry through SRR0/SRR1 reliably
        for our use-case."""
        ctrl = getattr(self, "_irq_controller", None)
        if ctrl is None:
            return
        irq_number_addr = getattr(ctrl, "irq_number_addr", None)
        irq_fired_addr = getattr(ctrl, "irq_fired_addr", None)
        if irq_number_addr is None or irq_fired_addr is None:
            log.warning(
                "inject_irq(%d): ppc controller has no "
                "irq_fired_addr/irq_number_addr — IRQ will not be "
                "delivered to the firmware", irq_num)
            return
        try:
            self._uc.mem_write(int(irq_number_addr),
                               int(irq_num).to_bytes(4, "big"))
            self._uc.mem_write(int(irq_fired_addr),
                               (1).to_bytes(4, "big"))
            log.info("inject_irq(%d): PPC shadow write -> "
                     "irq_number@0x%x irq_fired@0x%x",
                     irq_num, irq_number_addr, irq_fired_addr)
        except Exception as exc:  # noqa: BLE001
            log.warning("inject_irq(%d): PPC shadow write failed: %r",
                        irq_num, exc)

    def _maybe_handle_exc_return(self, addr: int) -> bool:
        """Called from the invalid-fetch hook. If the fetch address looks
        like an EXC_RETURN magic value, pop the exception frame and
        restore pre-interrupt state. Returns True when handled."""
        if self.arch_name != "cortex-m3":
            return False
        if (addr & self._EXC_RETURN_MASK) != self._EXC_RETURN_MAGIC:
            return False
        import struct
        sp = self.read_register("sp")
        try:
            frame = struct.unpack("<8I", bytes(self._uc.mem_read(sp, 32)))
        except Exception:
            return False
        self.write_register("r0", frame[0])
        self.write_register("r1", frame[1])
        self.write_register("r2", frame[2])
        self.write_register("r3", frame[3])
        self.write_register("r12", frame[4])
        self.write_register("lr", frame[5])
        self.write_register("pc", frame[6])
        self.write_register("cpsr", frame[7])
        self.write_register("sp", sp + 32)
        log.info("exc_return: popped frame, resuming at 0x%x", frame[6])
        # Unicorn needs to restart from the restored PC; stop the current
        # emu_start so our dispatch loop re-issues cont() at the new PC.
        self._uc.emu_stop()
        return True

    # ------------------------------------------------------------------
    # Shutdown
    # ------------------------------------------------------------------

    def shutdown(self) -> None:
        if self._uc is not None:
            try:
                self._uc.emu_stop()
            except Exception:
                pass
            self._uc = None
