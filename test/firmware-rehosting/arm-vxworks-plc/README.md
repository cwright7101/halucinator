# ARM / VxWorks PLC re-host (example)

A worked HALucinator re-host of an **ARM (AT91RM9200) VxWorks 6.x PLC** that boots
full multitasking VxWorks and serves its own **Modbus/UMAS server on TCP `:502`** —
a real Modbus client gets real responses from the firmware's own `Port502Server`.

> Run every command below **from this directory**
> (`test/firmware-rehosting/arm-vxworks-plc/`), with the HALucinator venv active.

## Prerequisites

1. **HALucinator installed** — this repo provides the `halucinator` command. If you
   have not set it up yet, follow *Installation* in the repo's **top-level
   `README.md`**. The short version, run **from the repo root**:

   ```bash
   git submodule update --init
   python3 -m venv ~/.virtualenvs/halucinator
   source ~/.virtualenvs/halucinator/bin/activate
   pip install -e deps/avatar2/
   pip install -r src/requirements.txt
   pip install -e src                      # installs the `halucinator` command
   ```

   `pip install -e src` is what creates the `halucinator` command and pulls in the
   `unicorn` + `capstone` libraries the unicorn backend needs. Verify with
   `halucinator --help`. **Activate this venv in every terminal** you use below.

2. **Python 3.7+**.

3. **The firmware image** — proprietary and **not committed**. Put your own copy in
   this directory as **`arm-vxworks-plc.bin`**: a flat ARM VxWorks image linked at
   load base `0x20010000`. The config's fixed addresses are bound to that exact
   image — a **byte-identical** copy works under any filename, but a **different
   firmware build/version does not**.

## 1. Recover the symbols

The config is **symbol-driven**: many intercepts name a `function:` and let the
loader resolve its address from the recovered symbol table. Recover that table from
the image into `symbols.csv`:

```bash
python3 extract_symbols.py arm-vxworks-plc.bin --base 0x20010000 -o symbols.csv
```

`extract_symbols.py` auto-locates the in-image VxWorks symbol table by signature
(standard library only — no extra deps). If your image's table has a sparse edge
the auto-scan misses, pin its file-offset bounds explicitly:

```bash
python3 extract_symbols.py arm-vxworks-plc.bin --base 0x20010000 \
        --symtab 0x3c8d14:0x41c068 -o symbols.csv
```

## 2. Boot it (terminal 1)

The committed config binds the **real Modbus port `:502`**, and binding a port
below 1024 needs **root**. Pick one:

**Option A — non-root, test on `:1502` (simplest).** In
`arm-vxworks-plc_config.yaml`, change `tcp_port: 502` → `tcp_port: 1502` in the
`SocketBridge` block, then:

```bash
HAL_MMU_FLAT_FALLBACK=1 HAL_IRQ_CHUNK=8000 \
  halucinator -c arm-vxworks-plc_config.yaml -s symbols.csv --emulator unicorn
```

**Option B — as root, serve the real `:502`** (a client then connects exactly as it
would to a real device):

```bash
sudo env "PATH=$PATH" HAL_MMU_FLAT_FALLBACK=1 HAL_IRQ_CHUNK=8000 \
  halucinator -c arm-vxworks-plc_config.yaml -s symbols.csv --emulator unicorn
```

The two `HAL_*` variables are required unicorn-backend options for this image:
`HAL_MMU_FLAT_FALLBACK=1` runs flat past the firmware's MMU gate (clears the ARM
MMU on the first abort); `HAL_IRQ_CHUNK=8000` delivers injected IRQs every 8000
instructions so the system tick advances.

**Leave it running.** A *successful* boot never exits — the firmware comes up and
sits in its `:502` server loop waiting for a client. You talk to it from a **second
terminal** (step 3), then stop it here with `Ctrl-C`.

A good run spawns ~14 real VxWorks tasks (including the PLC runtime), brings up the
TCP/IP stack, and reaches the `:502` LISTEN (the firmware's `Port502Server`); the
`SocketBridge` intercept opens the matching host TCP server. The boot is
single-threaded emulation, so it is **CPU-bound** — on a busy machine it just takes
longer. Free up CPU if it is slow.

### Bounded / CI run (optional)

`run_cfg.py` is the **same** `halucinator` invocation (same
`-c`/`-s`/`--emulator unicorn` args) plus a watchdog that exits after
`VERIFY_SECS`, so an automated run can't hang forever:

```bash
HAL_MMU_FLAT_FALLBACK=1 HAL_IRQ_CHUNK=8000 \
RUN_CFGS=arm-vxworks-plc_config.yaml RUN_SYMS=symbols.csv VERIFY_SECS=180 \
  python3 run_cfg.py
```

If you see `RUN: watchdog fired` **before** the `:502` LISTEN, the machine was just
too loaded — raise `VERIFY_SECS` or free up CPU. It is not a re-host failure.

## 3. Talk to it (terminal 2)

In a **second terminal** (venv active, the boot from step 2 still running). Use the
**same port you bound** — `1502` for option A, `502` for option B:

```bash
# shown for option A (:1502); use --port 502 if you booted with option B
python3 -m halucinator.diagnostics.modbus_probe --port 1502 --fc 0x2b --data 0e0101  # Read Device ID
python3 -m halucinator.diagnostics.modbus_probe --port 1502 --fc 0x5a --data 0002     # UMAS (the protocol PLC configurators use)
```

A successful probe prints `RESPONSE RECEIVED -- bridge round-trip works` plus the
decoded reply — the firmware's **own** server answering: Read Device ID returns the
device's product name + firmware version, and the UMAS request returns a real UMAS
response. (If you get `connect FAILED` / `NO RESPONSE`, the boot hasn't reached the
`:502` LISTEN yet, or you used the wrong `--port`.)

## What the config does

`arm-vxworks-plc_config.yaml` carries the SoC model + the re-host gates:
- memories at the true load base; AT91 peripheral windows (`At91SysCtrl` PIT
  status, `At91Emac` PHY link-up, the EBI/wheels windows);
- the clock seam (`mr9200IntLvlVecChk` + `At91SysCtrl` + the PIT-handler register
  + `ClockTickStarter`) so the VxWorks tick advances;
- boot-gate skips (`kl_NandFlashDrvInit`, `dosfsDiskFormat`, `sdCardMgt`, …) for
  absent NAND/SD/block hardware — these are **symbol-driven** (no addresses);
- the PLC cold-init model (X-bus/SD/trace/DBGU/ethernet-enable) — mid-function
  points, so these keep explicit `addr:`;
- Stage-1 EMAC TX/ARP stubs (so the IP stack reaches the `:502` LISTEN) and the
  Stage-2 `SocketBridge` (host TCP `:502` ⇄ the firmware's socket syscalls).

The reusable diagnostic harnesses are in `halucinator.diagnostics`
(`python -m halucinator.diagnostics.<tool>`). The general re-hosting **method**
behind this example — firmware-agnostic, with a deep VxWorks track — is written up
in [`PLAYBOOK.md`](PLAYBOOK.md).

## Files

- `arm-vxworks-plc_config.yaml` — the re-host config (symbol-driven).
- `extract_symbols.py` — VxWorks in-image symbol-table extractor.
- `run_cfg.py` — bounded runner (`RUN_CFGS` / `RUN_SYMS` / `VERIFY_SECS`).
- `PLAYBOOK.md` — the general re-hosting method (firmware-agnostic + VxWorks track).
- `arm-vxworks-plc.bin`, `symbols.csv` — **you provide / generate; git-ignored.**
