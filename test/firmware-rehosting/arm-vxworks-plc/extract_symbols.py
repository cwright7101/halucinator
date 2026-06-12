#!/usr/bin/env python3
"""Extract the in-image VxWorks symbol table from a flat firmware image -> CSV.

VxWorks images carry a built-in symbol table (an array of fixed-stride records:
next@+0, name_ptr@+4, value@+8, group@+0x10, type@+0x12). Recovering it converts
a symbol-less ARM blob into named functions, which is what every HALucinator
intercept keys on. With names you can write `function: logMsg` in a config and let
the loader resolve the address from this CSV (drop most hardcoded addresses).

Nothing here is firmware-specific: the load base is a flag, and the symbol table
is auto-located by signature (or given explicitly). For the example image, the
README documents the one value you need (`--base`).

Usage:
    python3 extract_symbols.py firmware.bin --base 0x20010000 -o symbols.csv
    # or pin the table explicitly if auto-scan misses:
    python3 extract_symbols.py firmware.bin --base 0x20010000 \
            --symtab 0x3c8d14:0x41c068 -o symbols.csv

Output rows: "name,first_addr,last_addr" (range = gap to the next symbol, so a
PC inside a function resolves to its containing symbol).
"""
from __future__ import annotations

import argparse
import re
import struct
import sys
from typing import Optional, Tuple

_SAN = lambda s: re.sub(r"[^A-Za-z0-9_.$:<>]", "_", s)[:200]


def _u32(data: bytes, off: int) -> Optional[int]:
    return struct.unpack_from("<I", data, off)[0] if 0 <= off <= len(data) - 4 else None


def _name_at(data: bytes, base: int, name_ptr: int, maxlen: int = 220) -> Optional[str]:
    o = name_ptr - base
    if not (0 <= o < len(data)):
        return None
    s = o
    while s > 0 and data[s - 1] != 0 and 31 < data[s - 1] < 127:
        s -= 1
    e = s
    while e < len(data) and data[e] != 0 and 31 < data[e] < 127 and e - s < maxlen:
        e += 1
    return data[s:e].decode("ascii", "replace") if e > s else None


def _entry_valid(data: bytes, base: int, off: int) -> bool:
    """A plausible symtab record: name_ptr points at printable ASCII in-image,
    value is at/above the load base."""
    if off + 0x13 > len(data):
        return False
    np = _u32(data, off + 4)
    val = _u32(data, off + 8)
    if np is None or val is None or val < base or not (base <= np < base + len(data)):
        return False
    so = np - base
    return 0 <= so < len(data) and 32 < data[so] < 127


def find_symtab(data: bytes, base: int, stride: int, min_run: int,
                gap_tol: int = 24) -> Optional[Tuple[int, int]]:
    """Locate the longest run of valid stride-byte records. The real table is
    contiguous but a few entries (.bss-valued symbols, padding) fail the cheap
    heuristic, so we tolerate up to `gap_tol` consecutive misses within a run."""
    n = len(data)
    best = (0, 0, 0)   # (valid_count, start, end)
    o = 0
    while o + stride <= n:
        if not _entry_valid(data, base, o):
            o += 4
            continue
        start, cnt, gaps, last_valid = o, 0, 0, o
        while o + stride <= n:
            if _entry_valid(data, base, o):
                cnt += 1
                last_valid = o
                gaps = 0
            else:
                gaps += 1
                if gaps > gap_tol:
                    break
            o += stride
        if cnt > best[0]:
            best = (cnt, start, last_valid + stride)
        o = max(o, last_valid + stride)      # don't rescan this run
    return (best[1], best[2]) if best[0] >= min_run else None


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("firmware", help="flat firmware image (.bin)")
    ap.add_argument("--base", type=lambda x: int(x, 0), default=0x20010000,
                    help="image load base VA (default 0x20010000)")
    ap.add_argument("-o", "--out", default="symbols.csv")
    ap.add_argument("--symtab", default=None,
                    help="pin the table as START:END file offsets (else auto-scan)")
    ap.add_argument("--stride", type=lambda x: int(x, 0), default=20)
    ap.add_argument("--min-run", type=int, default=500,
                    help="min consecutive records for auto-scan to accept a table")
    args = ap.parse_args()

    data = open(args.firmware, "rb").read()
    n = len(data)

    if args.symtab:
        a, b = args.symtab.split(":")
        start, end = int(a, 0), int(b, 0)
    else:
        found = find_symtab(data, args.base, args.stride, args.min_run)
        if not found:
            sys.stderr.write("could not auto-locate a VxWorks symbol table; pass "
                             "--symtab START:END (and check --base)\n")
            return 2
        start, end = found
        sys.stderr.write(f"auto-located symtab at file 0x{start:x}..0x{end:x}\n")

    byval = {}
    for off in range(start, end, args.stride):
        np = _u32(data, off + 4)
        val = _u32(data, off + 8)
        if np is None or val is None or val < args.base or (val - args.base) >= n:
            continue
        if val & 1:                          # skip odd/thumb (ARM image)
            continue
        nm = _name_at(data, args.base, np)
        if nm and 0 < len(nm) <= 200:
            byval.setdefault(val, _SAN(nm))

    addrs = sorted(byval)
    with open(args.out, "w") as f:
        for i, a in enumerate(addrs):
            nxt = addrs[i + 1] if i + 1 < len(addrs) else a + 0x40
            f.write("%s,0x%08x,0x%08x\n" % (byval[a], a, max(nxt - 1, a)))
    print("wrote %s: %d symbols (base 0x%08x)" % (args.out, len(addrs), args.base))
    return 0


if __name__ == "__main__":
    sys.exit(main())
