# Provenance — test/firmware-rehosting/steering-sam3x/

Auto-modeling rehost of the P2IM **Steering_Control** firmware (Atmel SAM3X / Arduino Due (Cortex-M3)): car steering controller (sensor/servo loop).
Boots and runs under halucinator's in-process unicorn backend with the
AutoPeripheral catch-all (breaks MMIO spin-waits, auto-discovers UART,
records an MMIO trace) and skip_svc (steps over P2IM's aflCall). Only
non-MMIO clock/delay setup is stubbed (see steering_auto_config.yaml).

**Binary not shipped.** `extract.sh` regenerates Steering.bin / steering_addrs.yaml
from the prebuilt, unstripped ELF in
[`RiS3-Lab/p2im-real_firmware@d4c7456`](https://github.com/RiS3-Lab/p2im-real_firmware/tree/d4c7456574ce2c2ed038e6f14fea8e3142b3c1f7)
(`binary/Steering_Control`). The P2IM binaries are AFL-instrumented (an `aflCall`
`svc #0x3f`); skip_svc handles it.

Run: `./extract.sh && ./run_auto.sh`  •  Test: `./run_tests_auto.bash`
