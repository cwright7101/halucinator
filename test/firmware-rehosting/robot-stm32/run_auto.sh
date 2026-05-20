#!/usr/bin/env bash
# Auto-modeling rehost of the P2IM self-balancing-robot firmware
# (STM32F103, Cortex-M3). AutoPeripheral breaks the MMIO spin-waits and
# auto-discovers the UART; skip_svc handles aflCall. See
# docs/auto-peripheral-modeling.md.
set -euo pipefail
SCRIPT_DIR=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )
cd "$SCRIPT_DIR"
[[ -f Robot.bin && -f robot_addrs.yaml ]] || ./extract.sh
mkdir -p /tmp/robot_pythonpath
ln -sfn "$SCRIPT_DIR" /tmp/robot_pythonpath/project
PYTHONPATH=/tmp/robot_pythonpath PYTHONUNBUFFERED=1 halucinator \
    -c robot_auto_config.yaml \
    -c robot_addrs.yaml \
    -c robot_auto_memory.yaml \
    --emulator unicorn \
    -n robot_auto
