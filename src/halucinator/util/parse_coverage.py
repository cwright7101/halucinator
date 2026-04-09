#!/usr/bin/python3

from __future__ import annotations

import os
import re
import dataclasses
from enum import Enum, auto
from typing import Dict, List, TextIO, Optional

import gtirb
from gtirb_functions import Function
import halucinator.hal_log as hal_log_conf

hal_log = hal_log_conf.getHalLogger()

# Enum used to indicate whether a line of assembly is expected to be executable
class CodeStatus(Enum):
    NotCode = auto()
    ReachableCode = auto()
    UnreachableCode = auto()


# Coverage information for a single line of assembly
@dataclasses.dataclass
class LineCoverageInfo:
    asm_line: int
    status: CodeStatus
    covered: bool = False


# Coverage information for a function
@dataclasses.dataclass
class FunctionCoverageInfo:
    asm_line: int
    name: str
    covered: bool = False


class CoverageParser(object):
    def code_status_at_address(
        self, module: gtirb.Module, address: int
    ) -> CodeStatus:
        """
        Determines the "executable" status (reachable, unreachable, not code) at an address
        """
        result = CodeStatus.NotCode
        reachable_aux = module.aux_data.get("reachableCode")

        for block in module.code_blocks_on(address):
            if not reachable_aux or block in reachable_aux.data:
                result = CodeStatus.ReachableCode
            else:
                result = CodeStatus.UnreachableCode

        return result

    def extract_line_coverage_map(
        self, assembly_path: str, module: gtirb.Module
    ) -> Dict[int, LineCoverageInfo]:
        """
        Parse an assembly file with address information into a dictionary that maps addresses to code coverage info
        """
        addr_to_cov: Dict[int, LineCoverageInfo] = {}
        addr_re = re.compile("# EA: (0x[0-9a-f]+)$")

        with open(assembly_path, "r") as f:
            for lineno, line in enumerate(f):
                m = addr_re.search(line)
                if m:
                    addr = int(m[1], 16)
                    status = self.code_status_at_address(module, addr)
                    addr_to_cov[addr] = LineCoverageInfo(lineno + 1, status)

        return addr_to_cov

    def extract_function_coverage_map(
        self,
        functions: List[Function],
        addr_to_line: Dict[int, LineCoverageInfo],
    ) -> Dict[int, FunctionCoverageInfo]:
        """
        Map function entry addresses to function coverage info
        """
        addr_to_cov: Dict[int, FunctionCoverageInfo] = {}

        for func in functions:
            blocks_to_syms = {sym.referent: sym for sym in func.name_symbols}
            entry_blocks = sorted(
                func.get_entry_blocks() & set(blocks_to_syms.keys()),
                key=lambda b: -1 if b.address is None else b.address,
            )

            if entry_blocks:
                # Pick the lowest entry block to represent the function, just to have
                # a deterministic result.
                best_entry_block = entry_blocks[0]
                assert best_entry_block.address
                info = addr_to_line.get(best_entry_block.address)
                assert info

                sym = blocks_to_syms[best_entry_block]
                addr_to_cov[best_entry_block.address] = FunctionCoverageInfo(
                    info.asm_line, sym.name
                )

        return addr_to_cov

    def __init__(
        self,
        outfile: str,
        log_path: str,
        bin_path: str,
        base_address: int,
        gtirb_ir: gtirb.IR,
        functions: List[Function],
        assembly_path: str,
    ) -> None:
        """
        Initialize code coverage variables used during coverage log parsing.
        """
        self.coverage_output: str = outfile
        self.log_path: str = log_path
        self.target: str = os.path.basename(bin_path)
        self.base_address: int = base_address
        self.gtirb_ir: gtirb.IR = gtirb_ir
        self.gtirb_module: gtirb.Module = gtirb_ir.modules[0]
        self.assembly_path: str = assembly_path
        self.ln_coverage_map: Dict[int, LineCoverageInfo] = self.extract_line_coverage_map(
            self.assembly_path, self.gtirb_module
        )
        self.fn_coverage_map: Dict[int, FunctionCoverageInfo] = self.extract_function_coverage_map(
            functions, self.ln_coverage_map
        )

        self.log_index: int = 0
        """Current line of self.log_file to be parsed."""

    # Example input:
    # ----------------
    # IN:
    # 0x0000004000ce23de:  mov    %ebp,%eax
    # 0x0000004000ce23e0:  pop    %rbx
    # 0x0000004000ce23e1:  pop    %rbp
    # 0x0000004000ce23e2:  pop    %r12
    # 0x0000004000ce23e4:  retq
    def parse_log(self, log_contents: str) -> None:
        """
        Parse a "-d in_asm" log from QEMU into function and line coverage maps
        """
        log_lines = log_contents.split("\n")
        while self.log_index < len(log_lines):
            line = log_lines[self.log_index]
            self.log_index += 1

            # Search for 32/64-bit address values
            addr_re = re.compile("^0x([0-9a-f]{8,16}): ")
            if not addr_re.match(line):
                continue

            addr = int(line.split(":")[0], 16)
            addr = addr - self.base_address
            if addr not in self.ln_coverage_map.keys():
                hal_log.warning(
                    f"Executed line at unknown address: {hex(addr)}"
                )
                continue
            self.ln_coverage_map[addr].covered = True

            if addr not in self.fn_coverage_map.keys():
                continue
            self.fn_coverage_map[addr].covered = True

    def get_lcov_func_str(self, info: FunctionCoverageInfo) -> str:
        """
        Generate an LCOV formatted function coverage string
        """
        return (
            f"FN:{info.asm_line},{info.name}\n"
            f"FNDA:{int(info.covered)},{info.name}\n"
        )

    def get_lcov_line_str(
        self, address: int, info: LineCoverageInfo
    ) -> Optional[str]:
        """
        Generate an LCOV formatted coverage string for a single assembly line
        """
        covered = int(info.covered)
        code_status = info.status

        if code_status == CodeStatus.NotCode and covered:
            hal_log.warning(
                "data at %x is covered", address,
            )
        elif code_status == CodeStatus.UnreachableCode and covered:
            hal_log.warning(
                "unreachable code at %x is covered", address,
            )
        elif code_status == CodeStatus.UnreachableCode:
            # Use -1 to indicate that a line was considered unreachable. This
            # isn't really valid lcov, but we just want it for the VS Code
            # gutters.
            covered = -1

        if code_status != CodeStatus.NotCode or covered:
            return f"DA:{info.asm_line},{covered}\n"
        return None

    def write_lcov_record(
        self,
        f: TextIO,
        assembly_path: str,
        ln_coverage_info: Dict[int, LineCoverageInfo],
        fn_coverage_info: Dict[int, FunctionCoverageInfo],
    ) -> None:
        """
        Writes a single lcov record to a file. The record contains coverage for
        a single gtirb module.
        """
        # See http://ltp.sourceforge.net/coverage/lcov/geninfo.1.php for the spec.

        # The spec says that the source file must be an absolute path, but it
        # doesn't seem to be the case in practice.
        f.write(f"SF:{assembly_path}\n")

        for fn_info in fn_coverage_info.values():
            func_str = self.get_lcov_func_str(fn_info)
            f.write(func_str)

        for ea, ln_info in ln_coverage_info.items():
            line_str = self.get_lcov_line_str(ea, ln_info)
            if line_str:
                f.write(line_str)

        f.write("end_of_record\n\n")

    def refresh(self) -> None:
        """
        Update the coverage output file using coverage information configured in init_coverage
        """
        log_contents = ""
        with open(self.log_path, "r", encoding="utf-8") as f:
            log_contents = f.read()

        self.parse_log(log_contents)
        with open(self.coverage_output, "w") as f:
            self.write_lcov_record(
                f,
                self.assembly_path,
                self.ln_coverage_map,
                self.fn_coverage_map,
            )
