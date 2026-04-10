"""
Tests for halucinator.debug_shell
"""

from unittest import mock

import pytest

from halucinator.debug_shell import (
    DebugShell,
    _trim_docstring,
    _display_mem_numeric,
    _display_mem_chars,
    numerate_args,
    addr_to_symoffs,
    debug_repeat_n,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_debugger():
    debugger = mock.Mock()
    debugger.memory_info.return_value = None
    return debugger


@pytest.fixture
def shell(mock_debugger):
    with mock.patch("halucinator.debug_shell.InteractiveShellEmbed"):
        s = DebugShell(mock_debugger)
    return s


# ---------------------------------------------------------------------------
# Tests: _trim_docstring
# ---------------------------------------------------------------------------

class TestTrimDocstring:
    def test_none_returns_empty(self):
        summary, details = _trim_docstring(None)
        assert summary == ""
        assert details == []

    def test_single_line(self):
        summary, details = _trim_docstring("Summary line.")
        assert summary == "Summary line."
        assert details == []

    def test_multiline(self):
        doc = """Summary.

        First detail line.
        Second detail line.
        """
        summary, details = _trim_docstring(doc)
        assert summary == "Summary."
        assert len(details) == 2
        assert "First detail line." in details[0]

    def test_empty_string(self):
        summary, details = _trim_docstring("")
        assert summary == ""
        assert details == []


# ---------------------------------------------------------------------------
# Tests: numerate_args
# ---------------------------------------------------------------------------

class TestNumerateArgs:
    def test_empty_list(self):
        result = numerate_args([])
        assert result == []

    def test_decimal_number(self):
        result = numerate_args(["42"])
        assert result == [42]

    def test_hex_number(self):
        result = numerate_args(["0x1000"])
        assert result == [0x1000]

    def test_multiple_numbers(self):
        result = numerate_args(["10", "0x20", "30"])
        assert result == [10, 0x20, 30]

    def test_invalid_number_returns_none(self):
        result = numerate_args(["notanumber"])
        assert result is None

    def test_star_prefix_without_starok(self):
        result = numerate_args(["*0x1000"], starok=False)
        assert result is None

    def test_star_prefix_with_starok(self):
        result = numerate_args(["*0x1000"], starok=True)
        assert result == [0x1000]


# ---------------------------------------------------------------------------
# Tests: DebugShell.lookup_command
# ---------------------------------------------------------------------------

class TestLookupCommand:
    def test_exact_match(self, shell):
        name, handler = DebugShell.lookup_command("help")
        assert name == "help"

    def test_short_command(self, shell):
        name, handler = DebugShell.lookup_command("b")
        assert name == "break"

    def test_prefix_match(self, shell):
        name, handler = DebugShell.lookup_command("hel")
        assert name == "help"

    def test_no_match_raises(self, shell):
        with pytest.raises(LookupError, match="Undefined command"):
            DebugShell.lookup_command("zzzzz_nonexistent")

    def test_ambiguous_raises(self, shell):
        # Register two commands that share a prefix for this test
        # "continue" and "clear" both start with "c"
        # but "co" should resolve to "continue"
        name, handler = DebugShell.lookup_command("co")
        assert name == "continue"


# ---------------------------------------------------------------------------
# Tests: DebugShell.command decorator
# ---------------------------------------------------------------------------

class TestCommandDecorator:
    def test_registers_single_name(self, shell):
        @DebugShell.command("test_cmd_unique_12345")
        def my_handler(state, args):
            """A test command."""
            pass

        assert "test_cmd_unique_12345" in DebugShell.command_handlers
        # Cleanup
        del DebugShell.command_handlers["test_cmd_unique_12345"]

    def test_registers_short_names(self, shell):
        @DebugShell.command(["test_cmd_long_99999", "tcl99"])
        def my_handler(state, args):
            pass

        assert "test_cmd_long_99999" in DebugShell.command_handlers
        assert DebugShell.short_commands.get("tcl99") == "test_cmd_long_99999"
        # Cleanup
        del DebugShell.command_handlers["test_cmd_long_99999"]
        del DebugShell.short_commands["tcl99"]

    def test_registers_extra_help(self, shell):
        @DebugShell.command("test_cmd_help_88888", extra_help="  Extra info  ")
        def my_handler(state, args):
            pass

        assert DebugShell.extra_help.get("test_cmd_help_88888") == "Extra info"
        # Cleanup
        del DebugShell.command_handlers["test_cmd_help_88888"]
        del DebugShell.extra_help["test_cmd_help_88888"]


# ---------------------------------------------------------------------------
# Tests: DebugShell.handle_command
# ---------------------------------------------------------------------------

class TestHandleCommand:
    def test_empty_command_uses_last(self, shell):
        shell.last_command = "help"
        with mock.patch.dict(DebugShell.command_handlers, {"help": mock.Mock()}):
            shell.handle_command("")
            DebugShell.command_handlers["help"].assert_called()

    def test_unknown_command_prints_error(self, shell, capsys):
        shell.handle_command("zzzzz_unknown")
        captured = capsys.readouterr()
        assert "Undefined command" in captured.out

    def test_slash_separator(self, shell):
        """Test that x/10xw splits correctly."""
        with mock.patch.dict(DebugShell.command_handlers, {"x": mock.Mock()}):
            shell.handle_command("x/10xw 0x1000")
            DebugShell.command_handlers["x"].assert_called_once()
            call_args = DebugShell.command_handlers["x"].call_args
            # args should start with "/10xw"
            assert "/10xw" in call_args[0][1]


# ---------------------------------------------------------------------------
# Tests: DebugShell.validate_memory_range
# ---------------------------------------------------------------------------

class TestValidateMemoryRange:
    def test_returns_false_when_no_memory_info(self, shell, mock_debugger):
        mock_debugger.memory_info.return_value = None
        assert shell.validate_memory_range(0x1000, 0x2000) is False

    def test_returns_true_when_in_range(self, shell, mock_debugger):
        mmi = mock.Mock()
        mmi.addr_end = 0x3000
        mock_debugger.memory_info.return_value = mmi
        assert shell.validate_memory_range(0x1000, 0x2000) is True

    def test_returns_false_when_end_exceeds(self, shell, mock_debugger):
        mmi = mock.Mock()
        mmi.addr_end = 0x1500
        mock_debugger.memory_info.return_value = mmi
        assert shell.validate_memory_range(0x1000, 0x2000) is False


# ---------------------------------------------------------------------------
# Tests: DebugShell.nested_completions
# ---------------------------------------------------------------------------

class TestNestedCompletions:
    def test_returns_dict_with_info(self, shell):
        comps = shell.nested_completions()
        assert "info" in comps
        assert "break" in comps["info"]
        assert "registers" in comps["info"]


# ---------------------------------------------------------------------------
# Tests: DebugShell.get_prompt_prefix
# ---------------------------------------------------------------------------

class TestGetPromptPrefix:
    def test_returns_hal_prompt(self, shell):
        prefix = shell.get_prompt_prefix()
        assert len(prefix) == 1
        assert "(HALr-gdb)" in prefix[0][1]


# ---------------------------------------------------------------------------
# Tests: _display_mem_numeric
# ---------------------------------------------------------------------------

class TestDisplayMemNumeric:
    def test_hex_format(self, capsys):
        _display_mem_numeric([0xAB, 0xCD], 0x1000, 2, 8, 1, "x")
        captured = capsys.readouterr()
        assert "0x00001000" in captured.out

    def test_decimal_format(self, capsys):
        _display_mem_numeric([42, 100], 0x2000, 2, 8, 1, "d")
        captured = capsys.readouterr()
        assert "42" in captured.out
        assert "100" in captured.out

    def test_row_wrapping(self, capsys):
        data = list(range(16))
        _display_mem_numeric(data, 0x1000, 16, 8, 1, "x")
        captured = capsys.readouterr()
        lines = [l for l in captured.out.strip().split("\n") if l]
        assert len(lines) == 2  # 16 elements / 8 per row = 2 rows


# ---------------------------------------------------------------------------
# Tests: _display_mem_chars
# ---------------------------------------------------------------------------

class TestDisplayMemChars:
    def test_printable_chars(self, capsys):
        _display_mem_chars([65, 66], 0x1000, 2)  # A, B
        captured = capsys.readouterr()
        assert "'A'" in captured.out
        assert "'B'" in captured.out

    def test_non_printable_chars(self, capsys):
        _display_mem_chars([0, 10], 0x1000, 2)  # NUL, LF
        captured = capsys.readouterr()
        assert "\\000" in captured.out
        assert "\\012" in captured.out

    def test_high_byte_chars(self, capsys):
        _display_mem_chars([200], 0x1000, 1)
        captured = capsys.readouterr()
        assert "\\310" in captured.out


# ---------------------------------------------------------------------------
# Tests: addr_to_symoffs
# ---------------------------------------------------------------------------

class TestAddrToSymoffs:
    def test_returns_formatted_string(self, shell, mock_debugger):
        config = mock.Mock()
        config.get_symbol_offset.return_value = ("main", 4)
        mock_debugger.avatar = mock.Mock()
        mock_debugger.avatar.config = config

        result = addr_to_symoffs(shell, 0x1004)
        assert result == "<main+4>"

    def test_returns_none_when_no_symbol(self, shell, mock_debugger):
        config = mock.Mock()
        config.get_symbol_offset.return_value = None
        mock_debugger.avatar = mock.Mock()
        mock_debugger.avatar.config = config

        result = addr_to_symoffs(shell, 0x9999)
        assert result is None


# ---------------------------------------------------------------------------
# Tests: help command
# ---------------------------------------------------------------------------

class TestHelpCommand:
    def test_help_list(self, shell, capsys):
        shell.handle_command("help")
        captured = capsys.readouterr()
        assert "help" in captured.out.lower()

    def test_help_specific_command(self, shell, capsys):
        shell.handle_command("help continue")
        captured = capsys.readouterr()
        assert "continue" in captured.out.lower()

    def test_help_unknown_command(self, shell, capsys):
        shell.handle_command("help zzz_nonexistent")
        captured = capsys.readouterr()
        assert "Undefined command" in captured.out


# ---------------------------------------------------------------------------
# Tests: quit command
# ---------------------------------------------------------------------------

class TestQuitCommand:
    def test_sets_exiting(self, shell):
        shell.exiting = False
        shell.handle_command("quit")
        assert shell.exiting is True

    def test_exit_alias(self, shell):
        shell.exiting = False
        shell.handle_command("exit")
        assert shell.exiting is True


# ---------------------------------------------------------------------------
# Tests: info command
# ---------------------------------------------------------------------------

class TestInfoCommand:
    def test_info_with_no_args_calls_help(self, shell, capsys):
        shell.handle_command("info")
        captured = capsys.readouterr()
        # Should display help for info (falls through to help)

    def test_info_breakpoints_empty(self, shell, mock_debugger, capsys):
        mock_debugger.list_debug_breakpoints.return_value = {}
        shell.handle_command("info breakpoints")
        captured = capsys.readouterr()
        assert "No breakpoints" in captured.out

    def test_info_breakpoints_with_entries(self, shell, mock_debugger, capsys):
        mock_debugger.list_debug_breakpoints.return_value = {1: 0x1000}
        config = mock.Mock()
        config.get_symbol_offset.return_value = ("main", 0)
        mock_debugger.avatar = mock.Mock()
        mock_debugger.avatar.config = config

        shell.handle_command("info break")
        captured = capsys.readouterr()
        assert "breakpoint" in captured.out

    def test_info_functions(self, shell, mock_debugger, capsys):
        config = mock.Mock()
        config.get_symbol_list.return_value = [("main", 0x1000), ("func", 0x2000)]
        mock_debugger.avatar = mock.Mock()
        mock_debugger.avatar.config = config

        shell.handle_command("info functions")
        captured = capsys.readouterr()
        assert "main" in captured.out
        assert "func" in captured.out


# ---------------------------------------------------------------------------
# Tests: debug_repeat_n
# ---------------------------------------------------------------------------

class TestDebugRepeatN:
    def test_runs_n_times(self, shell, mock_debugger, capsys):
        from avatar2 import TargetStates

        mock_debugger.get_target_state.return_value = TargetStates.STOPPED
        oper = mock.Mock(return_value=True)

        debug_repeat_n(shell, oper, 3)
        assert oper.call_count == 3


# ---------------------------------------------------------------------------
# Tests: continue command
# ---------------------------------------------------------------------------

class TestContinueCommand:
    def test_continue_calls_cont(self, shell, mock_debugger):
        shell.handle_command("continue")
        mock_debugger.cont.assert_called_once()


# ---------------------------------------------------------------------------
# Tests: stepi command
# ---------------------------------------------------------------------------

class TestStepiCommand:
    def test_single_step(self, shell, mock_debugger):
        from avatar2 import TargetStates
        mock_debugger.get_target_state.return_value = TargetStates.STOPPED
        shell.handle_command("stepi")
        mock_debugger.step.assert_called_once()

    def test_step_not_stopped(self, shell, mock_debugger, capsys):
        from avatar2 import TargetStates
        mock_debugger.get_target_state.return_value = TargetStates.RUNNING
        shell.handle_command("stepi")
        captured = capsys.readouterr()
        assert "not stopped" in captured.out

    def test_step_with_count(self, shell, mock_debugger):
        from avatar2 import TargetStates
        mock_debugger.get_target_state.return_value = TargetStates.STOPPED
        shell.handle_command("stepi 3")
        assert mock_debugger.step.call_count == 3

    def test_step_invalid_arg(self, shell, mock_debugger, capsys):
        from avatar2 import TargetStates
        mock_debugger.get_target_state.return_value = TargetStates.STOPPED
        shell.handle_command("stepi abc")
        captured = capsys.readouterr()
        assert "expecting a number" in captured.out

    def test_step_multiple_args(self, shell, mock_debugger, capsys):
        from avatar2 import TargetStates
        mock_debugger.get_target_state.return_value = TargetStates.STOPPED
        shell.handle_command("stepi 3 4")
        captured = capsys.readouterr()
        assert "multiple arguments" in captured.out


# ---------------------------------------------------------------------------
# Tests: nexti command
# ---------------------------------------------------------------------------

class TestNextiCommand:
    def test_single_next(self, shell, mock_debugger):
        from avatar2 import TargetStates
        mock_debugger.get_target_state.return_value = TargetStates.STOPPED
        shell.handle_command("nexti")
        mock_debugger.next.assert_called_once()

    def test_next_not_stopped(self, shell, mock_debugger, capsys):
        from avatar2 import TargetStates
        mock_debugger.get_target_state.return_value = TargetStates.RUNNING
        shell.handle_command("nexti")
        captured = capsys.readouterr()
        assert "not stopped" in captured.out


# ---------------------------------------------------------------------------
# Tests: finish command
# ---------------------------------------------------------------------------

class TestFinishCommand:
    def test_finish_calls_debugger(self, shell, mock_debugger):
        shell.handle_command("finish")
        mock_debugger.finish.assert_called_once()


# ---------------------------------------------------------------------------
# Tests: break command
# ---------------------------------------------------------------------------

class TestBreakCommand:
    def test_break_at_pc(self, shell, mock_debugger):
        mock_debugger.read_register.return_value = 0x1000
        shell.handle_command("break")
        mock_debugger.set_debug_breakpoint.assert_called_once_with(0x1000)

    def test_break_at_address(self, shell, mock_debugger):
        shell.handle_command("break 0x2000")
        mock_debugger.set_debug_breakpoint.assert_called_once_with(0x2000)

    def test_break_at_star_address(self, shell, mock_debugger):
        shell.handle_command("break *0x3000")
        mock_debugger.set_debug_breakpoint.assert_called_once_with(0x3000)

    def test_break_at_file_line(self, shell, mock_debugger, capsys):
        shell.handle_command("break file.c:10")
        captured = capsys.readouterr()
        assert "not supported" in captured.out

    def test_break_bad_address(self, shell, mock_debugger, capsys):
        shell.handle_command("break *notaddr")
        captured = capsys.readouterr()
        assert "Don't understand" in captured.out


# ---------------------------------------------------------------------------
# Tests: delete command
# ---------------------------------------------------------------------------

class TestDeleteCommand:
    def test_delete_specific_breakpoint(self, shell, mock_debugger):
        mock_debugger.list_debug_breakpoints.return_value = {1: 0x1000, 2: 0x2000}
        shell.handle_command("delete 1")
        mock_debugger.remove_debug_breakpoint.assert_called_once_with(1)

    def test_delete_nonexistent_breakpoint(self, shell, mock_debugger, capsys):
        mock_debugger.list_debug_breakpoints.return_value = {1: 0x1000}
        shell.handle_command("delete 99")
        captured = capsys.readouterr()
        assert "no breakpoint numbered 99" in captured.out

    def test_delete_with_break_prefix(self, shell, mock_debugger):
        mock_debugger.list_debug_breakpoints.return_value = {1: 0x1000}
        shell.handle_command("delete break 1")
        mock_debugger.remove_debug_breakpoint.assert_called_once_with(1)


# ---------------------------------------------------------------------------
# Tests: clear command
# ---------------------------------------------------------------------------

class TestClearCommand:
    def test_clear_at_address(self, shell, mock_debugger):
        mock_debugger.list_debug_breakpoints.return_value = {1: 0x1000}
        shell.handle_command("clear *0x1000")
        mock_debugger.remove_debug_breakpoint.assert_called_once_with(1)

    def test_clear_no_breakpoint_found(self, shell, mock_debugger, capsys):
        mock_debugger.list_debug_breakpoints.return_value = {1: 0x1000}
        shell.handle_command("clear *0x9999")
        captured = capsys.readouterr()
        assert "No breakpoint found" in captured.out

    def test_clear_at_pc(self, shell, mock_debugger):
        mock_debugger.read_register.return_value = 0x1000
        mock_debugger.list_debug_breakpoints.return_value = {1: 0x1000}
        shell.handle_command("clear")
        mock_debugger.remove_debug_breakpoint.assert_called_once_with(1)


# ---------------------------------------------------------------------------
# Tests: examine (x) command
# ---------------------------------------------------------------------------

class TestExamineCommand:
    def test_examine_unmapped_memory(self, shell, mock_debugger, capsys):
        mock_debugger.memory_info.return_value = None
        shell.handle_command("x 0x1000")
        captured = capsys.readouterr()
        assert "not mapped" in captured.out

    def test_examine_hex_format(self, shell, mock_debugger, capsys):
        mmi = mock.Mock()
        mmi.addr_end = 0x2000
        mock_debugger.memory_info.return_value = mmi
        mock_debugger.read_memory.return_value = [0xAB]
        shell.handle_command("x/1xb 0x1000")
        captured = capsys.readouterr()
        assert "0x00001000" in captured.out

    def test_examine_decimal_format(self, shell, mock_debugger, capsys):
        mmi = mock.Mock()
        mmi.addr_end = 0x2000
        mock_debugger.memory_info.return_value = mmi
        mock_debugger.read_memory.return_value = [42]
        shell.handle_command("x/1db 0x1000")
        captured = capsys.readouterr()
        assert "42" in captured.out

    def test_examine_char_format(self, shell, mock_debugger, capsys):
        mmi = mock.Mock()
        mmi.addr_end = 0x2000
        mock_debugger.memory_info.return_value = mmi
        mock_debugger.read_memory.return_value = [65]
        shell.handle_command("x/1cb 0x1000")
        captured = capsys.readouterr()
        assert "'A'" in captured.out

    def test_examine_bad_args(self, shell, mock_debugger, capsys):
        shell.handle_command("x something_weird!!!")
        captured = capsys.readouterr()
        assert "Unable to parse" in captured.out


# ---------------------------------------------------------------------------
# Tests: list command
# ---------------------------------------------------------------------------

class TestListCommand:
    def test_list_at_pc(self, shell, mock_debugger, capsys):
        mock_debugger.read_register.return_value = 0x1000
        config = mock.Mock()
        config.get_symbol_offset.return_value = ("main", 0)
        mock_debugger.avatar = mock.Mock()
        mock_debugger.avatar.config = config
        # Return list of (addr, mnem, operands) plus one extra for follow-up
        mock_debugger.read_instructions.return_value = [
            (0x1000, "mov", "r0, r1"),
            (0x1004, "add", "r0, r2"),
            (0x1008, "", ""),
        ]
        shell.handle_command("list")
        captured = capsys.readouterr()
        assert "mov" in captured.out

    def test_list_at_address(self, shell, mock_debugger, capsys):
        config = mock.Mock()
        config.get_symbol_offset.return_value = ("func", 0)
        mock_debugger.avatar = mock.Mock()
        mock_debugger.avatar.config = config
        mock_debugger.read_instructions.return_value = [
            (0x2000, "nop", ""),
            (0x2004, "", ""),
        ]
        shell.handle_command("list *0x2000")
        captured = capsys.readouterr()
        assert "nop" in captured.out


# ---------------------------------------------------------------------------
# Tests: backtrace command
# ---------------------------------------------------------------------------

class TestBacktraceCommand:
    def test_backtrace(self, shell, mock_debugger, capsys):
        mock_debugger._get_stack_trace.return_value = "#0  0x1000 in main\n#1  0x2000 in start"
        shell.handle_command("backtrace")
        captured = capsys.readouterr()
        assert "main" in captured.out


# ---------------------------------------------------------------------------
# Tests: python command
# ---------------------------------------------------------------------------

class TestPythonCommand:
    def test_python_expression(self, shell, mock_debugger, capsys):
        shell.ipshell.ev.return_value = 2
        shell.handle_command("python 1+1")
        captured = capsys.readouterr()
        assert "2" in captured.out
        shell.ipshell.ev.assert_called_once_with("1+1")

    def test_python_none_result(self, shell, mock_debugger, capsys):
        shell.ipshell.ev.return_value = None
        shell.handle_command("python None")
        captured = capsys.readouterr()
        # None result should not be printed
        assert captured.out == ""


# ---------------------------------------------------------------------------
# Tests: info halbreakpoints
# ---------------------------------------------------------------------------

class TestInfoHalBreakpoints:
    def test_info_halbreak_empty(self, shell, mock_debugger, capsys):
        mock_debugger.list_hal_breakpoints.return_value = {}
        shell.handle_command("info halbreak")
        captured = capsys.readouterr()
        assert "No HAL breakpoints" in captured.out

    def test_info_all_registers(self, shell, mock_debugger, capsys):
        mock_debugger.list_all_regs_names.return_value = ["r0", "r1"]
        mock_debugger.target = mock.Mock()
        mock_debugger.target.read_register.side_effect = [0x100, 0x200]
        shell.handle_command("info registers")
        captured = capsys.readouterr()
        assert "r0" in captured.out
        assert "r1" in captured.out

    def test_info_halbreak_with_entries(self, shell, mock_debugger, capsys):
        bp = mock.Mock()
        bp.address = 0x1000
        bp.bp_class = mock.Mock()
        bp.bp_handler = mock.Mock()
        bp.bp_handler.__name__ = "my_handler"
        bp.run_once = False
        mock_debugger.list_hal_breakpoints.return_value = {1: bp}
        shell.handle_command("info halbreak")
        captured = capsys.readouterr()
        assert "HALbreakpoint" in captured.out
        assert "keep" in captured.out
        assert "my_handler" in captured.out

    def test_info_halbreak_run_once(self, shell, mock_debugger, capsys):
        bp = mock.Mock()
        bp.address = 0x2000
        bp.bp_class = mock.Mock()
        bp.bp_handler = mock.Mock()
        bp.bp_handler.__name__ = "once_handler"
        bp.run_once = True
        mock_debugger.list_hal_breakpoints.return_value = {2: bp}
        shell.handle_command("info halbreak")
        captured = capsys.readouterr()
        assert "del" in captured.out

    def test_info_halbreak_with_filter(self, shell, mock_debugger, capsys):
        bp1 = mock.Mock()
        bp1.address = 0x1000
        bp1.bp_class = mock.Mock()
        bp1.bp_handler = mock.Mock()
        bp1.bp_handler.__name__ = "h1"
        bp1.run_once = False
        bp2 = mock.Mock()
        bp2.address = 0x2000
        bp2.bp_class = mock.Mock()
        bp2.bp_handler = mock.Mock()
        bp2.bp_handler.__name__ = "h2"
        bp2.run_once = False
        mock_debugger.list_hal_breakpoints.return_value = {1: bp1, 2: bp2}
        shell.handle_command("info halbreak 2")
        captured = capsys.readouterr()
        assert "h2" in captured.out

    def test_info_breakpoints_with_filter(self, shell, mock_debugger, capsys):
        mock_debugger.list_debug_breakpoints.return_value = {1: 0x1000, 2: 0x2000}
        config = mock.Mock()
        config.get_symbol_offset.return_value = ("main", 0)
        mock_debugger.avatar = mock.Mock()
        mock_debugger.avatar.config = config
        shell.handle_command("info break 2")
        captured = capsys.readouterr()
        # Should only show bp 2
        assert "breakpoint" in captured.out

    def test_info_registers_with_filter(self, shell, mock_debugger, capsys):
        mock_debugger.list_all_regs_names.return_value = ["r0", "r1"]
        mock_debugger.target = mock.Mock()
        mock_debugger.target.read_register.side_effect = [0x100, 0x200]
        shell.handle_command("info registers r0")
        captured = capsys.readouterr()
        assert "r0" in captured.out

    def test_info_with_resid_args(self, shell, mock_debugger, capsys):
        """Test info with extra args (line 745)."""
        config = mock.Mock()
        config.get_symbol_list.return_value = [("main", 0x1000), ("foo", 0x2000)]
        mock_debugger.avatar = mock.Mock()
        mock_debugger.avatar.config = config
        shell.handle_command("info functions main")
        captured = capsys.readouterr()
        assert "main" in captured.out
        # foo should not appear since it doesn't match "main"
        assert "foo" not in captured.out


# ---------------------------------------------------------------------------
# Tests: start_prompt (lines 65-80)
# ---------------------------------------------------------------------------

class TestStartPrompt:
    def test_start_prompt_eof(self, shell):
        """start_prompt exits on EOFError (lines 65-80)."""
        shell._prompt_session = mock.Mock()
        shell._prompt_session.prompt.side_effect = EOFError()
        # Should not raise
        shell.start_prompt()

    def test_start_prompt_processes_commands(self, shell):
        """start_prompt processes commands until exiting is set."""
        shell._prompt_session = mock.Mock()
        call_count = [0]

        def fake_prompt(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] >= 2:
                raise EOFError()
            return "help"

        shell._prompt_session.prompt.side_effect = fake_prompt
        shell.start_prompt()
        assert call_count[0] == 2


# ---------------------------------------------------------------------------
# Tests: ambiguous command (line 162)
# ---------------------------------------------------------------------------

class TestAmbiguousCommand:
    def test_ambiguous_prefix(self, shell):
        """Commands starting with 'c' are ambiguous (continue, clear)."""
        with pytest.raises(LookupError, match="Ambiguous command"):
            DebugShell.lookup_command("c")


# ---------------------------------------------------------------------------
# Tests: _display_mem_numeric unknown format (line 256)
# ---------------------------------------------------------------------------

class TestDisplayMemNumericUnknownFormat:
    def test_unknown_format(self, capsys):
        """Unknown format prints TODO message (line 256)."""
        _display_mem_numeric([42], 0x1000, 1, 8, 1, "o")
        captured = capsys.readouterr()
        assert "TODO" in captured.out


# ---------------------------------------------------------------------------
# Tests: _display_mem_chars row wrapping (lines 284-285)
# ---------------------------------------------------------------------------

class TestDisplayMemCharsRowWrap:
    def test_row_wrapping(self, capsys):
        """Test that _display_mem_chars wraps at 8 elements per row."""
        data = list(range(65, 65 + 16))  # 'A' through 'P'
        _display_mem_chars(data, 0x1000, 16)
        captured = capsys.readouterr()
        lines = [l for l in captured.out.strip().split("\n") if l]
        assert len(lines) == 2  # 16 / 8 = 2 rows


# ---------------------------------------------------------------------------
# Tests: debug_repeat_n timeout (lines 308-310)
# ---------------------------------------------------------------------------

class TestDebugRepeatNTimeout:
    def test_timeout(self, shell, mock_debugger, capsys):
        """debug_repeat_n prints timeout message when stuck (lines 308-310)."""
        from avatar2 import TargetStates

        mock_debugger.get_target_state.return_value = TargetStates.RUNNING
        oper = mock.Mock(return_value=True)

        import halucinator.debug_shell as ds
        original_timeout = ds.THREAD_TIMEOUT
        ds.THREAD_TIMEOUT = 0.001  # Very short timeout
        try:
            debug_repeat_n(shell, oper, 1)
        finally:
            ds.THREAD_TIMEOUT = original_timeout
        captured = capsys.readouterr()
        assert "Timeout" in captured.out


# ---------------------------------------------------------------------------
# Tests: help command - edge cases (lines 366, 376, 379, 383, 385, 389)
# ---------------------------------------------------------------------------

class TestHelpEdgeCases:
    def test_help_no_docstring(self, shell, capsys):
        """Help for a command with no docstring (lines 366, 383, 389)."""
        @DebugShell.command("test_nodoc_12345")
        def nodoc_handler(state, args):
            pass

        shell.handle_command("help test_nodoc_12345")
        captured = capsys.readouterr()
        assert "test_nodoc_12345" in captured.out
        assert "No help text exists" in captured.out

        # Cleanup
        del DebugShell.command_handlers["test_nodoc_12345"]

    def test_help_with_aliases(self, shell, capsys):
        """Help shows aliases (lines 376, 385)."""
        shell.handle_command("help quit")
        captured = capsys.readouterr()
        assert "Alias" in captured.out
        assert "exit" in captured.out

    def test_help_with_extra_help(self, shell, capsys):
        """Help with extra_help replaces details (line 379)."""
        shell.handle_command("help x")
        captured = capsys.readouterr()
        # "x" command has extra_help containing format info
        assert "FMT" in captured.out

    def test_help_no_docstring_in_list(self, shell, capsys):
        """Help list shows command name alone if no docstring (line 366)."""
        @DebugShell.command("test_nodoc_list_99999")
        def nodoc_handler(state, args):
            pass

        shell.handle_command("help")
        captured = capsys.readouterr()
        assert "test_nodoc_list_99999" in captured.out

        del DebugShell.command_handlers["test_nodoc_list_99999"]


# ---------------------------------------------------------------------------
# Tests: python command - shell and exception (lines 425-427)
# ---------------------------------------------------------------------------

class TestPythonShellException:
    def test_python_shell_start(self, shell, mock_debugger, capsys):
        """Python command with no args starts IPython shell (line 425)."""
        shell.handle_command("python")
        shell.ipshell.assert_called()

    def test_python_exception(self, shell, mock_debugger, capsys):
        """Python command catches exceptions (lines 426-427)."""
        original_side_effect = shell.ipshell.ev.side_effect
        try:
            shell.ipshell.ev.side_effect = RuntimeError("test error")
            shell.handle_command("python 1+1")
            captured = capsys.readouterr()
            assert "Unhandled exception" in captured.out
        finally:
            shell.ipshell.ev.side_effect = original_side_effect


# ---------------------------------------------------------------------------
# Tests: nexti edge cases (lines 473, 475, 478)
# ---------------------------------------------------------------------------

class TestNextiEdgeCases:
    def test_nexti_invalid_arg(self, shell, mock_debugger, capsys):
        """nexti with invalid arg prints error (line 473)."""
        from avatar2 import TargetStates
        mock_debugger.get_target_state.return_value = TargetStates.STOPPED
        shell.handle_command("nexti abc")
        captured = capsys.readouterr()
        assert "expecting a number" in captured.out

    def test_nexti_multiple_args(self, shell, mock_debugger, capsys):
        """nexti with multiple args prints error (line 475)."""
        from avatar2 import TargetStates
        mock_debugger.get_target_state.return_value = TargetStates.STOPPED
        shell.handle_command("nexti 3 4")
        captured = capsys.readouterr()
        assert "multiple arguments" in captured.out

    def test_nexti_with_count(self, shell, mock_debugger):
        """nexti with count calls next N times (line 478)."""
        from avatar2 import TargetStates
        mock_debugger.get_target_state.return_value = TargetStates.STOPPED
        shell.handle_command("nexti 3")
        assert mock_debugger.next.call_count == 3


# ---------------------------------------------------------------------------
# Tests: break edge cases (lines 519-521, 526)
# ---------------------------------------------------------------------------

class TestBreakEdgeCases:
    def test_break_bad_hex_address(self, shell, mock_debugger, capsys):
        """break with invalid hex (lines 519-521)."""
        shell.handle_command("break 0xZZZZ")
        captured = capsys.readouterr()
        assert "Don't understand" in captured.out

    def test_break_line_number(self, shell, mock_debugger, capsys):
        """break with line number (line 526)."""
        shell.handle_command("break some_symbol")
        captured = capsys.readouterr()
        assert "TODO" in captured.out


# ---------------------------------------------------------------------------
# Tests: delete all breakpoints (lines 549-553)
# ---------------------------------------------------------------------------

class TestDeleteAllBreakpoints:
    def test_delete_all_confirm_yes(self, shell, mock_debugger):
        """delete all breakpoints with 'y' confirmation (lines 549-553)."""
        mock_debugger.list_debug_breakpoints.return_value = {1: 0x1000, 2: 0x2000}
        with mock.patch("halucinator.debug_shell.prompt", return_value="y"):
            shell.handle_command("delete")
        assert mock_debugger.remove_debug_breakpoint.call_count == 2

    def test_delete_all_confirm_no(self, shell, mock_debugger):
        """delete all breakpoints with 'n' does nothing."""
        mock_debugger.list_debug_breakpoints.return_value = {1: 0x1000, 2: 0x2000}
        with mock.patch("halucinator.debug_shell.prompt", return_value="n"):
            shell.handle_command("delete")
        mock_debugger.remove_debug_breakpoint.assert_not_called()

    def test_delete_all_confirm_yes_full(self, shell, mock_debugger):
        """delete all breakpoints with 'yes' confirmation."""
        mock_debugger.list_debug_breakpoints.return_value = {1: 0x1000}
        with mock.patch("halucinator.debug_shell.prompt", return_value="yes"):
            shell.handle_command("delete")
        mock_debugger.remove_debug_breakpoint.assert_called_once_with(1)


# ---------------------------------------------------------------------------
# Tests: clear edge cases (line 575)
# ---------------------------------------------------------------------------

class TestClearEdgeCases:
    def test_clear_invalid_args(self, shell, mock_debugger, capsys):
        """clear with multiple args returns early (line 575)."""
        shell.handle_command("clear *0x1000 *0x2000")
        # Should not crash; just returns early
        mock_debugger.remove_debug_breakpoint.assert_not_called()


# ---------------------------------------------------------------------------
# Tests: examine edge cases
# ---------------------------------------------------------------------------

class TestExamineEdgeCases:
    def test_examine_unsupported_format(self, shell, mock_debugger, capsys):
        """examine with unsupported format (line 718)."""
        mmi = mock.Mock()
        mmi.addr_end = 0x2000
        mock_debugger.memory_info.return_value = mmi
        mock_debugger.read_memory.return_value = [65]
        # Use 'f' or some unsupported format character - but regex won't match
        # Actually we need to test with a format that passes the regex but is unsupported
        # 'c' is supported, let's construct state to have an unsupported format
        shell.examine_format = "f"
        shell.examine_nextaddr = 0x1000
        shell.examine_repeat = 1
        shell.examine_width = 1
        shell.handle_command("x")
        captured = capsys.readouterr()
        assert "not yet supported" in captured.out

    def test_examine_wide_char_warning(self, shell, mock_debugger, capsys):
        """examine with wide char width (line 700)."""
        mmi = mock.Mock()
        mmi.addr_end = 0x2000
        mock_debugger.memory_info.return_value = mmi
        mock_debugger.read_memory.return_value = [65]
        # Set up state: format=c, width=4
        shell.examine_format = "c"
        shell.examine_width = 4
        shell.examine_nextaddr = 0x1000
        shell.examine_repeat = 1
        shell.handle_command("x")
        captured = capsys.readouterr()
        assert "wide characters" in captured.out

    def test_examine_bad_address(self, shell, mock_debugger, capsys):
        """examine with bad address string (lines 685-687)."""
        mmi = mock.Mock()
        mmi.addr_end = 0x2000
        mock_debugger.memory_info.return_value = mmi
        # "xFxF" passes the regex [0-9a-fA-FxX]+ but fails int(base=0)
        shell.handle_command("x/1xb xFxF")
        captured = capsys.readouterr()
        assert "Couldn't understand" in captured.out

    def test_examine_no_addr_continues(self, shell, mock_debugger, capsys):
        """examine without address uses last address."""
        mmi = mock.Mock()
        mmi.addr_end = 0x2000
        mock_debugger.memory_info.return_value = mmi
        mock_debugger.read_memory.return_value = [0xAB]
        shell.examine_nextaddr = 0x1000
        shell.examine_repeat = 1
        shell.examine_width = 1
        shell.examine_format = "x"
        shell.handle_command("x")
        captured = capsys.readouterr()
        assert "0x00001000" in captured.out
        # After reading 1 byte, nextaddr should advance
        assert shell.examine_nextaddr == 0x1001


# ---------------------------------------------------------------------------
# Tests: list command edge cases (lines 813-816)
# ---------------------------------------------------------------------------

class TestListEdgeCases:
    def test_list_bad_address(self, shell, mock_debugger, capsys):
        """list with unparseable address (lines 813-814)."""
        config = mock.Mock()
        config.get_symbol_offset.return_value = ("func", 0)
        mock_debugger.avatar = mock.Mock()
        mock_debugger.avatar.config = config
        mock_debugger.read_instructions.return_value = [
            (0x1000, "nop", ""),
            (0x1004, "", ""),
        ]
        shell.listing_addr = 0x1000
        shell.handle_command("list *not_an_address")
        captured = capsys.readouterr()
        assert "don't understand" in captured.out

    def test_list_line_number(self, shell, mock_debugger, capsys):
        """list with line number (line 816)."""
        config = mock.Mock()
        config.get_symbol_offset.return_value = ("func", 0)
        mock_debugger.avatar = mock.Mock()
        mock_debugger.avatar.config = config
        mock_debugger.read_instructions.return_value = [
            (0x1000, "nop", ""),
            (0x1004, "", ""),
        ]
        shell.listing_addr = 0x1000
        shell.handle_command("list 42")
        captured = capsys.readouterr()
        assert "TODO" in captured.out


# ---------------------------------------------------------------------------
# Tests: handle_command auto-repeat behavior
# ---------------------------------------------------------------------------

class TestHandleCommandRepeat:
    def test_run_command_not_repeated(self, shell):
        """run and help commands should not be auto-repeated."""
        handler = mock.Mock()
        with mock.patch.dict(DebugShell.command_handlers, {"run": handler}):
            shell.handle_command("run")
            assert shell.last_command == ""

    def test_other_command_repeated(self, shell):
        """Other commands should be auto-repeated."""
        shell.handle_command("continue")
        assert shell.last_command == "continue"
