#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )
cd "$SCRIPT_DIR"
SHARED="../p2im-drone/build/p2im-real_firmware/binary/Gateway"
if [[ -f "$SHARED" ]]; then SRC_ELF="$SHARED"; else
  if [[ ! -d build/p2im-real_firmware/.git ]]; then mkdir -p build
    git clone https://github.com/RiS3-Lab/p2im-real_firmware.git build/p2im-real_firmware
    ( cd build/p2im-real_firmware && git checkout -q d4c7456574ce2c2ed038e6f14fea8e3142b3c1f7 ); fi
  SRC_ELF="build/p2im-real_firmware/binary/Gateway"; fi
cp -f "$SRC_ELF" Gateway.elf
python3 - Gateway.elf Gateway.bin <<'EOF'
import sys,struct
from elftools.elf.elffile import ELFFile
e=ELFFile(open(sys.argv[1],'rb')); segs=[]
for s in e.iter_segments():
    h=s.header
    if h.p_type=='PT_LOAD' and h.p_filesz: segs.append((h.p_paddr,s.data()[:h.p_filesz]))
base=min(p for p,_ in segs); end=max(p-base+len(d) for p,d in segs)
img=bytearray(end)
for p,d in segs: img[p-base:p-base+len(d)]=d
open(sys.argv[2],'wb').write(img)
print(">>> %s 0x%x bytes"%(sys.argv[2],len(img)))
EOF
hal_make_addr -b Gateway.elf -o gateway_addrs.yaml
echo ">>> ready: ./run_auto.sh"
