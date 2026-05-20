#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )
cd "$SCRIPT_DIR"
[[ -f Reflow.bin && -f reflow_addrs.yaml ]] || ./extract.sh
mkdir -p /tmp/reflow-oven-stm32_pp; ln -sfn "$SCRIPT_DIR" /tmp/reflow-oven-stm32_pp/project
PYTHONPATH=/tmp/reflow-oven-stm32_pp PYTHONUNBUFFERED=1 halucinator \
    -c reflow_auto_config.yaml -c reflow_addrs.yaml -c reflow_auto_memory.yaml \
    --emulator unicorn -n reflow_auto
