#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )
cd "$SCRIPT_DIR"
[[ -f Heat.bin && -f heat_addrs.yaml ]] || ./extract.sh
mkdir -p /tmp/heatpress-sam3x_pp; ln -sfn "$SCRIPT_DIR" /tmp/heatpress-sam3x_pp/project
PYTHONPATH=/tmp/heatpress-sam3x_pp PYTHONUNBUFFERED=1 halucinator \
    -c heat_auto_config.yaml -c heat_addrs.yaml -c heat_auto_memory.yaml \
    --emulator unicorn -n heat_auto
