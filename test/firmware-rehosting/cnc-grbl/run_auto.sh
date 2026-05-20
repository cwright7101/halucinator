#!/usr/bin/env bash
# Auto-modeling run: boot CNC/GRBL with the AutoPeripheral catch-all
# (cnc_auto_memory.yaml) instead of hand-written MMIO intercepts. The
# AutoPeripheral breaks the clock/USART spin-waits and auto-discovers the
# USART data register, surfacing the GRBL console; the unicorn backend's
# skip_svc steps over P2IM's aflCall. Only non-MMIO setup is stubbed in
# cnc_auto_config.yaml. See docs/auto-peripheral-modeling.md.
set -euo pipefail

SCRIPT_DIR=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )
cd "$SCRIPT_DIR"

if [[ ! -f CNC.bin || ! -f cnc_addrs.yaml ]]; then
    ./extract.sh
fi

mkdir -p /tmp/cnc_pythonpath
ln -sfn "$SCRIPT_DIR" /tmp/cnc_pythonpath/project

PYTHONPATH=/tmp/cnc_pythonpath PYTHONUNBUFFERED=1 halucinator \
    -c cnc_auto_config.yaml \
    -c cnc_addrs.yaml \
    -c cnc_auto_memory.yaml \
    --emulator unicorn \
    -n cnc_auto
