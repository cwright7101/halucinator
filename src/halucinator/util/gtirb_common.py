#!/usr/bin/python3

from __future__ import annotations

import subprocess
from typing import List

import gtirb
from gtirb_functions import Function


def generate_gtirb(bin_path: str, gtirb_path: str) -> None:
    """
    Generate GTIRB from binary
    """
    proc = subprocess.run(["ddisasm", bin_path, "--ir", gtirb_path,])
    if proc.returncode:
        exit(proc.returncode)


def get_functions(ir: gtirb.IR) -> List[Function]:
    functions: List[Function] = []
    for module in ir.modules:
        functions.extend(Function.build_functions(module))
    return functions


def generate_assembly(assembly_path: str, gtirb_path: str) -> None:
    """
    Print an assembly file with address information from GTIRB
    """
    proc = subprocess.run(
        [
            "gtirb-pprinter",
            "--asm",
            assembly_path,
            "--listing-mode=ui",
            gtirb_path,
        ]
    )
    if proc.returncode:
        exit(proc.returncode)
