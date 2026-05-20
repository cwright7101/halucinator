#!/usr/bin/env bash
# E2E rehosting test for the GRBL CNC controller. Boots the firmware under
# the in-process unicorn backend and asserts the real GRBL console output
# (settings dump + startup banner) is produced.
set -uo pipefail

SCRIPT_DIR=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )
cd "$SCRIPT_DIR"

if [[ ! -f CNC.bin || ! -f cnc_addrs.yaml ]]; then
    ./extract.sh
fi

pkill -9 -f "halucinator.*-n cnc" 2>/dev/null || true
rm -f hal_out.txt

HAL_EMULATOR="${HAL_EMULATOR:-unicorn}" ./run.sh > hal_out.txt 2>&1 &
RUN_PID=$!

# Wait up to 40s for the banner (or the run to die).
banner=""
for _ in $(seq 1 40); do
    if grep -q "Grbl " hal_out.txt 2>/dev/null; then
        banner=1
        break
    fi
    kill -0 "$RUN_PID" 2>/dev/null || break
    sleep 1
done

kill "$RUN_PID" 2>/dev/null || true
pkill -9 -f "halucinator.*-n cnc" 2>/dev/null || true

# Success: GRBL settings dump ($N=...) AND the startup banner.
if grep -q "Grbl " hal_out.txt && grep -qE '\$0=.*step/mm' hal_out.txt; then
    echo "CNC GRBL e2e test PASSED - firmware booted and emitted GRBL console"
    grep -E "Grbl |\\\$0=" hal_out.txt | sed 's/^/    /' | head -3
    exit 0
else
    echo "CNC GRBL e2e test FAILED - no GRBL banner/settings in output"
    grep -vE "pkg_resources|UserWarning" hal_out.txt | tail -20
    exit 1
fi
