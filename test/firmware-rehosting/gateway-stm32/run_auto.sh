#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )
cd "$SCRIPT_DIR"
[[ -f Gateway.bin && -f gateway_addrs.yaml ]] || ./extract.sh
mkdir -p /tmp/gateway-stm32_pp; ln -sfn "$SCRIPT_DIR" /tmp/gateway-stm32_pp/project
PYTHONPATH=/tmp/gateway-stm32_pp PYTHONUNBUFFERED=1 halucinator \
    -c gateway_auto_config.yaml -c gateway_addrs.yaml -c gateway_auto_memory.yaml \
    --emulator unicorn -n gateway_auto
