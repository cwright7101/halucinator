# cnc-grbl — rehosting a real GRBL CNC controller

Rehosts unmodified **GRBL** motion-control firmware for an
**STM32F407VG (Cortex-M4)** from the P2IM real-firmware dataset. The
firmware boots under halucinator and emits its real serial console — the
`$N=` settings dump and the `Grbl 0.8c ['$' for help]` banner — with no
hardware model beyond a catch-all peripheral region plus a few intercepts.

## Run

```sh
./extract.sh        # fetch prebuilt ELF, carve CNC.bin, build cnc_addrs.yaml
./run.sh            # boot under the unicorn backend (HAL_EMULATOR overrides)
./run_tests.bash    # boot + assert the GRBL banner/settings appear
```

`extract.sh` reuses the p2im-drone clone of the dataset if present, else
clones the pinned commit. See `PROVENANCE.md` for source + licensing.

## How it boots without hardware

| Concern | Handling |
|---|---|
| Clock / PLL / SysTick spin-waits | `SystemInit`, `SystemClock_Config`, `HAL_RCC_*Config`, `SysTick_Config` → `ReturnZero` |
| `usart_putc` TXE busy-wait | intercepted by `bp_handlers/cnc_uart.CncUart` — captures the byte, returns |
| delays | `HAL_Delay`, `_delay_ms/us`, `delay_ms/us` → `ReturnZero` |
| AFL fuzz hypercall (`svc #0x3f`) | `aflCall` → `ReturnZero` (dataset binaries are AFL-instrumented) |
| everything else | catch-all `GenericPeripheral` over the STM32 MMIO window |

## Files

- `cnc_memory.yaml` — STM32F407 memory map + machine (entry/SP/vector)
- `cnc_config.yaml` — intercept wiring
- `bp_handlers/cnc_uart.py` — USART2 output-capture intercept
- `extract.sh` / `run.sh` / `run_tests.bash` — regenerate / run / test
- `PROVENANCE.md` — source dataset + licensing
