#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )
cd "$SCRIPT_DIR"
[[ -f Steering.bin && -f steering_addrs.yaml ]] || ./extract.sh
mkdir -p /tmp/steering-sam3x_pp; ln -sfn "$SCRIPT_DIR" /tmp/steering-sam3x_pp/project
PYTHONPATH=/tmp/steering-sam3x_pp PYTHONUNBUFFERED=1 halucinator \
    -c steering_auto_config.yaml -c steering_addrs.yaml -c steering_auto_memory.yaml \
    --emulator unicorn -n steering_auto
