"""Tests for halucinator.util.parse_coverage module."""

import io
from unittest import mock

import pytest

# gtirb and gtirb_functions may not be available
gtirb = pytest.importorskip("gtirb")
pytest.importorskip("gtirb_functions")

from halucinator.util.parse_coverage import (
    CodeStatus,
    CoverageParser,
    FunctionCoverageInfo,
    LineCoverageInfo,
)


# ---------------------------------------------------------------------------
# CodeStatus enum
# ---------------------------------------------------------------------------


class TestCodeStatus:
    def test_values(self):
        assert CodeStatus.NotCode is not None
        assert CodeStatus.ReachableCode is not None
        assert CodeStatus.UnreachableCode is not None


# ---------------------------------------------------------------------------
# LineCoverageInfo / FunctionCoverageInfo dataclasses
# ---------------------------------------------------------------------------


class TestDataclasses:
    def test_line_coverage_info_defaults(self):
        info = LineCoverageInfo(asm_line=10, status=CodeStatus.ReachableCode)
        assert info.asm_line == 10
        assert info.status == CodeStatus.ReachableCode
        assert info.covered is False

    def test_function_coverage_info_defaults(self):
        info = FunctionCoverageInfo(asm_line=5, name="main")
        assert info.asm_line == 5
        assert info.name == "main"
        assert info.covered is False


# ---------------------------------------------------------------------------
# CoverageParser methods (unit-tested with mocks)
# ---------------------------------------------------------------------------


class TestCoverageParserMethods:
    def _make_parser_instance(self):
        """Create a CoverageParser instance bypassing __init__."""
        obj = object.__new__(CoverageParser)
        obj.log_index = 0
        return obj

    def test_code_status_at_address_not_code(self):
        parser = self._make_parser_instance()
        module = mock.Mock()
        module.code_blocks_on.return_value = []
        result = parser.code_status_at_address(module, 0x1000)
        assert result == CodeStatus.NotCode

    def test_code_status_at_address_reachable(self):
        parser = self._make_parser_instance()
        module = mock.Mock()
        block = mock.Mock()
        module.code_blocks_on.return_value = [block]
        reachable_aux = mock.Mock()
        reachable_aux.data = {block}
        module.aux_data = {"reachableCode": reachable_aux}
        result = parser.code_status_at_address(module, 0x1000)
        assert result == CodeStatus.ReachableCode

    def test_code_status_at_address_unreachable(self):
        parser = self._make_parser_instance()
        module = mock.Mock()
        block = mock.Mock()
        module.code_blocks_on.return_value = [block]
        reachable_aux = mock.Mock()
        reachable_aux.data = set()  # block not in reachable set
        module.aux_data = {"reachableCode": reachable_aux}
        result = parser.code_status_at_address(module, 0x1000)
        assert result == CodeStatus.UnreachableCode

    def test_code_status_no_reachable_aux(self):
        parser = self._make_parser_instance()
        module = mock.Mock()
        block = mock.Mock()
        module.code_blocks_on.return_value = [block]
        module.aux_data = {}  # no reachableCode
        result = parser.code_status_at_address(module, 0x1000)
        assert result == CodeStatus.ReachableCode

    def test_parse_log_basic(self):
        parser = self._make_parser_instance()
        parser.base_address = 0x0
        parser.ln_coverage_map = {
            0x1000: LineCoverageInfo(1, CodeStatus.ReachableCode),
            0x1004: LineCoverageInfo(2, CodeStatus.ReachableCode),
        }
        parser.fn_coverage_map = {
            0x1000: FunctionCoverageInfo(1, "func_a"),
        }

        log_text = (
            "IN:\n"
            "0x00001000:  mov r0, r1\n"
            "0x00001004:  bx lr\n"
        )
        parser.parse_log(log_text)

        assert parser.ln_coverage_map[0x1000].covered is True
        assert parser.ln_coverage_map[0x1004].covered is True
        assert parser.fn_coverage_map[0x1000].covered is True

    def test_parse_log_unknown_address(self):
        parser = self._make_parser_instance()
        parser.base_address = 0x0
        parser.ln_coverage_map = {}
        parser.fn_coverage_map = {}

        log_text = "0x00009999:  unknown\n"
        # Should not raise, just log a warning
        parser.parse_log(log_text)

    def test_parse_log_skips_non_address_lines(self):
        parser = self._make_parser_instance()
        parser.base_address = 0x0
        parser.ln_coverage_map = {}
        parser.fn_coverage_map = {}

        log_text = "IN:\nsome other text\n"
        parser.parse_log(log_text)
        # No crash

    def test_parse_log_with_base_address(self):
        parser = self._make_parser_instance()
        parser.base_address = 0x4000000000
        parser.ln_coverage_map = {
            0x1000: LineCoverageInfo(1, CodeStatus.ReachableCode),
        }
        parser.fn_coverage_map = {}

        log_text = "0x4000001000:  mov r0, r1\n"
        parser.parse_log(log_text)
        assert parser.ln_coverage_map[0x1000].covered is True

    def test_get_lcov_func_str(self):
        parser = self._make_parser_instance()
        info = FunctionCoverageInfo(asm_line=10, name="main", covered=True)
        result = parser.get_lcov_func_str(info)
        assert "FN:10,main" in result
        assert "FNDA:1,main" in result

    def test_get_lcov_func_str_not_covered(self):
        parser = self._make_parser_instance()
        info = FunctionCoverageInfo(asm_line=5, name="init", covered=False)
        result = parser.get_lcov_func_str(info)
        assert "FNDA:0,init" in result

    def test_get_lcov_line_str_reachable_covered(self):
        parser = self._make_parser_instance()
        info = LineCoverageInfo(asm_line=10, status=CodeStatus.ReachableCode, covered=True)
        result = parser.get_lcov_line_str(0x1000, info)
        assert result == "DA:10,1\n"

    def test_get_lcov_line_str_reachable_not_covered(self):
        parser = self._make_parser_instance()
        info = LineCoverageInfo(asm_line=10, status=CodeStatus.ReachableCode, covered=False)
        result = parser.get_lcov_line_str(0x1000, info)
        assert result == "DA:10,0\n"

    def test_get_lcov_line_str_not_code_not_covered(self):
        parser = self._make_parser_instance()
        info = LineCoverageInfo(asm_line=10, status=CodeStatus.NotCode, covered=False)
        result = parser.get_lcov_line_str(0x1000, info)
        assert result is None

    def test_get_lcov_line_str_not_code_covered(self):
        parser = self._make_parser_instance()
        info = LineCoverageInfo(asm_line=10, status=CodeStatus.NotCode, covered=True)
        result = parser.get_lcov_line_str(0x1000, info)
        assert result == "DA:10,1\n"

    def test_get_lcov_line_str_unreachable_covered(self):
        parser = self._make_parser_instance()
        info = LineCoverageInfo(asm_line=10, status=CodeStatus.UnreachableCode, covered=True)
        result = parser.get_lcov_line_str(0x1000, info)
        assert result == "DA:10,1\n"

    def test_get_lcov_line_str_unreachable_not_covered(self):
        parser = self._make_parser_instance()
        info = LineCoverageInfo(asm_line=10, status=CodeStatus.UnreachableCode, covered=False)
        result = parser.get_lcov_line_str(0x1000, info)
        assert result == "DA:10,-1\n"

    def test_write_lcov_record(self):
        parser = self._make_parser_instance()
        f = io.StringIO()

        ln_map = {
            0x1000: LineCoverageInfo(1, CodeStatus.ReachableCode, True),
        }
        fn_map = {
            0x1000: FunctionCoverageInfo(1, "main", True),
        }

        parser.write_lcov_record(f, "test.s", ln_map, fn_map)

        output = f.getvalue()
        assert "SF:test.s" in output
        assert "FN:1,main" in output
        assert "FNDA:1,main" in output
        assert "DA:1,1" in output
        assert "end_of_record" in output

    def test_extract_function_coverage_map(self):
        parser = self._make_parser_instance()

        # Mock a function with entry blocks and symbols
        block = mock.Mock()
        block.address = 0x1000

        sym = mock.Mock()
        sym.referent = block
        sym.name = "test_func"

        func = mock.Mock(spec=["name_symbols", "get_entry_blocks"])
        func.name_symbols = [sym]
        func.get_entry_blocks.return_value = {block}

        addr_to_line = {
            0x1000: LineCoverageInfo(5, CodeStatus.ReachableCode),
        }

        result = parser.extract_function_coverage_map([func], addr_to_line)
        assert 0x1000 in result
        assert result[0x1000].name == "test_func"
        assert result[0x1000].asm_line == 5

    def test_extract_line_coverage_map(self, tmp_path):
        parser = self._make_parser_instance()
        asm_file = tmp_path / "test.s"
        asm_file.write_text(
            "nop # EA: 0x00001000\n"
            "nop # EA: 0x00001004\n"
            "some other line\n"
        )

        module = mock.Mock()
        block = mock.Mock()
        module.code_blocks_on.return_value = [block]
        reachable_aux = mock.Mock()
        reachable_aux.data = {block}
        module.aux_data = {"reachableCode": reachable_aux}

        result = parser.extract_line_coverage_map(str(asm_file), module)
        assert 0x1000 in result
        assert 0x1004 in result
        assert result[0x1000].asm_line == 1
        assert result[0x1004].asm_line == 2
        assert result[0x1000].status == CodeStatus.ReachableCode

    def test_init_full(self, tmp_path):
        """Test full __init__ of CoverageParser."""
        asm_file = tmp_path / "test.s"
        asm_file.write_text("nop # EA: 0x00001000\n")

        log_path = tmp_path / "log.txt"
        log_path.write_text("")
        bin_path = tmp_path / "test.bin"
        bin_path.write_text("")

        module = mock.Mock()
        module.code_blocks_on.return_value = []
        module.aux_data = {}

        gtirb_ir = mock.Mock()
        gtirb_ir.modules = [module]

        func = mock.Mock(spec=["name_symbols", "get_entry_blocks"])
        func.name_symbols = []
        func.get_entry_blocks.return_value = set()

        parser = CoverageParser(
            str(tmp_path / "out.lcov"),
            str(log_path),
            str(bin_path),
            0,
            gtirb_ir,
            [func],
            str(asm_file),
        )
        assert parser.log_index == 0
        assert parser.target == "test.bin"
        assert parser.base_address == 0

    def test_refresh(self, tmp_path):
        """Test refresh reads log and writes lcov."""
        parser = self._make_parser_instance()
        parser.base_address = 0
        parser.ln_coverage_map = {
            0x1000: LineCoverageInfo(1, CodeStatus.ReachableCode),
        }
        parser.fn_coverage_map = {
            0x1000: FunctionCoverageInfo(1, "main"),
        }
        parser.assembly_path = "test.s"

        log_file = tmp_path / "qemu.log"
        log_file.write_text("0x00001000:  mov r0, r1\n")
        parser.log_path = str(log_file)

        out_file = tmp_path / "out.lcov"
        parser.coverage_output = str(out_file)

        parser.refresh()

        assert parser.ln_coverage_map[0x1000].covered is True
        assert parser.fn_coverage_map[0x1000].covered is True
        content = out_file.read_text()
        assert "SF:test.s" in content
        assert "end_of_record" in content
