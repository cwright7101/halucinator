#!/usr/bin/env bash
# E2E test for the auto-modeling path: assert the AutoPeripheral
# auto-discovers the UART and surfaces the GRBL console WITHOUT a
# usart_putc / usart_init intercept (contrast run_tests.bash, which uses
# hand-written intercepts).
set -uo pipefail

SCRIPT_DIR=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )
cd "$SCRIPT_DIR"

[[ -f CNC.bin && -f cnc_addrs.yaml ]] || ./extract.sh

pkill -9 -f "halucinator.*-n cnc_auto" 2>/dev/null || true
rm -f hal_auto_out.txt

./run_auto.sh > hal_auto_out.txt 2>&1 &
RUN_PID=$!

for _ in $(seq 1 40); do
    if grep -q "AutoPeripheral UART.*Grbl " hal_auto_out.txt 2>/dev/null; then
        break
    fi
    kill -0 "$RUN_PID" 2>/dev/null || break
    sleep 1
done

kill -INT "$RUN_PID" 2>/dev/null || true
sleep 2
pkill -9 -f "halucinator.*-n cnc_auto" 2>/dev/null || true

# Success: the GRBL banner came out via the AUTO-discovered UART, with no
# UART intercept in the config.
if grep -q "AutoPeripheral UART.*Grbl " hal_auto_out.txt \
   && grep -q "AutoPeripheral.*busy-wait" hal_auto_out.txt \
   && ! grep -qE "function:[[:space:]]*usart" cnc_auto_config.yaml; then
    echo "CNC auto-modeling e2e test PASSED - UART auto-discovered, spin-waits auto-broken"
    grep "AutoPeripheral UART.*Grbl " hal_auto_out.txt | sed 's/^/    /' | head -2
    exit 0
else
    echo "CNC auto-modeling e2e test FAILED"
    grep -vE "pkg_resources|UserWarning" hal_auto_out.txt | tail -20
    exit 1
fi
