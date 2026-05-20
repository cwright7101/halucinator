#!/usr/bin/env bash
# Rehost the GRBL CNC controller (P2IM real-firmware dataset) under the
# in-process unicorn backend. CNC.elf / CNC.bin / cnc_addrs.yaml are
# produced by extract.sh from the dataset's prebuilt, unstripped ELF.
set -euo pipefail

SCRIPT_DIR=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )
cd "$SCRIPT_DIR"

if [[ ! -f CNC.bin || ! -f cnc_addrs.yaml ]]; then
    echo ">>> CNC.bin / cnc_addrs.yaml missing — run ./extract.sh first"
    exit 1
fi

# Map this dir to the importable `project` package so the
# project.bp_handlers.* intercept classes resolve.
mkdir -p /tmp/cnc_pythonpath
ln -sfn "$SCRIPT_DIR" /tmp/cnc_pythonpath/project

PYTHONPATH=/tmp/cnc_pythonpath PYTHONUNBUFFERED=1 halucinator \
    -c cnc_config.yaml \
    -c cnc_addrs.yaml \
    -c cnc_memory.yaml \
    --emulator "${HAL_EMULATOR:-unicorn}" \
    -n cnc
