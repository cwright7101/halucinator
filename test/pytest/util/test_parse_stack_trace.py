"""
Unit tests for stack trace parsing
"""

import os
import tempfile
from typing import List
from unittest import mock

import gtirb

import halucinator.util.gtirb_common as gtirb_common
from halucinator.util.parse_stack_trace import StackTraceParser

script_dir = os.path.dirname(os.path.realpath(__file__))
target_asm_path = os.path.join(script_dir, "test-exes", "test-arm.s")
target_gtirb_path = os.path.join(script_dir, "test-exes", "test-arm.gtirb")

main_entry = 0x8018
main_exit = 0x8020
main_after_imm_ret = 0x801C
layered_imm_ret_entry = 0x8254
layered_imm_ret_exit = 0x8258
imm_ret_address = 0x8250


class TestHalLog:
    def _extend_log(self, address_list: List[int], log_path: str) -> None:
        with open(log_path, "a") as f:
            f.write("----------------\nIN:\n")
            for address in address_list:
                f.write(f"0x{address:016x}:  nop\n")

    def _generate_log(
        self, address_list: List[int]
    ) -> tempfile.NamedTemporaryFile:
        log_file = tempfile.NamedTemporaryFile(mode="w+")
        self._extend_log(address_list, log_file.name)
        return log_file

    def test_parse_single_trace(self) -> None:
        global target_gtirb_path, target_asm_path
        trace_output = tempfile.NamedTemporaryFile(mode="w+")
        log_file = self._generate_log([main_entry])
        base_address = 0
        gtirb_ir = gtirb.IR.load_protobuf(target_gtirb_path)
        functions = gtirb_common.get_functions(gtirb_ir)
        parser = StackTraceParser(
            trace_output.name,
            log_file.name,
            base_address,
            gtirb_ir,
            functions,
            target_asm_path,
        )
        parser.refresh(None)

        assert len(parser.stack_record) == 1
        assert parser.stack_record[0].address == main_entry
        assert parser.stack_record[0].name == "main"

    def test_parse_immediate_return(self) -> None:
        global target_gtirb_path, target_asm_path
        trace_output = tempfile.NamedTemporaryFile(mode="w+")
        log_file = self._generate_log(
            [main_entry, layered_imm_ret_entry, imm_ret_address,]
        )
        base_address = 0
        gtirb_ir = gtirb.IR.load_protobuf(target_gtirb_path)
        functions = gtirb_common.get_functions(gtirb_ir)
        parser = StackTraceParser(
            trace_output.name,
            log_file.name,
            base_address,
            gtirb_ir,
            functions,
            target_asm_path,
        )

        parser.refresh(None)
        assert len(parser.stack_record) == 3
        assert parser.stack_record[0].address == main_entry
        assert parser.stack_record[0].name == "main"
        assert parser.stack_record[1].address == layered_imm_ret_entry
        assert parser.stack_record[1].name == "layered_return"
        assert parser.stack_record[2].address == imm_ret_address
        assert parser.stack_record[2].name == "immediate_return"

        self._extend_log([layered_imm_ret_exit], log_file.name)
        parser.refresh(None)
        assert len(parser.stack_record) == 2
        assert parser.stack_record[0].address == main_entry
        assert parser.stack_record[0].name == "main"
        assert parser.stack_record[1].address == layered_imm_ret_exit
        assert parser.stack_record[1].name == "layered_return"

        self._extend_log([main_after_imm_ret], log_file.name)
        parser.refresh(None)
        assert len(parser.stack_record) == 1
        assert parser.stack_record[0].address == main_after_imm_ret
        assert parser.stack_record[0].name == "main"

    def test_parse_missed_exit(self) -> None:
        global target_gtirb_path, target_asm_path
        trace_output = tempfile.NamedTemporaryFile(mode="w+")
        log_file = self._generate_log(
            [main_entry, layered_imm_ret_entry, main_after_imm_ret]
        )
        base_address = 0
        gtirb_ir = gtirb.IR.load_protobuf(target_gtirb_path)
        functions = gtirb_common.get_functions(gtirb_ir)
        parser = StackTraceParser(
            trace_output.name,
            log_file.name,
            base_address,
            gtirb_ir,
            functions,
            target_asm_path,
        )

        parser.refresh(None)
        assert len(parser.stack_record) == 1
        assert parser.stack_record[0].address == main_after_imm_ret
        assert parser.stack_record[0].name == "main"

    def test_parse_missed_entry(self) -> None:
        global target_gtirb_path, target_asm_path
        trace_output = tempfile.NamedTemporaryFile(mode="w+")
        log_file = self._generate_log([main_entry, layered_imm_ret_exit,])
        base_address = 0
        gtirb_ir = gtirb.IR.load_protobuf(target_gtirb_path)
        functions = gtirb_common.get_functions(gtirb_ir)
        parser = StackTraceParser(
            trace_output.name,
            log_file.name,
            base_address,
            gtirb_ir,
            functions,
            target_asm_path,
        )

        parser.refresh(None)
        assert len(parser.stack_record) == 2
        assert parser.stack_record[0].address == main_entry
        assert parser.stack_record[0].name == "main"
        assert parser.stack_record[1].address == layered_imm_ret_exit
        assert parser.stack_record[1].name == "layered_return"

        self._extend_log([main_after_imm_ret], log_file.name)
        parser.refresh(None)
        assert len(parser.stack_record) == 1
        assert parser.stack_record[0].address == main_after_imm_ret
        assert parser.stack_record[0].name == "main"

    def test_parse_entry_after_exit(self) -> None:
        global target_gtirb_path, target_asm_path
        trace_output = tempfile.NamedTemporaryFile(mode="w+")
        log_file = self._generate_log(
            [
                main_entry,
                layered_imm_ret_entry,
                layered_imm_ret_exit,
                main_after_imm_ret,
                layered_imm_ret_entry,
            ]
        )
        base_address = 0
        gtirb_ir = gtirb.IR.load_protobuf(target_gtirb_path)
        functions = gtirb_common.get_functions(gtirb_ir)
        parser = StackTraceParser(
            trace_output.name,
            log_file.name,
            base_address,
            gtirb_ir,
            functions,
            target_asm_path,
        )

        parser.refresh(None)
        assert len(parser.stack_record) == 2
        assert parser.stack_record[0].address == main_after_imm_ret
        assert parser.stack_record[0].name == "main"
        assert parser.stack_record[1].address == layered_imm_ret_entry
        assert parser.stack_record[1].name == "layered_return"

    def test_parse_pc_repeat(self) -> None:
        global target_gtirb_path, target_asm_path
        trace_output = tempfile.NamedTemporaryFile(mode="w+")
        log_file = self._generate_log([main_entry])
        base_address = 0
        gtirb_ir = gtirb.IR.load_protobuf(target_gtirb_path)
        functions = gtirb_common.get_functions(gtirb_ir)
        parser = StackTraceParser(
            trace_output.name,
            log_file.name,
            base_address,
            gtirb_ir,
            functions,
            target_asm_path,
        )

        avatar_target = mock.Mock(name="avatar_target")
        avatar_target.regs.pc = layered_imm_ret_entry
        parser.refresh(layered_imm_ret_entry)
        assert len(parser.stack_record) == 2
        assert parser.stack_record[0].address == main_entry
        assert parser.stack_record[0].name == "main"
        assert parser.stack_record[1].address == layered_imm_ret_entry
        assert parser.stack_record[1].name == "layered_return"

        self._extend_log([layered_imm_ret_entry], log_file.name)
        parser.refresh(None)
        assert len(parser.stack_record) == 2
        assert parser.stack_record[0].address == main_entry
        assert parser.stack_record[0].name == "main"
        assert parser.stack_record[1].address == layered_imm_ret_entry
        assert parser.stack_record[1].name == "layered_return"

    def test_get_next_address_blank_lines(self) -> None:
        """Test that get_next_address skips blank lines."""
        global target_gtirb_path, target_asm_path
        trace_output = tempfile.NamedTemporaryFile(mode="w+")
        log_file = self._generate_log([main_entry])
        base_address = 0
        gtirb_ir = gtirb.IR.load_protobuf(target_gtirb_path)
        functions = gtirb_common.get_functions(gtirb_ir)
        parser = StackTraceParser(
            trace_output.name,
            log_file.name,
            base_address,
            gtirb_ir,
            functions,
            target_asm_path,
        )

        log_contents = ["", "  ", "IN:", f"0x{main_entry:016x}:  nop"]
        parser.log_index = 0
        addr = parser.get_next_address(log_contents)
        assert addr == main_entry

    def test_get_next_address_no_address(self) -> None:
        """Test get_next_address returns None when no address found."""
        global target_gtirb_path, target_asm_path
        trace_output = tempfile.NamedTemporaryFile(mode="w+")
        log_file = self._generate_log([main_entry])
        base_address = 0
        gtirb_ir = gtirb.IR.load_protobuf(target_gtirb_path)
        functions = gtirb_common.get_functions(gtirb_ir)
        parser = StackTraceParser(
            trace_output.name,
            log_file.name,
            base_address,
            gtirb_ir,
            functions,
            target_asm_path,
        )

        log_contents = ["IN:", "some text"]
        parser.log_index = 0
        addr = parser.get_next_address(log_contents)
        assert addr is None

    def test_get_function_on_no_function(self) -> None:
        """Test get_function_on returns None for unknown address."""
        global target_gtirb_path, target_asm_path
        trace_output = tempfile.NamedTemporaryFile(mode="w+")
        log_file = self._generate_log([main_entry])
        base_address = 0
        gtirb_ir = gtirb.IR.load_protobuf(target_gtirb_path)
        functions = gtirb_common.get_functions(gtirb_ir)
        parser = StackTraceParser(
            trace_output.name,
            log_file.name,
            base_address,
            gtirb_ir,
            functions,
            target_asm_path,
        )

        # Use an address that no function covers
        result = parser.get_function_on(0xDEADBEEF)
        assert result is None

    def test_is_function_entry(self) -> None:
        """Test is_function_entry returns correct results."""
        global target_gtirb_path, target_asm_path
        trace_output = tempfile.NamedTemporaryFile(mode="w+")
        log_file = self._generate_log([main_entry])
        base_address = 0
        gtirb_ir = gtirb.IR.load_protobuf(target_gtirb_path)
        functions = gtirb_common.get_functions(gtirb_ir)
        parser = StackTraceParser(
            trace_output.name,
            log_file.name,
            base_address,
            gtirb_ir,
            functions,
            target_asm_path,
        )

        # main_entry should be an entry to the main function
        func = parser.function_entries.get(main_entry)
        if func is not None:
            assert parser.is_function_entry(func, main_entry) is True
            assert parser.is_function_entry(func, 0xDEAD) is False

    def test_is_function_exit(self) -> None:
        """Test is_function_exit returns correct results."""
        global target_gtirb_path, target_asm_path
        trace_output = tempfile.NamedTemporaryFile(mode="w+")
        log_file = self._generate_log([main_entry])
        base_address = 0
        gtirb_ir = gtirb.IR.load_protobuf(target_gtirb_path)
        functions = gtirb_common.get_functions(gtirb_ir)
        parser = StackTraceParser(
            trace_output.name,
            log_file.name,
            base_address,
            gtirb_ir,
            functions,
            target_asm_path,
        )

        func = parser.function_exits.get(main_exit)
        if func is not None:
            assert parser.is_function_exit(func, main_exit) is True
            assert parser.is_function_exit(func, 0xDEAD) is False
