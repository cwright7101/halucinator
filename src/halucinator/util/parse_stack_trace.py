#!/usr/bin/python3

from __future__ import annotations

import dataclasses
import re
from typing import Dict, List, Optional

import gtirb
from gtirb_capstone.instructions import GtirbInstructionDecoder
from gtirb_functions import Function

import halucinator.hal_log as hal_log_conf
from halucinator.util import gtirb_common

hal_log = hal_log_conf.getHalLogger()


@dataclasses.dataclass
class StackFrame:
    """Data about a function on the call stack."""

    address: int
    """Address of the last instruction executed in this function."""
    name: str
    """Name of this function."""


class StackTraceParser(object):
    def __init__(
        self,
        outfile: str,
        log_file: str,
        base_address: int,
        gtirb_ir: gtirb.IR,
        functions: List[Function],
        assembly_path: str,
    ) -> None:
        """
        Initialize stack trace variables used during coverage log parsing.
        """
        self.base_address: int = base_address
        self.trace_output: str = outfile
        self.gtirb_ir: gtirb.IR = gtirb_ir
        self.assembly_path: str = assembly_path
        self.log_file: str = log_file
        self.functions: List[Function] = functions

        self.log_index: int = 0
        """Current line of self.log_file to be parsed."""

        self.got_func_exit: bool = False
        """Flag used to indicate when we have reached the end of a function."""

        self.stack_record: List[StackFrame] = []
        """
        Ordered list of stack frames used to represent the stack trace.
        The bottom of stack_record represents the top of the stack.
        """

        self.function_blocks: Dict[gtirb.CodeBlock, Function] = {}
        """Maps code block UUID's to GTIRB Functions."""

        self.function_entries: Dict[int, Function] = {}
        """Maps addresses of function entry instructions to Functions."""

        self.function_exits: Dict[int, Function] = {}
        """Maps addresses of function exit instructions to Functions."""

        # Populate the function maps
        isa = gtirb_ir.modules[0].isa
        decoder = GtirbInstructionDecoder(isa)
        for module in gtirb_ir.modules:
            for function in Function.build_functions(module):
                for block in function.get_all_blocks():
                    self.function_blocks[block] = function
                for block in function.get_entry_blocks():
                    if block.address is None:
                        raise SyntaxError(
                            "Function entry block has no address!"
                        )
                    self.function_entries[block.address] = function
                for block in function.get_exit_blocks():
                    if block.address is None:
                        raise SyntaxError(
                            "Function exit block has no address!"
                        )
                    for instruction in decoder.get_instructions(block):
                        instr_end = instruction.address + instruction.size
                        block_end = block.address + block.size
                        if instr_end == block_end:
                            # We found the exit edge instruction (I think)
                            self.function_exits[instruction.address] = function
                            break

    def get_function_on(self, address: int) -> Optional[Function]:
        """
        Get a function containing address (if one exists)

        If multiple functions overlap at the same address,
        this will return the first function found.
        """
        # TODO: Handle multiple blocks/functions overlapping at the same address
        for block in self.gtirb_ir.code_blocks_on(address):
            function = self.function_blocks.get(block)
            if function:
                return function
        return None

    def is_function_entry(self, function: Function, address: int) -> bool:
        """
        Determine if the instruction at address is an entrypoint to function
        """
        return self.function_entries.get(address) == function

    def is_function_exit(self, function: Function, address: int) -> bool:
        """
        Determine if the instruction at address is an exit from function
        """
        return self.function_exits.get(address) == function

    def get_next_address(self, log_contents: List[str]) -> Optional[int]:
        """
        Get the next available address from a newline separated list of coverage log contents.

        This function will set self.log_index to the index of the returned address,
        or len(log_contents) if no address is found.

        If self.log_index already points to an address,
        this function will return the address at self.log_index without advancing the counter.
        """
        while self.log_index < len(log_contents):
            line = log_contents[self.log_index].strip()
            if not line:
                self.log_index += 1
                continue

            # Search for 32/64-bit address values
            addr_re = re.compile("^0x([0-9a-f]{8,16}): ")
            if not addr_re.match(line):
                self.log_index += 1
                continue

            addr = int(line.split(":")[0], 16)
            return addr - self.base_address
        return None

    # Example input:
    # ----------------
    # IN:
    # 0x0800081e:  429a       cmp      r2, r3
    def parse_log_loop(
        self, stack_record: List[StackFrame], log_contents: List[str],
    ) -> List[StackFrame]:
        """
        Main loop for parsing a code coverage log into an ordered list of stack frames.
        """
        # Resume parsing from the top of the stack (bottom of the record)
        addr = self.get_next_address(log_contents)

        while addr is not None:
            function = self.get_function_on(addr)
            if not function:
                hal_log.warning(f"Cannot find function. {hex(addr)}")
                self.log_index += 1
                continue

            new_function_entry = stack_record == [] or self.is_function_entry(
                function, addr
            )
            function_exit = self.is_function_exit(function, addr)

            # The current function does not match the top of the stack,
            # and no entry/exit events have been detected.
            if (
                not new_function_entry
                and not self.got_func_exit
                and stack_record[-1].name != function.get_name()
            ):
                if (len(stack_record) > 1) and (
                    stack_record[-2].name == function.get_name()
                ):
                    # Assume we missed an exit.
                    hal_log.warning(
                        f"Function exited without event. {hex(addr)}"
                    )
                    new_function_entry = False
                    self.got_func_exit = True
                else:
                    # Assume we missed an entry.
                    hal_log.warning(
                        f"Function entered without event. {hex(addr)}"
                    )
                    new_function_entry = True
                    self.got_func_exit = False

            # We have exited a function layer, pop the top of the stack.
            if self.got_func_exit:
                stack_record.pop()
                self.got_func_exit = False

            # We have entered a new function, add it to the stack.
            if new_function_entry:
                stack_record.append(StackFrame(addr, function.get_name()))

            # The PC is pointing to the last instruction in this function.
            # Make sure we exit this function in our next iteration.
            if function_exit:
                self.got_func_exit = True

            # Update the address at the top of the stack
            if len(stack_record):
                stack_record[-1].address = addr
            # Move on to the next address in the log
            self.log_index += 1
            addr = self.get_next_address(log_contents)

        return stack_record

    def parse_log(
        self, stack_record: List[StackFrame], pc: Optional[int]
    ) -> List[StackFrame]:
        """
        Parse a coverage log into a stack trace approximation
        consisting of a list of address values and function names
        organized with the highest function level in the lowest index
        """
        log_contents = []
        with open(self.log_file) as f:
            log_contents = f.readlines()

        # Make sure we don't duplicate the last PC entry
        addr = self.get_next_address(log_contents)
        if len(stack_record) and stack_record[-1].address == addr:
            self.log_index += 1

        # Make sure the current PC is included in the traces
        if pc is not None:
            pc = pc & 0xFFFFFFFE  # Clear Thumb bit
            log_contents.append(f"0x{pc:016x}:  pc")

        return self.parse_log_loop(stack_record, log_contents)

    def refresh(self, pc: Optional[int]) -> None:
        """
        Update the stack trace output file
        """
        self.stack_record = self.parse_log(self.stack_record, pc)
        with open(self.trace_output, "w") as f:
            f.write(str(self.stack_record))


if __name__ == "__main__":
    from argparse import ArgumentParser

    p = ArgumentParser()
    p.add_argument(
        "-o",
        "--output",
        type=str,
        required=True,
        help="Path to stack trace output",
    )
    p.add_argument(
        "-l", "--log", type=str, required=True, help="Path to QEMU log"
    )
    p.add_argument(
        "-i", "--ir", type=str, required=True, help="Path to GTIRB IR"
    )
    p.add_argument(
        "-s", "--asm", type=str, required=True, help="Path to assembly"
    )
    p.add_argument(
        "--base-address",
        type=int,
        default=0,
        help="Base address of the binary",
    )

    args = p.parse_args()

    gtirb_ir: gtirb.IR = gtirb.IR.load_protobuf(args.ir)
    functions: List[Function] = gtirb_common.get_functions(gtirb_ir)
    parser = StackTraceParser(
        args.output, args.log, args.base_address, gtirb_ir, functions, args.asm
    )
    parser.refresh(None)
