# Provenance — test/firmware-rehosting/reflow-oven-stm32/

Auto-modeling rehost of the P2IM **Reflow_Oven** firmware (STM32F4 (Cortex-M4)): reflow-oven controller (GPIO/SSR control loop).
Boots and runs under halucinator's in-process unicorn backend with the
AutoPeripheral catch-all (breaks MMIO spin-waits, auto-discovers UART,
records an MMIO trace) and skip_svc (steps over P2IM's aflCall). Only
non-MMIO clock/delay setup is stubbed (see reflow_auto_config.yaml).

**Binary not shipped.** `extract.sh` regenerates Reflow.bin / reflow_addrs.yaml
from the prebuilt, unstripped ELF in
[`RiS3-Lab/p2im-real_firmware@d4c7456`](https://github.com/RiS3-Lab/p2im-real_firmware/tree/d4c7456574ce2c2ed038e6f14fea8e3142b3c1f7)
(`binary/Reflow_Oven`). The P2IM binaries are AFL-instrumented (an `aflCall`
`svc #0x3f`); skip_svc handles it.

Run: `./extract.sh && ./run_auto.sh`  •  Test: `./run_tests_auto.bash`
