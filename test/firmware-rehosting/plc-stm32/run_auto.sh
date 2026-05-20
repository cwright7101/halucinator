#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )
cd "$SCRIPT_DIR"
[[ -f PLC.bin && -f plc_addrs.yaml ]] || ./extract.sh
mkdir -p /tmp/plc-stm32_pp; ln -sfn "$SCRIPT_DIR" /tmp/plc-stm32_pp/project
PYTHONPATH=/tmp/plc-stm32_pp PYTHONUNBUFFERED=1 halucinator \
    -c plc_auto_config.yaml -c plc_addrs.yaml -c plc_auto_memory.yaml \
    --emulator unicorn -n plc_auto
