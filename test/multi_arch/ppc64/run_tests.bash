#!/usr/bin/env bash

set -e
set -x
# Clean up any leftover processes from previous tests
pkill -9 -f qemu-system-ppc64 2>/dev/null || true
pkill -9 -f halucinator 2>/dev/null || true
pkill -9 -f hal_dev_uart 2>/dev/null || true
pkill -9 -f gdb-multiarch 2>/dev/null || true
sleep 2

rm -f ./hal_out.txt ./test_out.txt

# Run halucinator
PYTHONUNBUFFERED=1 HALUCINATOR_QEMU_PPC64="${HALUCINATOR_QEMU_PPC64}" \
  ./test/multi_arch/ppc64/run.sh </dev/null >hal_out.txt 2>&1 &
HAL_PID=$!

# Wait for firmware UART prompt
TIMEOUT=120
ELAPSED=0
while ! grep -q "Multi-Arch UART Test" ./hal_out.txt 2>/dev/null; do
    sleep 2
    ELAPSED=$((ELAPSED + 2))
    if [ $ELAPSED -ge $TIMEOUT ]; then
        echo "TIMEOUT waiting for halucinator to reach UART prompt"
        cat ./hal_out.txt
        kill $HAL_PID 2>/dev/null || true
        exit 1
    fi
done

# Use Python to send input via zmq and read output
python3 -c "
from halucinator.external_devices.ioserver import IOServer
from halucinator.external_devices.uart import UARTPrintServer
import time, sys

io = IOServer(5556, 5555)
uart = UARTPrintServer(io)
io.start()

# Wait for zmq subscription to propagate
time.sleep(3)

# Send '1234567890' as the UART input
uart.send_data(0x40013800, '1234567890')
print('Sent input via zmq', file=sys.stderr)

# Wait for response and collect output
time.sleep(15)
io.shutdown()
" 2>&1 &
SENDER_PID=$!

# Wait for expected output in hal_out.txt
function check_output {
    until grep -q "Example Finished" ./hal_out.txt 2>/dev/null; do
        sleep 1
    done
}

export -f check_output
if ! timeout 3m bash -c check_output; then
    echo "TIMEOUT waiting for 'Example Finished'"
    echo "=== hal_out.txt (last 50 lines) ==="
    tail -50 ./hal_out.txt || true
    kill $SENDER_PID 2>/dev/null || true
    kill $HAL_PID 2>/dev/null || true
    pkill -f qemu-system-ppc64 2>/dev/null || true
    exit 1
fi

# Clean up
kill $SENDER_PID 2>/dev/null || true
kill $HAL_PID 2>/dev/null || true
pkill -f qemu-system-ppc64 2>/dev/null || true
echo "PPC64 UART e2e test PASSED"
