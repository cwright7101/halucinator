#!/usr/bin/env bash
# Regenerate the rehosting inputs (CNC.elf, CNC.bin, cnc_addrs.yaml) for
# the GRBL CNC controller from the P2IM real-firmware dataset.
#
# The dataset ships prebuilt, unstripped ARM ELFs, so no cross-compiler
# is needed: we copy the ELF, carve a flat flash image from its PT_LOAD
# segments, and regenerate the symbol map with hal_make_addr. The ELF /
# bin / addrs are not committed (see PROVENANCE.md) — run this first.
set -euo pipefail

SCRIPT_DIR=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )
cd "$SCRIPT_DIR"

P2IM_REPO="https://github.com/RiS3-Lab/p2im-real_firmware.git"
P2IM_COMMIT="d4c7456574ce2c2ed038e6f14fea8e3142b3c1f7"
BUILD_DIR="build/p2im-real_firmware"

# Reuse the p2im-drone clone if present, else clone the pinned commit.
SHARED="../p2im-drone/build/p2im-real_firmware/binary/CNC"
if [[ -f "$SHARED" ]]; then
    SRC_ELF="$SHARED"
else
    if [[ ! -d "$BUILD_DIR/.git" ]]; then
        mkdir -p build
        git clone "$P2IM_REPO" "$BUILD_DIR"
        ( cd "$BUILD_DIR" && git checkout -q "$P2IM_COMMIT" )
    fi
    SRC_ELF="$BUILD_DIR/binary/CNC"
fi

cp -f "$SRC_ELF" CNC.elf
echo ">>> using prebuilt ELF: $SRC_ELF"

# Carve a flat flash image (base 0x08000000) from the ELF LOAD segments.
python3 - CNC.elf CNC.bin <<'PY'
import sys, struct
from elftools.elf.elffile import ELFFile
elf_path, bin_path = sys.argv[1], sys.argv[2]
e = ELFFile(open(elf_path, "rb"))
FLASH = 0x08000000
end = 0
segs = []
for s in e.iter_segments():
    h = s.header
    if h.p_type == "PT_LOAD" and h.p_filesz > 0:
        lma = h.p_paddr
        data = s.data()[:h.p_filesz]
        segs.append((lma, data))
        end = max(end, lma - FLASH + len(data))
img = bytearray(end)
for lma, data in segs:
    img[lma - FLASH: lma - FLASH + len(data)] = data
open(bin_path, "wb").write(img)
sp, pc = struct.unpack("<II", img[:8])
print(">>> CNC.bin = 0x%x bytes  init_sp=0x%08x  reset_pc=0x%08x" % (len(img), sp, pc))
PY

hal_make_addr -b CNC.elf -o cnc_addrs.yaml
echo ">>> wrote cnc_addrs.yaml"
echo ">>> ready: ./run.sh"
