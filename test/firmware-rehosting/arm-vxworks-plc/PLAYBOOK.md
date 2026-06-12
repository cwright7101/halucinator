# Firmware Re-Hosting Playbook (HALucinator) — general method, with a deep VxWorks track

A field guide for taking an opaque firmware blob from "won't boot in an emulator"
to "runs its real application and a real client talks to it." Written from the
end-to-end re-host of an **ARM / VxWorks 6.4 / AT91RM9200 PLC** whose
**Modbus/UMAS :502 server now answers a real client** (Read Device ID returns the
device's product name + firmware version; UMAS responds). The *method* is
firmware-agnostic; the **VxWorks** sections capture what that OS specifically needs.

> Audience: a future agent or engineer doing the next re-host. Read §1–§3 for the
> method, §4 for the toolbox, §5 to classify a stall, §6 for VxWorks specifics,
> §7 for the worked example, §8 for the hard-won lessons.

---

## 1. Mental model

A re-host is **the firmware running unmodified against models of the hardware it
expects**. You are not patching the firmware; you are supplying — lazily, only
where it actually looks — believable answers for the peripherals, interrupts,
clock, and (eventually) the network that aren't there.

**The bare-march philosophy (the only approach that scales):** start with *real
RAM only* and the reset vector. Run. At the **first fault or hang**, add the
**minimal** model that gets past it — a memory window, a peripheral read value, a
skipped driver, a clock tick — then run again. Repeat. Every model is justified
by a concrete failure you observed, never by speculation. This converges; "build
a faithful full SoC model up front" does not.

**Two failure shapes, and you must tell them apart (see §5):**
- **Fault** — the CPU can't continue (unmapped access, undefined instruction,
  data/prefetch abort). Loud, with a PC and an address.
- **Hang** — the CPU runs forever making no progress. Either a **busy-spin**
  (one hot PC window: a poll loop on a status bit that never flips) or a
  **pend** (the kernel parked a task on a semaphore/event that nothing will
  ever give — the CPU idles in the scheduler).

Each gate you clear reveals the next. The whole job is: **observe → classify →
locate the gate → model the smallest thing → re-run.**

### 1.1 How this method was arrived at (and what it replaced)

The target went through four eras; understand the arc so you don't repeat the
abandoned ones:
- **Era 1 — fabrication tower** (`arm-vxworks-plc_auto_config.yaml`, ~92 intercepts):
  hand-built kernel/C++ state to fake past a wall — `ScratchAlloc` replacing
  `memPartAlloc` wholesale, `FixupTaskSP`, a synthetic round-robin scheduler, a
  fake object pool, 21-entry vtable seeds, forced ctor/task bootstraps. It
  produced an observable "steady state" but the firmware's OWN scheduler never
  ran. **It was all masking one bug.**
- **Era 2 — minimal reframe** (~13–15 intercepts): replace as little as possible,
  model only at real HW seams; every Era-1 intercept classified KEEP/REMOVE
  (`INTERCEPT_AUDIT.md`, see §5.1).
- **Era 3 — bare-march**: start BARE (no intercepts, real RAM only), run, add the
  minimal model at each first fault. This disciplined re-derivation exposed the
  real root cause — the **wrong load base** — which the fabrication tower had been
  papering over.
- **Era 4 — rebased natural boot** (`arm-vxworks-plc_config.yaml`): bare-march on the
  CORRECT base → full multitasking VxWorks, ~14 real tasks, **no fabrication**.

**The lesson that governs everything below:** over-replacement masks single bugs.
The entire tower — and the earlier "irreducible C++ construction wall" conclusion
— were artifacts of the load-base error. When you find yourself inventing kernel
state the firmware should build itself, stop and look for the one upstream bug.

---

## 2. The core diagnostic loop

```
        ┌─────────────────────────────────────────────┐
        │ 1. RUN to the current frontier               │
        │ 2. CLASSIFY: fault | busy-spin | pend        │
        │ 3. LOCATE the gate (the exact fn/instruction │
        │    and WHY it blocks)                         │
        │ 4. MODEL the minimum (a bp_handler / a memory │
        │    window / a peripheral value / a clock)     │
        │ 5. VERIFY it advanced; capture the NEW gate   │
        └───────────────┬─────────────────────────────┘
                        └────────── repeat ───────────►
```

**Visibility is everything.** Before you can classify anything you need to *see*
where the firmware is. In order of preference:
- **Symbols** (§6.2). On VxWorks, recover the in-image symbol table first — it
  turns `FUN_2003a85c` into `XbMgr::runStateCold`. This single step is worth more
  than any other.
- **A logging intercept on the firmware's own logger** (VxWorks `logMsg`,
  `printf`, a custom trace fn) → you read the boot narrative the firmware emits.
- **Reached-traces**: plant `LogAndContinue` on a set of candidate functions; the
  last one logged is your frontier. Cheap, and immune to the clock-storm problem
  below.
- **PC histogram** (`HAL_PC_SAMPLE=1`, or a bounded `UC_HOOK_CODE` sampler): the
  hottest PC window *is* a busy-spin. **Caveat:** once a fast periodic timer IRQ
  is running, the idle scheduler (`reschedule`) dominates any per-instruction
  sampler and the histogram lies — switch to Reached-traces for pends.
- **Call trace** (`HAL_CALL_TRACE=<path>`): records `bl` edges to reconstruct
  reachability without a debugger.

**Bound every run.** Emulation is far slower than real time; a hung firmware will
run "forever." Use a watchdog (a wall-clock timer that `os._exit()`s) and/or a
`faulthandler` dump. The repo's `run_cfg.py` (`RUN_CFGS=`, `VERIFY_SECS=`) is the
pattern.

**Always kill stray runs between iterations.** Leftover background emulator
processes steal CPU and *quietly* make boots look 10× slower than they are — a
real time-sink we hit. `pkill -9 -f run_cfg` (or your runner) before each run.

**Trust your faults — cross-validate before modeling past one.** Before spending
hours modeling around a crash, confirm it's a real firmware issue and not a
CPU-model quirk of one emulator. Run the same bare boot under **both unicorn and
avatar-qemu**: on the target they were instruction-for-instruction identical through
the reset stub, AIC init, and into the first crash; the only divergence was
post-fault (unicorn halts on `pc=0`, qemu slides through zeroed RAM). That
agreement is your license to iterate fast in the in-process unicorn backend and
only re-confirm true anomalies in qemu. (Keep a single-step qemu trace —
`-d in_asm,exec,cpu` — for instruction-level correlation in Ghidra.)

---

## 3. Setup & prerequisites

**Config skeleton** (`-c file.yaml`, multiple `-c` allowed; later files win):

```yaml
machine:
  arch: arm
  cpu_model: arm                 # see HAL_ARM_CPU_MODEL for the real core
  entry_addr: 0x20010184         # reset vector (often file-offset + load base)
  init_sp: 0x00203ff0
  interrupt_controller:          # how injected IRQs enter the CPU (see §4.4)
    type: arm_vic                # arm_vic | gicv2/gicv3 | cortex_m | mips | x86_pic
    options: { vector_base: 0x0 }

memories:
  rom_or_sdram:                  # the image, at its TRUE link base
    base_addr: 0x20010000
    file: FIRMWARE.bin
    permissions: rwx
    size: 0x03ff0000
  # ...low RAM, reserved windows, mirror banks...

peripherals:                     # MMIO windows that need behavior, not just RAM
  sysctrl:
    base_addr: 0xffff0000
    emulate: At91SysCtrl         # a peripheral_models class (§4.3)
    size: 0x00010000

intercepts:                      # bp_handlers keyed to addresses (the workhorse)
  - class: halucinator.bp_handlers.SkipFunc
    function: some_blocking_init
    addr: 0x202bff80
```

**Three load-base truths that bit us hard (check these first):**
1. **The link base is not always 0.** The target links at `0x20010000`; we mapped it
   `0x10000` low and *every absolute pointer* read garbage. The reset stub is
   PC-relative so it "ran fine" until the first absolute deref — which masqueraded
   as a code bug for a long time. **If early-boot dies at the first pointer
   dereference, suspect the load base.** A quick check: do code-pointer literals in
   the image land on real function prologues at your assumed base?
2. **Reserved low memory.** Firmware often sits *above* a reserved region (ARM
   vectors / OS low globals). Map that region too (RAM), or absolute low-global
   access faults.
3. **Mirror/aliased banks.** SoCs alias SDRAM/SRAM at multiple addresses; map the
   aliases the firmware actually uses.

**How to FIND the base of a headerless blob (two converging methods):**
- **Pointer-word histogram.** Treat every 32-bit word as a candidate pointer and
  histogram those that fall inside plausible RAM ranges. The base is where the
  mass lands: on the target, 83k words fell inside the image extent and almost none
  above it, pointing at the SDRAM base; the handful beyond the image end are
  `.bss` globals (which confirms the upper bound). *Caveat:* this got the target
  *close* but the true link base was 64 KB higher — so cross-check.
- **Boot-stub absolute literals.** The reset stub loads absolute values from its
  PC-relative literal pool: a bootstrap SP (`0x00203ff0`), a peripheral base it
  pokes (`ldr r2,…→0xfffff000`, then writes the AIC/system-controller regs at
  `+0x124/+0x128/+0x130`), and global pointers that sit just past the image end
  (where `.bss` lives). These are absolute, not base-relative, so they pin the
  map directly. **Verify the base independently** — a 64 KB error mimics a hundred
  code bugs *and* corrupts symbol recovery (see §6.2).

**`cpu_model`.** Unicorn's default ARM core may not implement the CP15/MMU/
privileged ops your firmware uses → `UC_ERR_INSN_INVALID`. Set the real core
(`HAL_ARM_CPU_MODEL=UC_CPU_ARM_926`, etc.).

**Run command** (in-process unicorn backend, the fast path):
```
HAL_MMU_FLAT_FALLBACK=1 HAL_IRQ_CHUNK=8000 python3 -c \
  "import sys; sys.argv=['hal','-c','cfg.yaml','-s','syms.csv','--emulator','unicorn']; \
   from halucinator import main; main.main()"
```

---

## 4. The toolbox

### 4.1 Breakpoint handlers (`intercepts:` → `class: halucinator.bp_handlers.<Name>`)

A handler fires when PC reaches `addr`. **The return contract is the thing to
internalize** (ARM; `intercepts.interceptor()` + `qemu_targets/arm_qemu.py`):

| handler returns | effect |
|---|---|
| `(True, value)` | **skip** the real fn: `execute_return(value)` → `r0 = value & 0xFFFFFFFF`, then `pc = lr` |
| `(True, None)`  | skip, **void**: `r0` untouched, `pc = lr` (the `SkipFunc` idiom) |
| `(False, x)`    | `x` ignored, **no return** — execution continues from current PC/regs (observe, or *patch-then-run*) |

To **redirect control flow**, a `(False, …)` handler writes `pc` itself first
(this is how `SetRegisters {pc: …}` jumps, and how the bridges call a firmware fn
by setting `r0..r3`, `lr`, `pc` then returning `False`).

**The handlers you'll use constantly** (37 exist; these are the core):

*Stubs / return-fakers* — "this call can't run; answer for it":
- **`SkipFunc`** — return void (`pc=lr`, `r0` intact). The default for a blocking
  or unimplementable routine whose caller ignores the result. *(NAND init, an
  SD probe, a diagnostic trace, a slow `.bss` memset, a deadlocking mutex.)*
- **`ReturnZero`** / **`ReturnConstant {ret_value}`** — return `0` / a fixed magic
  value (chip ID, "ready" status, capability mask) so the caller takes the path
  you want.
- **`IncrementingReturn {step, mask}`** — return a monotonically increasing value
  each call. Models a **free-running counter/timer** whose backing store doesn't
  tick in the rehost, so elapsed-time/timeout loops actually complete.

*State patchers* — "edit memory/regs, then let the real code run" (`False`):
- **`SetRegisters {registers:{r2:1, pc:0x…}}`** — overwrite registers (incl. `pc`)
  then continue. Force a branch by patching the compared register; redirect flow
  by setting `pc`. The general "edit CPU state" primitive.
- **`SetMemory {addresses:{0xADDR:val}}`** / **`ForceMemValue {target_addr,value,
  size}`** — write a **fixed** global (a "device present" flag, a config word, a
  stale `_func_` hook pointer to null) when a PC is reached.
- **`RegMemWrite {reg, offset, value, size}`** — write to **`[reg+offset]`**, the
  address computed from a *live* register at hit time. Use to poke a field of a
  `this`/`r4` object (e.g. instantly ACK a poll: `[r4+0x3e]=3`; mark a phantom
  device absent: `[r0+0x21c]=0xff`). The dynamic-address counterpart to SetMemory.
- **`MovePC {move_by}`** — step over a single offending instruction mid-function
  (an unsupported CP15 op, a `wfi`, a hardware poll) without unwinding the call.

*Observers* — "watch, don't change" (`False`, logging only):
- **`LogAndContinue {max_logs}`** — log entry (PC, lr, regs) and run normally. The
  Reached-trace workhorse for locating a frontier.
- **`PrintString {arg_num}`** / **`PrintChar`** — surface a firmware logger's
  messages; `intercept:false` keeps the real logger running too.
- **`DumpMemory`**, **`ArgumentLogger`**, **`Counter`** — forensics.

*Control / lifecycle:*
- **`CallFunction`** — call a firmware function from the host (stage args, set lr,
  jump). The mechanism behind the bridges.
- **`KillExit {exit_code}`** — cleanly stop the run at a terminal/marker PC
  (great for "assert boot reached milestone X" harnesses).
- **`Timer`** — a free-running counter delay primitive so HW busy-waits terminate.

*Bridges (application-layer connectivity):*
- **`SocketBridge`** — host TCP server ⇄ firmware BSD socket syscalls (§6.5). The
  most faithful "real client talks to the firmware's real server" path; no TAP.
- **`ModbusTcpBridge`** — a higher, app-layer alternative (host :502 → call a
  firmware Modbus handler directly, bypassing the stack).

### 4.2 Writing a custom bp_handler

When no built-in fits (we wrote `RegMemWrite`, `IncrementingReturn`, and
`SocketBridge` this way), subclass `BPHandler`:

```python
class MyHandler(BPHandler):
    def __init__(self): self.cfg = {}
    def register_handler(self, qemu, addr, func_name, **registration_args):
        self.cfg[addr] = registration_args        # YAML registration_args -> kwargs
        return cast(HandlerFunction, MyHandler.my_method)   # the dispatched method
    @bp_handler
    def my_method(self, qemu, addr):
        # read args/mem/regs, decide, return (intercept, value)
        return True, 0
```

- `register_handler`'s kwargs **are** the YAML `registration_args` keys (with
  defaults). Store per-`addr` state in dicts (this is how one class handles many
  addresses and returns different values per call).
- **One instance per class**, cached: every `class: …MyHandler` entry shares one
  object — so a handler can own cross-address state (the `SocketBridge` owns
  select+accept+recv+send together this way).
- **Backend API a handler calls** (`qemu` == the backend):
  `get_arg(n)` (ARM: r0–r3 then stack), `read_register/write_register(name,val)`,
  `read_memory(addr,size)` / `write_memory(addr,size,val)` /
  `read_memory_bytes(addr,n)` / `write_memory_bytes(addr,buf)`, `read_string`,
  `get_ret_addr()` (=lr), `execute_return(val)` (r0=val, pc=lr — normally let the
  dispatcher call it via `return True,val`).
- **Threading rule (load-bearing):** the emulator is a *single* dispatch thread.
  A handler may **never** be called from a background thread, and a handler must
  **not block** the emu thread (no sleeps / blocking socket I/O) — that freezes
  timer-IRQ delivery and can deadlock. Background work (a host socket server) runs
  on its own thread touching **only plain-Python state under a lock**; the handler
  reads that state when its bp fires. (See `SocketBridge` / `modbus_tcp_bridge.py`.)

### 4.3 Peripheral models (`peripherals:` → `emulate: <Class>`)

MMIO windows that need *behavior*, not just backing RAM. `hw_read(offset,size,pc)`
/ `hw_write(...)`. ~25 exist; the ones that matter:
- **`GenericPeripheral`** — returns 0 for every read, swallows writes, records the
  access. The default "absorb this MMIO window." **Pitfall:** default-0 reads
  silently send the firmware down wrong branches — if a peripheral read gates a
  decision, model the *value*, don't return 0.
- **`AutoPeripheral` / `RecordingPeripheral`** — record all MMIO to an SQLite
  trace; `AutoPeripheral` also auto-advances free-running-counter registers
  (`HAL_AUTO_COUNTER_ADDRS`) and breaks uEmu-style busy-waits. Use to *discover*
  which registers the firmware reads and when.
- **`At91SysCtrl`**, **`At91Emac`**, **`At91Dbgu`** — worked AT91RM9200 models
  (system-controller PIT status, EMAC/PHY link-up, DBGU TXRDY). Patterns to copy
  for your SoC: a `GenericPeripheral` subclass overriding a few register reads.
- **`EthernetModel`/`EthernetInterface`**, **`UARTPublisher`**, **`GPIO`**,
  **`SDCardModel`**, **`HostFSModel`/`DosFsModel`**, **`ADC`**, **`SPIPublisher`**,
  **`IEEE802_15_4`** — ZMQ-registered I/O models you bridge to the host.

### 4.4 Interrupts, the clock, and exception delivery

Two independent axes (`backends/irq/`):
1. **Make the line pending** — `IrqController`: `cortex_m` (NVIC), `gicv2/gicv3`
   (needs `gicd_base`), **`arm_vic`** (synthesizes the A-profile IRQ entry for
   SoCs unicorn doesn't model — what the target uses), `mips`, `openpic`, `x86_pic`.
2. **How the CPU enters the handler** — `ExceptionDeliverer` + `DeliveryModel`:
   **FRAME** (build the real architectural exception frame, vector to
   `vbar+0x18`), **TRAMPOLINE** (AAPCS call into a firmware stub), **SHADOW**
   (just set the post-ack globals the firmware polls — mips/ppc).

**The system clock is usually the single most important peripheral** — without
ticks, `taskDelay`/timeouts/periodic work never fire and the whole app idles.
The plumbing: `TimerModel` (a daemon thread firing an IRQ at a rate) +
`Interrupts` model + the OS clock-connect handler. **Start the tick only once the
kernel is in steady state** (`ClockTickStarter` on `reschedule`) — ticking before
the scheduler exists drives the tick routine into an uninitialized kernel and
hangs. **Get the rate right:** the target's `usrClock` *divides* the injected tick
(~1000 Hz expected → ~60 Hz kernel tick); we had to inject at 200 Hz
(`rate: 0.005`) + `HAL_IRQ_CHUNK=8000` so real `taskDelay`s completed in
human-scale wall time instead of appearing to hang.

### 4.5 Backend diagnostic env-vars (the under-used superpower)

These turn the backend into a debugger without a debugger. The high-value ones:

| env var | what it does | reach for it when |
|---|---|---|
| `HAL_MMU_FLAT_FALLBACK=1` | on the 1st data/prefetch abort, clears CP15 SCTLR.M so the rest runs flat (VA==PA) | ARM firmware enables an MMU and unicorn aborts forever (TTBR/page-walk gaps) |
| `HAL_IRQ_CHUNK=<n>` | bounds the emu chunk so IRQs drain sooner (default 2M) | early-boot needs ticks before 2M instructions elapse |
| `HAL_PC_SAMPLE=1` (+`_EVERY`) | PC histogram; top-N hottest | "stuck where?" — find a busy-spin's hot window |
| `HAL_BREAK_RAM_SPINS=1` (+`_LIMIT`,`_DISTINCT`) | detects a tight loop over few distinct PCs and breaks it | firmware idle-spins on a RAM flag an unrun ISR/core would set |
| `HAL_RECOVER_BAD_CALLS=1` (+`HAL_BOOT_RESCUE_PC`) | recovers an indirect call into garbage (unsatisfiable `_func_` vtable thunk) | C++ vtable / function-pointer dispatch to routines you can't satisfy |
| `HAL_PIN_REGS=0xA=0xV,…` (+`_PC_LO/HI`,`_ARM_PC`) | pin a RAM "ready" flag the firmware polls but nothing sets | a boot-ready latch in RAM that hangs a poll |
| `HAL_TRACK_READS=1` (+`HAL_BSS_START/END`) | logs the first read of any uninitialized .bss global (PC+lr) | crashes dereferencing a global some un-run code should have set |
| `HAL_WATCH_WRITE=0xA,…` | logs who writes an address | "who sets this field?" (a TCB self-ptr never written) |
| `HAL_STEP_TRACE=0xLO-0xHI[:path]` | single-step register dump over a PC range | pin frame/reg state to exact instructions |
| `HAL_CALL_TRACE=<path>` (+`_MAX`) | record `bl` call edges | build a call graph / reachability without a debugger |
| `HAL_SP_WATCH=1` | log PC on any SP warp ≥64MB | context-switch SP landing in garbage |
| `HAL_MAP_UNMAPPED=1` | lazily map a zero page on a stray ld/st to a gap | a garbage-pointer access shouldn't crash boot |
| `HAL_TIMER_DBG=<path>` | log timer-thread lifecycle | ticks aren't being delivered; see why |

---

## 5. Classifying a stall (do this before you "fix" anything)

| symptom | it's a… | how to confirm | how to clear |
|---|---|---|---|
| run dies with a PC + address | **fault** | the backend logs the abort/unmapped intno + addr | map the memory, set `cpu_model`, model the peripheral, or `HAL_MMU_FLAT_FALLBACK` |
| one PC window dominates the histogram | **busy-spin** (poll loop) | `HAL_PC_SAMPLE`; the hot fn reads an MMIO/RAM status in a loop | model the status read (peripheral value, `IncrementingReturn`, `RegMemWrite` the flag, or `SkipFunc` the poller) |
| CPU sits in the scheduler/idle (`reschedule`), no progress, **histogram useless** | **pend** (parked task) | Reached-traces show the last app fn reached then nothing; it's waiting on a sem/event | find what would `give` the sem (an IRQ, a peer task, a HW response) and supply it, or no-op the wait / instantly-complete it |

**The pend trap (we lived this):** once a fast timer IRQ runs, a per-instruction
sampler shows `reschedule` as 99% hot — that is **not** the bug, it's the idle
loop. For pends, stop sampling and use **Reached-traces** (`LogAndContinue` on the
suspected call chain) + **caller-capture** (an address-filtered hook recording
`lr` at a hot leaf function tells you which loop is driving it).

**The reframe that unlocked the target:** many "irreducible" pends are the firmware
**waiting on hardware that isn't there** (an I/O backplane, an SD card, a serial
peer, an interrupt). The fix is rarely "model the whole device" — it's "make the
*wait* complete": instantly-ACK the poll, return a free-running timer, report the
device absent, or **bypass at a higher level** (jump the function to its return
once the object it was constructing is built — we jumped `XbMgr::runStateCold` past
its bottomless I/O-module init once the bus object existed).

### 5.1 Audit every intercept: KEEP vs REMOVE vs DIAGNOSTIC

The discipline that separates a faithful re-host from a fabricated one (the method
in `INTERCEPT_AUDIT.md`). Classify every intercept:
- **KEEP** — a faithful model of real hardware or a firmware-derived skip: a
  genuine peripheral window (UART/timer/EMAC), a `SkipFunc` of a driver that polls
  absent hardware, or an uninstalled-hook null that forces a slot to the *exact*
  value the firmware's own `cmp#0/beq` guard already checks for (§6.3).
- **REMOVE** — fabrication: hand-constructed kernel/C++ state the firmware should
  build itself (`ScratchAlloc` replacing `memPartAlloc`, a synthetic scheduler,
  fake object pools/vtables, `FixupTaskSP` symptom-patching, force-invoked ctors).
- **DIAGNOSTIC** — observers that change nothing (`LogAndContinue`, loggers); keep
  them OUT of the permanent config.

**The test:** an intercept is fabrication if it supplies state the firmware's own
correct code would have produced — and if you're inventing such state, you're
masking a bug (usually the load base or a missing peripheral), not re-hosting. Re-
run the permanent config ALONE (no scratch overlays) before declaring victory;
overlays hide REMOVE-class crutches.

---

## 6. VxWorks track

### 6.0 Start from the known-good intercept set, don't re-derive

Don't re-derive the VxWorks-on-AT91 boot intercept set from scratch — that cost
weeks. The proven minimal set (addresses at the correct base `0x20010000`, all in
`arm-vxworks-plc_config.yaml`):

| function | addr | role |
|---|---|---|
| `bootStringToStruct` | `0x202655c0` | inject a static-IP / no-DHCP bootline (`Boot`) |
| `mr9200IntLvlVecChk` | `0x20011ff0` | inject the timer IRQ level+vector (`IntLvlVecChkArm`) |
| `sysClkEnable` | `0x20011a08` | an alternative tick-start hook (we use `reschedule`) |
| `intConnect` / `intEnable` / `intDisable` | `0x2022a06c` / `0x201737c0` / `0x201737d8` | |
| `taskSpawn` | `0x202ab070` | success marker — reaching **taskSpawn=13 → usrAppInit** |
| `taskDelay` | `0x202ad49c` | |
| `kl_NandFlashDrvInit` | `0x202bff80` | `SkipFunc` (polls unmodeled NAND forever) |

**The key idea:** do NOT model the AIC interrupt-vector *hardware*. Intercept the
one BSP routine `mr9200IntLvlVecChk` (which reads `AIC_IPR`/`AIC_IMR` — both 0 in
the rehost, so it returns "no IRQ") and inject the timer IRQ's level+vector; the
kernel's own **software** dispatch does the rest. That is the template for any
AT91/VxWorks clock bring-up (§6.3a).

VxWorks is one of the **most tractable** RTOSes to re-host, for one reason:

### 6.1 It ships its own symbol table — recover it first

A VxWorks image carries a built-in symbol table. Recovering it converts a
symbol-less ARM blob into **named functions**, and every bp_handler keys on
`addr↔symbol`. With names you intercept `logMsg`/`taskSpawn`/`sysClkConnect`/
`reschedule`/`usrClock` **by name** and read the boot via `logMsg`; without them
every gate is a blind `FUN_xxxxxxxx`. **This is the highest-leverage hour of the
whole project.**

### 6.2 Symbol recovery (`gen_symbols.py` pattern)

- The in-image symtab (VxWorks 6 / the target) is a table of **20-byte entries**:
  `next@+0`, `name_ptr@+4` (into the string table), `value@+8` (the symbol VA),
  `group@+0x10`, `type@+0x12`. The string table is NUL-separated ASCII elsewhere.
- Read words relative to the **TRUE link base** (the load-base fix matters here
  too — a wrong base mangles every name/value). Filter entries whose `value` is
  out of range or odd (Thumb bit; the image is ARM). Resolve `name_ptr`→offset→
  NUL-terminated string. Emit `name,start,end` CSV; load with `-s syms.csv`.
- Locate the table by scanning for the characteristic 20-byte stride / a known
  symbol string, or from a VxWorks `symTbl` reference.
- **Entry `type@+0x12` matters:** type `0x05` = global **text** (a real code
  function, in-file) — these are what you intercept; type `0x11` = global
  **.bss/data** (resolves *past* the file end, populated at runtime) — these are
  method/handler slots, not text routines. Don't try to break on a `0x11` symbol.
- **Tools beat hand-parsing.** A hand-parser often finds only a fragment; use
  **VxHunter** (`PAGalaxyLab/vxhunter`) to recover the full table by signature
  (the target: ~12.7k usable symbols), and the **Ghidra VxWorks loader + FunctionID +
  apply-symbols** flow to recover stripped functions by code signature and merge
  the names (the target: 19,378 functions). On Apple Silicon, drive Ghidra with headless
  Java scripts — PyGhidra's JIT init SIGBUS'd.
- **The app/downloadable symtab STRIPS the core kernel.** `reschedule`,
  `sysClkConnect`, `taskSpawn`, `intConnect`, `tickAnnounce`, etc. are often
  ABSENT from the recovered table (it's the application symtab, not the kernel's).
  Locate those by code signature / call-graph (or the §6.0 addresses),
  not by name.

### 6.3 The boot chain and its canonical gates

Each stage has a well-known gate that stalls a naive rehost. (Addresses are the target;
the *shapes* are general VxWorks.)

- **STAGE 0 — reset / CP15 bring-up.** Entry at file-offset + link base. CP15
  cache-type read may need a real value (`ReturnConstant` the CP15 reg) or the
  decoder rejects privileged ops (`cpu_model`). Reset disables the AIC.
- **STAGE 1 — `sysInit`→`usrInit`→`sysHwInit`/`cacheLibInit`.** Board/console
  init + a us-delay primitive on a free-running counter → model that counter
  (`Timer`) so busy-waits terminate.
- **STAGE 2 — `usrRoot`** (the root task: drivers, clock, MMU, network, app). The
  gate cluster:
  - **(a) Clock / AIC vectoring.** `sysClkConnect`→`sysClkEnable`; the tick must
    route `vector+0x18`→`intEnt`→AIC dispatch→`xxxIntLvlVecChk`→the system
    dispatcher→`usrClock`→`tickAnnounce`. The classic gate: `xxxIntLvlVecChk`
    reads an empty AIC pending register → "no IRQ." **Fix = `IntLvlVecChkArm`**
    (inject level/vec for the timer IRQ — the kernel's *software* dispatch does
    the rest; no hardware-vector modeling). Two concrete AT91 sub-gates (both
    faithful models, not skips): **(i)** the System-IRQ dispatcher gates on
    `(ST_SR & ST_IMR) & PITS`, but a plain `GenericPeripheral` reads 0 → clock
    never called; **`At91SysCtrl`** reports bit0=1 for `ST_SR` (`0xfffffd10`) and
    `ST_IMR` (`0xfffffd1c`). **(ii)** the BSP PIT-handler global `*0x2042e5d0` is 0
    (firmware never registered it in the rehost) → a `SetMemory` on the dispatcher
    entry `0x200196e8` writes `*0x2042e5d0 = usrClock (0x2001bc68)` each tick (only
    ONE intercept per addr — don't also trace it). Start the tick only at steady
    state (`ClockTickStarter` on `reschedule`); get the **rate** right — `usrClock`
    *divides* the injected tick (~1000→~60 Hz), so inject at ~200 Hz
    (`rate: 0.005`) + `HAL_IRQ_CHUNK=8000` or correct `taskDelay`s look like hangs.
  - **(b) MMU / TTBR / vmLib.** `usrMmuInit` enables the MMU; unicorn's ARMv5
    CP15/TTBR handling is unreliable (TTBR0 reads 0 → endless aborts). **Fix =
    `HAL_MMU_FLAT_FALLBACK=1`** (clear SCTLR.M on the first abort → run flat;
    vmLib stays initialized because the fix is *late*, on the fault — do **not**
    skip `usrMmuInit`, the app needs vmLib). Or switch to the avatar2/QEMU backend
    (real MMU) for MMU-heavy phases.
  - **(c) NAND / flash / FS.** A driver-init (`kl_NandFlashDrvInit`) polls
    unmodeled NAND forever → `SkipFunc`. Related: `dosfsDiskFormat`/`chkdsk` pend
    on an XBD bio-done semaphore (no block device) → `SkipFunc` (callers treat the
    nonzero device-name ptr as success).
  - **(d) C++ static ctors (`cplusCallCtors`).** The app's global objects are
    built here. **Subtlety:** the ctor table is **runtime-populated** — calling
    `cplusCallCtors` out of order walks an empty table. It must be reached
    *naturally* after the kernel is multitasking. A single ctor can hang (it
    constructs an object that touches absent HW) — find it by tracing the ctor
    dispatch site and skip the *blocking sub-call*, not the whole ctor.
  - **(e) Network-up / DHCP.** `usrNetworkInit`/`usrNetAppInit` start the stack
    and `tNetTask`/`tDhcpc*`. The stored bootline often enables DHCP → blocks on a
    lease that never comes. **Fix = the `Boot` handler** on `bootStringToStruct`:
    inject a **static-IP, no-DHCP** bootline. IP may also come from board
    switches (model that MMIO → default path). For the stack to *progress* without
    a NIC, TX must "complete" and ARP must "resolve" (return success → `ip_output`
    proceeds; see §6.5/§7).
- **STAGE 3 — `usrAppInit` → the application.** Now you're in vendor code
  (the target PLC runtime, its cooperative sub-manager state machine, its comm
  system). Gates here are app-specific phantom-HW waits — clear them with the §5
  reframe (instant-complete the wait, or higher-level bypass).

**The uninstalled-hook null (the most-reused *faithful* VxWorks model).** Pattern:
`ldr rN,[=slot]; ldr rN,[rN]; cmp rN,#0; beq <skip>; … mov pc,rN`. The slot holds a
sentinel because the installer ctor hasn't run yet — a mid-function placeholder, a
mangled C++ type-name ptr, or the marker `0x00050000`. Force the slot to 0 so the
firmware takes its OWN `beq` skip path (`ForceMemValue`/`SetMemory`). Four hard-won
caveats: **(1)** `0x00050000` occurs ~14,000× in the image — it's a common word,
NOT a unique marker; never bulk-zero it (a blanket fill destroyed the C++ class
tables/string pool). **(2)** Only null where the dispatch HAS a `cmp#0/beq` — an
unguarded vtable call (`ldr r3,[r0]; ldr r1,[r3,#4]; mov pc,r1`) needs a real
object and cannot be nulled. **(3)** A boot-time `SetMemory` seed may not hold if a
runtime write re-arms the slot — apply `ForceMemValue` AT THE READ SITE instead.
**(4)** A PC-bound breakpoint can be bypassed when the function is entered via a
`bl` past the bp address — verify the hook actually fires (`max_logs`).

### 6.4 The VxWorks bp_handler suite (`bp_handlers/vxworks/`)

Purpose-built; use these instead of hand-rolling:
- **`vx_logging.VxLogging`** (`logMsg`) — **your primary boot-visibility window.**
- **`boot.Boot`** (`bootStringToStruct`) — inject the bootline (static IP/no DHCP).
- **`sys_clock.SysClock`** (`sysClkConnect`/`Enable`/`RateSet`) — learn the clock
  ISR; **`sys_clock.ClockTickStarter`** (on `reschedule`) — start the tick at
  steady state. The clock-gate logic lives here.
- **`interrupts.Interrupts`** (`intConnect`/`intEnable`/`IntLvlVecChk`) — bridge
  to the `Interrupts` model. **`generic.common.IntLvlVecChkArm`** is the ARM AIC
  vector injector the clock depends on; **`IrqReturnArm`** is the canonical IRQ
  exit; **`IntConnectLogger`** records vec→ISR.
- **`tasks.Tasks`/`TaskSpawnLogger`** — log every `taskSpawn` (name + entry): your
  map of what the kernel brought up. **`scheduler.Scheduler`** — WIND scheduler /
  TCB instrumentation; **`FixupTaskSP`** repairs a context-switch SP warp.
- **`vx_mem.VxMem`** (`vxMemProbe`) — implement the safe-probe in Python.
- **`errors.VxErrors`** — decode `errno`/`S_xxx` (incl. `selectLib`) — invaluable
  when a socket/IO call returns a negative code.
- **`ios_dev.IosDev`**, **`posix_logging.PosixLogging`**, **`dos_fs.DosFs`**,
  **`yaf_fs.YafFs`** (NAND-FS), **`ty_dev.TyDev`** (tty), **`ethernet.Ethernet`**
  (END/MUX EMAC) — the I/O layers.

### 6.5 Application-layer connectivity (the socket-level bridge)

Once the firmware's own server **binds and listens** (e.g. VxWorks
`socket`/`bind`/`listen` reach LISTEN), let a real client talk to it **without a
TAP** by bridging the BSD socket *thunks*:

- **`SocketBridge`** intercepts `select`/`accept`/`recv`/`send`/`close`/
  `shutdown`/`setsockopt`/`__errno` and runs a host TCP server. The firmware's own
  accept/recv/send loop runs; you feed its `select`/`recv` from host bytes and
  ship its `send` to the client. The firmware's real protocol stack (UMAS/Modbus,
  here) builds every response.
- **Why it works cleanly on VxWorks:** servers are commonly a **non-blocking
  `select()`-driven poll** (`selLib`, timeout {0,0}) called by a scheduler — so no
  hook ever blocks the emu thread. You report readiness from host-side state a
  background thread maintains.
- **The contract details that matter** (general to BSD sockets): `select` zeroes
  `readfds` then sets only ready bits and returns the count (the `fds_bits[fd>>5]
  & 1<<(fd&0x1f)` layout); `recv` n>0 = data, n==0 = **peer closed** (firmware
  tears down), n==-1 + `errno EWOULDBLOCK` = retry/keep-alive (so a "no data"
  recv must set errno via an `__errno` hook); hand out **connection fds high
  enough** (200+) to avoid colliding with real kernel fds; **scope** each hook to
  your server (caller-LR for `select`, fd-in-map for `recv`/`send`/`close`) and
  **pass everything else through** (`return False,None`) so other sockets keep
  working. Derive the exact `recv`/`errno` branch from the server's
  `recv`-wrapper disassembly — don't guess.
- **Simpler alternative:** `ModbusTcpBridge` (app-layer) calls a firmware message
  handler directly, bypassing the stack — faster to stand up but less faithful.
- **Port note:** binding host `:502` needs root (ports <1024). Use a high port
  (1502) for non-root testing; the firmware side is identical.

---

## 7. Worked example — the target, end to end (condensed)

1. **Load base fix** — image links at `0x20010000`, not `0x20000000`. Mapping it
   right resolved a year's worth of "C++ construction wall" symptoms at a stroke.
2. **Symbols** — recovered the in-image symtab (`gen_symbols.py`) → 15k named
   functions; `logMsg`/`taskSpawn` intercepts gave a live boot narrative.
3. **Clock** — `IntLvlVecChkArm` (vec=1) + `At91SysCtrl` (PIT status) +
   `SetMemory` PIT-handler seed + `ClockTickStarter` at 200 Hz → time advances,
   `taskDelay` works.
4. **MMU** — `HAL_MMU_FLAT_FALLBACK=1` cleared the 6.4M-abort loop; vmLib stays up.
5. **Boot gates** — `SkipFunc` NAND/dosfsFormat/chkdsk/sdCardMgt; static-IP
   bootline; wheels MMIO=0; `muxEndProtoRegister` forced inline → reached
   `usrAppInit` and the PLC runtime.
6. **PLC cold-init (the long tail)** — the cooperative sub-manager state machine
   pends on absent X-bus/SD/trace/UART hardware. Cleared each with the §5 reframe:
   instant-ACK the X-bus exchange poll (`RegMemWrite [r4+0x3e]=3`), free-running
   GPX timer (`IncrementingReturn`), no-card SD (`ReturnConstant 3`), no-op the
   trace task (`SkipFunc`), DBGU TXRDY (`SetRegisters r3|=2`), and a **higher-level
   bypass** jumping `XbMgr::runStateCold` to its return once the bus object was
   built (`SetRegisters {r0:0, pc:…}`). A **snapshot lab** (`context_save` + all
   `mem_regions`, restore per experiment) made each test ~90 s instead of a full
   boot.
7. **The Ethernet gate** — comm-ctor starts the Ethernet manager only if a
   board-config flag is set (`config[0x70]`); forced it (`SetRegisters r2=1`) →
   into the **live TCP/IP stack**.
8. **Stage 1 — reach LISTEN** — the stack spun in `ip_output` (TX never
   completes). Modeled EMAC TX-done (`ARM920_Send_Internal`→`ReturnConstant 0`) +
   ARP-resolve (`arpresolve`→`1`) → the firmware's real `Port502Server` did
   `socket`/`bind(:502)`/`listen` → **LISTENING**.
9. **Stage 2 — real client round-trip** — `SocketBridge` over the firmware's
   `select`/`accept`/`recv`/`send` → a stdlib Modbus client gets **`the device product name`
   / `the firmware version`** (Read Device ID) and a real **UMAS** (FC 0x5A) response. the PLC configurator
   would see a genuine device.

**Success markers (grep for these — a *fabricated* steady-state will NOT show
them).** The rebased config + `HAL_MMU_FLAT_FALLBACK=1` boots full multitasking
VxWorks spawning ~14 real tasks: `tJobTask tLogTask tNbioLog tErfTask tNetTask`
(network stack), `tDhcpcStateTask`/`ReadTask`, `tTftpd tFtp6d`, `tShell0`,
**`MidRangePPP_C_1` / `MidRangePPP_D_1`** (the target PLC runtime), `EnableUSB`,
`tXbdService` — clock advancing, no faults. The natural boot chain on the correct
base: `0x20010184` (cold entry) → reset stub/AIC → CP15/MMU/cache+SP → SoC HW init
→ `kernelInit` → `memPartInit` → `taskInit` → `reschedule` → first real context
switch (`ldm r0,{…,pc}^`) → `usrRoot` → `usrAppInit` → the task set. **Note the
two Modbus servers:** the `*125`/`acceptP502Connections` path is the *manufacturing*
FC125 server (provisioning: read/program serial+MAC), gated on test/proto mode —
**not** the one the PLC configurator talks to. The real PLC Modbus/UMAS :502 server is
**`Port502Server`** (its `PollMsgToRout` select-poll loop), reached via the comm
system on the normal `EthernetManager::initialize` path. Don't wire the bridge to
the FC125 server.

---

## 8. Lessons & pitfalls (the expensive ones)

- **Load base before anything.** A wrong link base mimics a hundred code bugs.
  First-pointer-deref crash ⇒ check the base.
- **Recover symbols first (VxWorks).** Everything downstream is 10× faster.
- **Kill stray runs.** Leftover emulator processes made boots look 10× slower and
  cost real debugging hours chasing a phantom "boot wall."
- **Address-filter your hooks.** A `UC_HOOK_CODE` with `begin==end==addr` is nearly
  free; an *unfiltered* per-instruction hook fires every instruction and cripples
  boot — it'll look like a hang.
- **The clock-storm lie.** After a fast tick, `reschedule` dominates any PC
  sampler; it is the idle loop, not the bug. Use Reached-traces for pends.
- **Default-0 MMIO is a silent branch-flipper.** If a peripheral read gates a
  decision, model the value (`HAL_MMIO_LOG` helps spot these).
- **Don't model the device — complete the wait.** Most "irreducible" pends are
  waits on absent hardware; instant-complete/ACK them, or bypass at a higher level
  once the object being built exists. Modeling a whole integrated subsystem
  (we tried, on the X-bus) does not converge.
- **Snapshot for iteration speed.** `context_save` + `mem_read(all mem_regions)`,
  restore per experiment, turns a 40 s boot into a 1 s reset for model trials.
  *Caveat:* PC-writing hooks disrupt unicorn's `emu_start` instruction-`count`
  cap — bounded runs overshoot; use a wall-clock watchdog, and the snapshot lab is
  unreliable once such hooks are installed (run natively past that point).
- **Get the tick rate right.** A divided kernel tick makes correct `taskDelay`s
  look like hangs. Match the firmware's expected timer frequency.
- **Bridge, don't TAP, on a dev box.** Socket-syscall interception gives a
  faithful "real client ⇄ real firmware server" with no kernel networking — and
  it sidesteps macOS TAP pain entirely.
- **Scope and pass-through.** Shared syscall thunks serve every socket/fd —
  bridge only your target (by caller-LR or fd) and `return False,None` for the
  rest, or you'll break the firmware's other I/O.
- **Verify the committed config alone.** Re-run with only the permanent config (no
  scratch overlays) before declaring victory — overlays hide gaps.

### 8.1 Named dead-ends — do not re-walk these

- **The two load-base misdiagnoses.** Before the base fix, the same bug was
  mis-explained twice: as a "+0x10000 pointer glitch" and as a "missing 64 KB NAND
  block" (with an `arm-vxworks-plc_fixed.bin` zero-insertion workaround). Both were wrong; the
  image simply links at `0x20010000`. The wrong base also corrupted symbol recovery
  (the old `recover_symtab_names.py` at base `0x20000000` had a "mid-string defect"
  + a `_Z`-only filter — both artifacts of the wrong base). A wrong base mimics a
  hundred code bugs **and** breaks symbols.
- **The fabrication tower** (§1.1). ~92 hand-built intercepts faking kernel/C++
  state produced a fake steady-state while the firmware's own scheduler never ran.
  Deleted wholesale once the load base was fixed.
- **MMU options A/C/D** (three rejected ARM data-abort fixes). A = `SkipFunc
  usrMmuInit` (MMU never enables) killed the abort but the app silently stalled —
  vmLib is non-functional without the MMU; reverted. D = extend `vmGlobalMapInit`
  coverage — moot, the global map already identity-maps the page-table pool (the
  table was fine, just not installed in TTBR0). C = vector aborts to the firmware
  handler — judged likely to panic. **Winner = B = `HAL_MMU_FLAT_FALLBACK=1`**
  (clear SCTLR.M late, on the first fault).
- **Nulling *installed* hooks starves init.** Forcing a `_func_` slot to 0 is only
  valid for an *uninstalled* guarded hook; nulling one the firmware legitimately
  populated deletes real initialization downstream.
- **X-RAM-as-MMIO / wholesale-skipping a sub-manager.** Mapping the X-bus dual-port
  RAM as a `GenericPeripheral` (writes ignored) made `CheckXRam`'s copy/verify
  retry-loop forever — it must be real RAM that persists writes. And wholesale
  `SkipFunc` of `XbMgr::runStateCold` left the X-bus object unbuilt, crashing a
  later ctor on a garbage pointer — skip the *blocking sub-call*, not the manager.
- **The QEMU GIC clock.** Wiring a GICv2 to drive the tick under qemu delivered the
  first IRQ then stalled — the firmware uses the AT91 AIC and never EOIs the GIC,
  so the active priority blocks further IRQs. qemu would also hit the same
  AIC→`tickAnnounce` gate. (Clock is a backend-independent gate; fix it at the
  `IntLvlVecChk`/`At91SysCtrl` seam, not with a foreign interrupt controller.)

---

## 9. When to escalate / change backend

- **MMU-heavy app phase that flat-fallback can't satisfy** → avatar2/QEMU backend
  (real ARM MMU + proper abort vectoring). Cost: slower (MMIO round-trips), Docker,
  and the IRQ path differs (QEMU has its own injection; `arm_vic` is unicorn-only).
  **Caveat:** don't bolt a GIC on to drive the clock — the firmware uses the AT91
  AIC and never EOIs a GIC, so it delivers one IRQ then stalls (§8.1). The clock is
  a backend-independent gate; fix it at the `IntLvlVecChk`/`At91SysCtrl` seam on
  *either* backend. Port your intercepts; instructions were validated equal early.
- **You need fuzzing** → `--emulator libafl-qemu`.
- **You're reversing blind** (no symbols, unknown SoC) → lean on `AutoPeripheral`
  + `RecordingPeripheral` (SQLite MMIO trace), `HAL_CALL_TRACE`, `HAL_TRACK_READS`,
  `HAL_STEP_TRACE` to *discover* structure before modeling it.

> **Context — what else this branch built (used here, documented elsewhere).** The
> the target re-host rode on framework work this branch also produced: the multi-arch
> IRQ/exception-delivery framework (the target uses its `arm_vic` controller), the
> auto-peripheral modeling pipeline (`RecordingPeripheral`/`AutoPeripheral` +
> synthesize/triage/unpack, used as a discovery aid), LLM-assisted model synthesis,
> an x86/i386 target, and the QEMU/avatar2 + libafl-qemu backends. This playbook
> only covers them as *tools the target used* — see the framework modules + commit
> history for how they work.

---

## 10. Quick reference — the target config as a template

`test/firmware-rehosting/arm-vxworks-plc/arm-vxworks-plc_config.yaml` is a complete,
working example of every technique above: load-base memories, AT91 peripheral
windows, the clock/AIC/MMU stack, the boot-gate skips, the PLC cold-init model
(`RegMemWrite`/`IncrementingReturn`/`SetRegisters`/`SkipFunc`/`ReturnConstant`),
the Stage-1 EMAC stubs, and the Stage-2 `SocketBridge`. Read it alongside this
playbook and the target usage guide (`README.md`). The general diagnostic harnesses
are a shipped subpackage — **`halucinator.diagnostics`**
(`python -m halucinator.diagnostics.<tool>`: `probe_at_pc`, `caller_histogram`,
`mmio_region_sampler`, `mmu_fault_introspect`, `snapshot_lab`, `modbus_probe`) with
its own README + the built-in `HAL_*` env-var table. arm-vxworks-plc-local: `run_cfg.py`
(runner) and the `arm-vxworks-plc_lab_spec.py` snapshot-lab spec shown in `README.md`.
The proven minimal intercept recipe is in §6.0.
