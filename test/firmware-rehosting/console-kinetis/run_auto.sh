#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )
cd "$SCRIPT_DIR"
[[ -f Console.bin && -f console_addrs.yaml ]] || ./extract.sh
mkdir -p /tmp/console-kinetis_pp; ln -sfn "$SCRIPT_DIR" /tmp/console-kinetis_pp/project
PYTHONPATH=/tmp/console-kinetis_pp PYTHONUNBUFFERED=1 halucinator \
    -c console_auto_config.yaml -c console_addrs.yaml -c console_auto_memory.yaml \
    --emulator unicorn -n console_auto
