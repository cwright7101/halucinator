#!/usr/bin/env bash
# Regenerate Robot.elf / Robot.bin / robot_addrs.yaml from the P2IM
# real-firmware dataset's prebuilt, unstripped ELF (no cross-compiler
# needed). See PROVENANCE.md. Not committed — run this first.
set -euo pipefail
SCRIPT_DIR=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )
cd "$SCRIPT_DIR"

P2IM_REPO="https://github.com/RiS3-Lab/p2im-real_firmware.git"
P2IM_COMMIT="d4c7456574ce2c2ed038e6f14fea8e3142b3c1f7"
SHARED="../p2im-drone/build/p2im-real_firmware/binary/Robot"
if [[ -f "$SHARED" ]]; then
    SRC_ELF="$SHARED"
else
    if [[ ! -d build/p2im-real_firmware/.git ]]; then
        mkdir -p build
        git clone "$P2IM_REPO" build/p2im-real_firmware
        ( cd build/p2im-real_firmware && git checkout -q "$P2IM_COMMIT" )
    fi
    SRC_ELF="build/p2im-real_firmware/binary/Robot"
fi
cp -f "$SRC_ELF" Robot.elf

python3 - Robot.elf Robot.bin <<'PY'
import sys, struct
from elftools.elf.elffile import ELFFile
e = ELFFile(open(sys.argv[1], "rb")); FLASH = 0x08000000; end = 0; segs = []
for s in e.iter_segments():
    h = s.header
    if h.p_type == "PT_LOAD" and h.p_filesz:
        segs.append((h.p_paddr, s.data()[:h.p_filesz]))
        end = max(end, h.p_paddr - FLASH + h.p_filesz)
img = bytearray(end)
for lma, d in segs:
    img[lma - FLASH: lma - FLASH + len(d)] = d
open(sys.argv[2], "wb").write(img)
sp, pc = struct.unpack("<II", img[:8])
print(">>> Robot.bin = 0x%x bytes  init_sp=0x%08x  reset_pc=0x%08x" % (len(img), sp, pc))
PY

hal_make_addr -b Robot.elf -o robot_addrs.yaml
echo ">>> ready: ./run_auto.sh"
