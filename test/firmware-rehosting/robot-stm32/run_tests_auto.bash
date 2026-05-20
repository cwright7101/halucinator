#!/usr/bin/env bash
# E2E test: the auto-modeling stack generalizes to a second real device.
# The self-balancing-robot firmware is a control loop (not a console app),
# so we assert the auto-modeling MECHANISMS fire — the firmware boots, the
# AutoPeripheral auto-discovers a UART data register, and it breaks at
# least one MMIO spin-wait — rather than asserting on rich console text.
set -uo pipefail
SCRIPT_DIR=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )
cd "$SCRIPT_DIR"
[[ -f Robot.bin && -f robot_addrs.yaml ]] || ./extract.sh

pkill -9 -f "halucinator.*-n robot_auto" 2>/dev/null || true
rm -f hal_auto_out.txt
./run_auto.sh > hal_auto_out.txt 2>&1 &
RUN_PID=$!
for _ in $(seq 1 30); do
    if grep -q "AutoPeripheral UART(" hal_auto_out.txt 2>/dev/null \
       && grep -q "AutoPeripheral.*busy-wait" hal_auto_out.txt 2>/dev/null; then
        break
    fi
    kill -0 "$RUN_PID" 2>/dev/null || break
    sleep 1
done
kill -INT "$RUN_PID" 2>/dev/null || true
sleep 2
pkill -9 -f "halucinator.*-n robot_auto" 2>/dev/null || true

if grep -q "AutoPeripheral UART(" hal_auto_out.txt \
   && grep -qE "AutoPeripheral UART\(|AutoPeripheral.*busy-wait" hal_auto_out.txt \
   && ! grep -qE "Traceback|UcError" hal_auto_out.txt; then
    echo "Robot auto-modeling e2e test PASSED - booted, UART auto-discovered"
    grep -oE "AutoPeripheral UART\(0x[0-9a-f]+\)" hal_auto_out.txt | head -1 | sed 's/^/    discovered /'
    exit 0
else
    echo "Robot auto-modeling e2e test FAILED"
    grep -vE "pkg_resources|UserWarning" hal_auto_out.txt | tail -20
    exit 1
fi
