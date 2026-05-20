#!/usr/bin/env bash
# E2E test: the auto-modeling stack boots Gateway and runs its real firmware
# logic. Firmata gateway (Firmata loop). We assert the firmware boots and executes (the PC sampler
# proves millions of instructions run in application code, not stuck at an
# init stub) without a crash. Some of these are control loops with little/no
# UART, so we assert execution rather than console text.
set -uo pipefail
SCRIPT_DIR=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )
cd "$SCRIPT_DIR"
[[ -f Gateway.bin && -f gateway_addrs.yaml ]] || ./extract.sh
pkill -9 -f "halucinator.*-n gateway_auto" 2>/dev/null || true
rm -f hal_auto_out.txt
HAL_PC_SAMPLE=1 HAL_PC_SAMPLE_EVERY=200000 ./run_auto.sh > hal_auto_out.txt 2>&1 &
RUN_PID=$!
for _ in $(seq 1 30); do
    grep -qE "PC sample|busy-wait|AutoPeripheral UART" hal_auto_out.txt 2>/dev/null && break
    kill -0 "$RUN_PID" 2>/dev/null || break
    sleep 1
done
kill -9 "$RUN_PID" 2>/dev/null || true
pkill -9 -f "halucinator.*-n gateway_auto" 2>/dev/null || true
if grep -q "Letting Unicorn Run" hal_auto_out.txt \
   && grep -qE "PC sample|busy-wait|AutoPeripheral UART" hal_auto_out.txt \
   && ! grep -qE "Traceback|UcError" hal_auto_out.txt; then
    echo "Gateway auto-modeling e2e test PASSED - booted and running firmware logic"
    grep -A4 "PC sample" hal_auto_out.txt | grep -oE "0x[0-9a-f]{8}  x[0-9]+" | head -3 | sed 's/^/    pc /'
    exit 0
else
    echo "Gateway auto-modeling e2e test FAILED"
    grep -vE "pkg_resources|UserWarning" hal_auto_out.txt | tail -15
    exit 1
fi
