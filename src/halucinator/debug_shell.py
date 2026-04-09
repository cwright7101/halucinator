from __future__ import annotations

import re
import time
from typing import Any, Callable, Dict, List, Optional, Tuple, Union

from prompt_toolkit import PromptSession, prompt
from prompt_toolkit.completion import NestedCompleter
from IPython.terminal.embed import InteractiveShellEmbed

from halucinator.bp_handlers.debugger import Debugger, HalPrompt, MemoryMatch
from avatar2 import TargetStates

THREAD_TIMEOUT = 1.0
THREAD_SLEEP = 0.00001
PC_REGISTER = "pc"
SP_REGISTER = "sp"
CommandFunc = Callable[["DebugShell", str], None]


class DebugShell:
    command_handlers: Dict[str, CommandFunc] = {}
    short_commands: Dict[str, str] = {}
    extra_help: Dict[str, str] = {}

    def __init__(self, debugger: Debugger) -> None:
        self.debugger = debugger
        self._prompt_session: PromptSession[Any] = PromptSession()
        self.ipshell = InteractiveShellEmbed(
            banner1='Starting IPython shell. Type "exit" to close.\n',
            exit_msg="Closing IPython Shell",
        )
        self.hal_prompt = HalPrompt(self.ipshell, debugger)
        self.ipshell.prompts = self.hal_prompt
        self.last_command = ""
        self.examine_nextaddr = 0
        self.examine_repeat = 1
        self.examine_width = 2
        self.examine_format = "x"
        self.listing_addr: Optional[int] = None
        self.listsize = 10

    def nested_completions(self) -> Dict[str, Any]:
        """ Build a nested completion dictionary to support options for info. """
        comp_dict: Dict[str, Any] = {
            cmd: None for cmd in list(DebugShell.command_handlers.keys())
        }

        comp_dict["info"] = {
            "break": None,
            "breakpoints": None,
            "watch": None,
            "watchpoints": None,
            "reg": None,
            "registers": None,
            "all-registers": None,
            "halbreak": None,
            "halbreakpoints": None,
        }

        return comp_dict

    def start_prompt(self) -> None:
        """ Starts a blocking interactive debug shell on stdio. """
        completer = NestedCompleter.from_nested_dict(self.nested_completions())
        self.exiting = False

        # TODO remove these prints when they're no longer needed
        print("This debug shell is an early work-in-progress.")
        print('Type "python" to switch to an IPython shell.')
        try:
            while not self.exiting:
                entry = self._prompt_session.prompt(
                    self.get_prompt_prefix(),
                    completer=completer,
                    complete_while_typing=False,
                )
                self.handle_command(entry)
        except EOFError:
            pass

    def get_prompt_prefix(self) -> Any:
        """ Returns a prefix for the shell prompt. """
        # This prompt is currently mostly identical to the IPython one for now,
        # except we add "Debug" at the start. One or both of these prompts
        # should probably be changed more substantially in the future.
        return [("ansigreen bold", "(HALr-gdb) ")]

    def handle_command(self, entry: str) -> None:
        """ Handle a single command line as if specified in the prompt.

        Parameters:
            entry: The input text.
        """
        entry_split = entry.split(maxsplit=1)
        command = entry_split[0] if len(entry_split) > 0 else ""
        args = entry_split[1] if len(entry_split) > 1 else ""

        if not command:
            command = self.last_command

        # Special case for handling slash as parse separator;
        # we move it to the beginning of the argument list
        slashsep = re.match(r"^([a-z]+)(/.+)", command)
        if slashsep:
            args = slashsep.group(2) + " " + args
            command = slashsep.group(1)

        try:
            command, handler = DebugShell.lookup_command(command)
            handler(self, args)

            # There are some commands we don't auto-repeat because it's
            # dangerous or just redundant.
            if command in {"run", "help"}:
                self.last_command = ""
            else:
                self.last_command = command
        except LookupError as e:
            print(e.args[0])
            return

    def validate_memory_range(self, s_addr: int, e_addr: int) -> bool:
        """Confirm or deny that the memory range we are about to access falls
        within a known/mapped memory region. This prevents hitting an
        exception deeper in the stack.
        """
        mmi: Optional[MemoryMatch] = self.debugger.memory_info(s_addr)
        # Fail if starting address is not present, or if end is not in same memory.
        if mmi is None or e_addr > mmi.addr_end:
            return False
        else:
            return True

    @classmethod
    def lookup_command(cls, name: str) -> Tuple[str, CommandFunc]:
        """ Searches for and returns a matching command.

        Parameters:
            name: A short name, full name, or prefix of any registered command.
        Raises:
            LookupError if no unambiguous match is found.
        """
        # Translate short commands like "b" to long ones like "break"
        long_name = cls.short_commands.get(name)
        if long_name is not None:
            name = long_name

        # Return an exact match if found
        handler = cls.command_handlers.get(name)
        if handler is not None:
            return (name, handler)

        # Try to find a command that starts with the specified string
        matched: List[str] = []
        for key in cls.command_handlers.keys():
            if key.startswith(name):
                matched.append(key)
        if len(matched) == 0:
            raise LookupError(f'Undefined command: "{name}". Try "help".')
        if len(matched) > 1:
            raise LookupError(
                f'Ambiguous command "{name}": {", ".join(matched)}.'
            )
        name = matched[0]
        return name, cls.command_handlers[name]

    @classmethod
    def command(
        cls, names: Union[str, List[str]], extra_help: Optional[str] = None
    ) -> Callable[[CommandFunc], CommandFunc]:
        """ Decorator function for registering shell commands.

        Parameters:
            names:
                One or more names for the command.
                Only the first name specified is used for autocompletion.
                Others can be used for short forms. Note that any prefix of the
                command name that cannot ambiguously refer to another command
                can be used to invoke it, so short names only need to be
                specified to disambiguate (i.e. "b" for break, not backtrace)
                or for non-prefix abbreviations (i.e. "bt" for backtrace).
            extra_help:
                Optional string to supply when asking for help on this particular command.

        Decorates: A command handler function.
            Parameters for command handler:
                DebugShell state: the current DebugShell instance.
                str args: arguments from the shell input
            The docstring of this function is used to populate the help text.
        """

        if type(names) == str:
            name = names
        else:  # List[str]
            name = names[0]
            for short_name in names[1:]:
                cls.short_commands[short_name] = name
        if extra_help:
            cls.extra_help[name] = extra_help.strip()

        def register_command(func: CommandFunc) -> CommandFunc:
            cls.command_handlers[name] = func
            return func

        return register_command


def _trim_docstring(doc: Optional[str]) -> Tuple[str, List[str]]:
    """ Trims unnecessary whitespace from a docstring.

    Splits the docstring into a summary and the longer multi-line details.
    Leading spaces up to the minimum indent level are removed from every
    line, and empty lines at the beginning and end of the details list are
    removed.
    """
    if doc is None:
        return "", []

    lines = doc.expandtabs().splitlines()
    summary = lines[0] if lines else ""
    lines = [line.rstrip() for line in lines[1:]]
    indent = 80
    for line in lines:
        if line:
            indent = min(indent, len(line) - len(line.lstrip()))
    lines = [line[indent:] for line in lines]
    while lines and not lines[0]:
        lines.pop(0)
    while lines and not lines[-1]:
        lines.pop()

    return summary, lines


# Display helpers
def _display_mem_numeric(
    md: List[int],
    addr: int,
    repeat: int,
    e_per_row: int,
    e_size: int,
    dispfmt: str,
) -> None:
    ltext = ""
    p_size = 10
    p_pfx = ""
    p_fmtchar = dispfmt
    if dispfmt == "x":
        p_size = e_size * 2 + 2
        p_pfx = "#0"
    elif dispfmt == "d":
        # Calculate largest field for an integer of specified size
        p_size = len(str(2 ** (e_size * 8)))
    else:
        print("TODO: implement p_size for other formats")
    p_fmt = p_pfx + str(p_size) + p_fmtchar
    for idx in range(repeat):
        if ltext == "":
            ltext += f"{addr + idx * e_size:#010x}: "
        ltext += f"{md[idx]:{p_fmt}} "
        if idx % e_per_row == e_per_row - 1:
            print(ltext)
            ltext = ""
    if ltext:
        print(ltext)


def _display_mem_chars(md: List[int], addr: int, repeat: int) -> None:
    """ Display memory as combined integer/character dump.
    TODO: Only supports 1-byte characters at present. """
    ltext = ""
    for idx in range(repeat):
        if ltext == "":
            ltext += f"{addr + idx:#010x}: "
        if md[idx] < 32 or md[idx] > 127:
            orep = f"'\\{md[idx]:03o}'"
            if md[idx] > 127:
                md[idx] = md[idx] - 256
        else:
            orep = f"'{chr(md[idx])}'"
        ltext += f"{int(md[idx]):4} {orep:6} "
        if idx % 8 == 7:
            print(ltext)
            ltext = ""
    if ltext:
        print(ltext)


def debug_repeat_n(
    state: DebugShell, oper: Callable[[], bool], count: int
) -> None:
    """Wrapper to allow a function to be called more than once, waiting
    for debugger to run to completion each time."""
    print(f"Running {oper} {count} times")
    for ct in range(count):
        print(f"Iteration {ct}")
        oper()
        begin_wait = time.time()
        while True:
            time.sleep(THREAD_SLEEP)
            target_state = state.debugger.get_target_state()
            if (
                target_state == TargetStates.STOPPED
                or target_state == TargetStates.EXITED
            ):
                break
            elif time.time() - begin_wait >= THREAD_TIMEOUT:
                print("Timeout waiting for debugger to return.")
                return


def addr_to_symoffs(state: DebugShell, addr: int) -> Optional[str]:
    # See debugger.py:_reload_hal_config
    # This isn't actually part of avatar - it's inserted into it (?)
    # and so typing it through mypy as if it were is a bit suspect.
    config = state.debugger.avatar.config  # type: ignore
    symoffs = config.get_symbol_offset(addr)

    if symoffs is None:
        return None
    return f"<{symoffs[0]}+{symoffs[1]}>"


def numerate_args(
    args: List[str], starok: bool = False
) -> Optional[List[int]]:
    i_args = []

    for a in args:
        if a.startswith("*"):
            if starok:
                a = a[1:]
            else:
                print("Was not expecting an address argument.")
                return None
        try:
            i_args.append(int(a, base=0))
        except ValueError:
            print(f"I don't understand {a}, was expecting a number.")
            return None
    return i_args


@DebugShell.command("help")
def help(state: DebugShell, args: str) -> None:
    """ Displays the help text.

    USAGE
    help -- Displays a list of all commands with summarized help
    help <command> -- Displays detailed help text for a single command
    """

    # Display the list of commands with summarized help for each
    if not args:
        print('Type "help <command>" for more details about a command.')
        print("List of commands:\n")
        maxlen = max([len(name) for name in DebugShell.command_handlers])
        for name, func in sorted(DebugShell.command_handlers.items()):
            doc_short = ""
            if func.__doc__ is not None:
                doc_short = func.__doc__.splitlines()[0].strip()
            if doc_short:
                print(f"{name.ljust(maxlen)} -- {doc_short}")
            else:
                print(name)
        return

    # Display detailed help for a single command
    try:
        name, func = DebugShell.lookup_command(args.strip())

        aliases = []
        for short, full in DebugShell.short_commands.items():
            if full == name:
                aliases.append(short)
        summary, details = _trim_docstring(func.__doc__)
        if name in DebugShell.extra_help:
            details = [DebugShell.extra_help[name]]
        if summary:
            print(f"{name} -- {summary}")
        else:
            print(name)
        if aliases:
            print("Alias: " + " ".join(aliases))
        if details:
            print("\n" + "\n".join(details))
        elif not summary:
            print("\nNo help text exists for this command.")
    except LookupError as e:
        print(e.args[0])
        return


@DebugShell.command(["quit", "exit"])
def quit_command(state: DebugShell, args: str) -> None:
    """ Closes this shell and exits. """
    state.exiting = True


@DebugShell.command(["python", "ipython"])
def python_shell(state: DebugShell, args: str) -> None:
    """ Starts an interactive Python shell.

    USAGE
    python -- Starts an interactive Python shell.
    python <expression> -- Evaluates a single Python expression.

    The started Python session is based on IPython. Type "exit" or send an
    EOF (Ctrl-D) to exit the Python console and return to a debug prompt.
    If the "python" command is later invoked again within the same debug
    session, the state and history from the previous invocation will still
    be present.

    Exposed Python namespace:
    debug -- May be used to examine or control the current debug session.
    """
    try:
        state.ipshell.user_ns["debug"] = state.debugger
        if args:
            result = state.ipshell.ev(args)
            if result is not None:
                print(repr(result))
        else:
            state.ipshell(local_ns=state.ipshell.user_ns)
    except:
        print("Unhandled exception. Returning to debug shell.")


@DebugShell.command("continue")
def continue_command(state: DebugShell, args: str) -> None:
    """ Continues running the program until the next breakpoint or error. """

    # TODO: `cont` should theoretically support an argument but this
    # seems riskier than doing this for step and next because we can't
    # estimate what kind of timeout might make sense.
    state.debugger.cont()


@DebugShell.command(["stepi", "si"])
def stepi_command(state: DebugShell, args: str) -> None:
    """ Single step by one instruction, or multiple if given an argument. """

    if state.debugger.get_target_state() != TargetStates.STOPPED:
        print("Target is not stopped, cannot step.")
        return

    i_args = numerate_args(args.split())
    if i_args is None:
        # Already reported a error, exit now
        return
    if len(i_args) > 1:
        print("Command doesn't accept multiple arguments")
    elif len(i_args) == 1 and i_args[0] > 0:
        # For multiple step, we need to wait for debugger to be ready after each step
        debug_repeat_n(state, state.debugger.step, i_args[0])
    else:
        # For single step, we just return back to the user
        state.debugger.step()


@DebugShell.command(["nexti", "ni"])
def nexti_command(state: DebugShell, args: str) -> None:
    """ Next instruction, stepping over function calls; or multiple if given an argument. """

    if state.debugger.get_target_state() != TargetStates.STOPPED:
        print("Target is not stopped, cannot step.")
        return

    i_args = numerate_args(args.split())
    if i_args is None:
        # Already reported a error, exit now
        return
    if len(i_args) > 1:
        print("Command doesn't accept multiple arguments")
    elif len(i_args) == 1 and i_args[0] > 0:
        # For multiple next, we need to wait for debugger to be ready after each next
        debug_repeat_n(state, state.debugger.next, i_args[0])
    else:
        # For single next, we just return back to the user
        state.debugger.next()


@DebugShell.command("finish")
def finish_command(state: DebugShell, args: str) -> None:
    """ Run until return from current stack frame. """
    state.debugger.finish()


@DebugShell.command(["break", "b"])
def break_command(state: DebugShell, args: str) -> None:
    """Set breakpoint at specified location.
    break [LOCATION]
    If present, LOCATION must be an address.
    With no LOCATION, uses current execution address of the selected
    stack frame.
    """

    if ":" in args:
        # Set breakpoint at file:line
        print("Setting filename for breakpoint not supported.")
        return

    if args == "" or args.startswith("*") or args.lower().startswith("0x"):
        if args == "":
            # Set breakpoint at current PC
            addr = state.debugger.read_register(PC_REGISTER, False)
        elif args.startswith("*"):
            # Set breakpoint at address (* prefix)
            try:
                addr = int(args[1:], base=0)
            except ValueError:
                print(f"Don't understand how to set a breakpoint at {args}")
                return
        else:
            # Set breakpoint at address
            try:
                addr = int(args, base=0)
            except ValueError:
                print(f"Don't understand how to set a breakpoint at {args}")
                return

        state.debugger.set_debug_breakpoint(addr)
    else:
        # Set breakpoint at line
        print("TODO: translate line number to address for breakpoint")


@DebugShell.command("delete")
def delete_command(state: DebugShell, args: str) -> None:
    """ Delete all or some breakpoints.
    Usage: delete [BREAKPOINTNUM]...
    Arguments are breakpoint numbers with spaces in between.
    To delete all breakpoints, give no argument.
    """

    # We can't modify the dictionary from an iterator relying on it
    all_keys = list(state.debugger.list_debug_breakpoints().keys())

    argwords = args.split()
    if len(argwords) > 0 and argwords[0].startswith("b"):
        # This allows us to accept the more verbose commands:
        # `delete b <n>`
        # `delete break <n>`
        # `delete breakpoints <n>`
        argwords = argwords[1:]

    if len(argwords) == 0:
        confirm: str = prompt("Delete all breakpoints? (y or N) ")
        if confirm.lower() == "y" or confirm.lower() == "yes":
            for bpnum in all_keys:
                state.debugger.remove_debug_breakpoint(bpnum)
        return

    i_args = numerate_args(argwords)
    if i_args is not None:
        for bpnum in i_args:
            if bpnum in all_keys:
                state.debugger.remove_debug_breakpoint(bpnum)
            else:
                print(f"There is no breakpoint numbered {bpnum}")


@DebugShell.command("clear")
def clear_command(state: DebugShell, args: str) -> None:
    """ Clear breakpoint at specified location.
    With no argument, clears all breakpoints in the line that the selected frame
    is executing in.
    If an argument is provided, it should specify an address location.
    """

    i_args = numerate_args(args.split(), starok=True)
    if i_args is None or len(i_args) > 1:
        # We were passed something that's not legal
        return
    elif len(i_args) == 0:
        # No argument is a special case, not an error
        addr = state.debugger.read_register(PC_REGISTER, False)
    else:
        addr = i_args[0]

    to_remove = []
    for bpnum, baddr in state.debugger.list_debug_breakpoints().items():
        if baddr == addr:
            to_remove.append((bpnum, baddr))

    if len(to_remove) == 0:
        print(f"No breakpoint found at address {addr:#x}")
    else:
        for bpnum, baddr in to_remove:
            print(f"Removing breakpoint {bpnum} at {baddr:#x}")
            state.debugger.remove_debug_breakpoint(bpnum)


@DebugShell.command(
    "x",
    """
/FMT (optional) specifies the number, format, and size of the output.
If absent, the most recent settings will be reused. If present, it must
include at least one of the following, and can include any number;
they must be in the specified order.
  N - number of units to display (for example 10 units)
  f - printing format
      x - hexadecimal integers
      d - decimal integers
      c - characters (as integers, and decoded as ASCII-7)
  u - unit size
      b - bytes - 1 byte per unit
      h - half-words - 2 bytes per unit
      w - words - 4 bytes per unit
      g - 'giant' words - 8 bytes per unit)
ADDRESS (optional) may be specified in decimal or hex. A '*' prefix
is allowed, but ignored. If absent, the memory dump will continue
at the address where it last completed.
""",
)
def examine_mem_command(state: DebugShell, args: str) -> None:
    """ Examine memory: x/FMT ADDRESS.
    /FMT is optional, but if present must include one of the following
      N - number of units to display
      f - printing format (x, d, c)
      u - unit size (b=1, h=2, w=4, g=8)
    ADDRESS may be specified in decimal or hex
    """

    # Currently does not handle:
    # - Negative repeat counts (indicates to start before the address)
    # - Swapping order of format and size letters
    # - Strings, because they can read an arbitrary amount of memory
    # - Unsigned, octal, binary, float
    # - Instructions, addresses

    nextaddr = state.examine_nextaddr
    repeat = state.examine_repeat
    dispfmt = state.examine_format
    width = state.examine_width
    size_to_width = {"b": 1, "h": 2, "w": 4, "g": 8}

    # Should be 'xduotacfsi'
    parseargs = re.fullmatch(
        r"\s*(?P<nfu>/([0-9]*)([xdc]*)([bhwg]*))?\s*\*?(?P<addr>([0-9a-fA-FxX]+))?",
        args,
    )
    if parseargs is None:
        print(
            f"Unable to parse arguments '{args}', or feature may not be supported."
        )
        return
    if parseargs.group("nfu") is not None:
        # We got a number/format/size specification so we will adjust settings
        # The typing here is just an annoying PITA because we receive these
        # as strings but then want to treat some of them as numbers and empty
        # strings as None.
        n_repeat: Optional[Union[int, str]] = None
        n_dispfmt: Optional[str] = None
        n_usize: Optional[str] = None
        n_width: Optional[int] = None
        (n_repeat, n_dispfmt, n_usize) = parseargs.groups()[1:4]

        n_repeat = None if n_repeat == "" else int(n_repeat)

        # Special cases:
        if dispfmt == "i":
            # i - unit width is ignored, but default is not changed
            n_width = width
            width = 4
        elif dispfmt == "s" and n_usize == "":
            # s - unit width defaults to b unless explicitly given
            # and default is never changed
            width = 1
        elif n_usize != "":
            # Default case if specified, width will be updated
            n_width = size_to_width[n_usize]
            width = n_width
        else:
            # Default case if not specified, no update needed
            n_width = None
    else:
        n_repeat = None
        n_dispfmt = None
        n_width = None
    if parseargs.group("addr") is not None:
        try:
            nextaddr = int(parseargs.group("addr"), base=0)
        except ValueError:
            print(f"Couldn't understand the address {parseargs.group('addr')}")
            return

    # Update default values if they were changed
    # We don't update size because we may have selected a temporary custom value above
    if n_repeat is not None:
        state.examine_repeat = n_repeat
        repeat = n_repeat
    if n_dispfmt is not None and n_dispfmt != "":
        state.examine_format = n_dispfmt
        dispfmt = n_dispfmt

    if dispfmt == "c":
        if width > 1:
            print(f"Warning: wide characters (width={width}) not supported.")
        width = 1

    follow_addr = nextaddr + repeat * width
    if not state.validate_memory_range(nextaddr, follow_addr):
        print(f"Memory range {nextaddr:#x}-{follow_addr:#x} is not mapped.")
        return

    md = state.debugger.read_memory(
        addrs=nextaddr, size=width, words=repeat, raw=False,
    )

    if dispfmt in "xduot":
        epr = int(16 / width)
        _display_mem_numeric(md, nextaddr, repeat, epr, width, dispfmt)
    elif dispfmt == "c":
        _display_mem_chars(md, nextaddr, repeat)
    else:
        print(f"Examine format '{dispfmt}' not yet supported.")

    # Now we can update size and new starting address
    if n_width is not None:
        state.examine_width = n_width

    state.examine_nextaddr = follow_addr


@DebugShell.command("info")
def info_command(state: DebugShell, args: str) -> None:
    """ Generic command for showing things about the program being debugged.

    List of all info subcommands:
    info all-registers -- List of all registers and their contents, for selected stack frame.
    info breakpoints -- Status of specified breakpoints (all user-settable breakpoints if no argument).
    info functions -- All function names or those matching REGEXPs.
    info halbreakpoints -- Status of specifed HALucinator breakpoints.
    """
    # TODO: info line -- Core addresses of the code for a source line.
    # TODO: info watchpoints -- Core addresses of the code for a source line.

    asplit = args.split()
    if len(asplit) == 0:
        return help(state, "info")
    info_tgt = asplit[0]
    if len(asplit) > 1:
        resid_args = " ".join(asplit[1:])
    else:
        resid_args = ""

    if info_tgt.startswith("all-reg") or info_tgt.startswith("r"):
        for reg in state.debugger.list_all_regs_names():
            if resid_args == "" or resid_args == reg:
                val = state.debugger.target.read_register(reg)
                print(f"{reg:<16}{val:#010x}      {val:16}")
    elif info_tgt.startswith("b"):
        bpts = list(state.debugger.list_debug_breakpoints().items())
        if len(bpts) == 0:
            print("No breakpoints or watchpoints.")
        else:
            print("Num     Type           Disp Enb Address    What")
            for idx, addr in bpts:
                locstr = addr_to_symoffs(state, addr)
                if resid_args == "" or int(resid_args) == idx:
                    print(
                        f"{idx:<8}breakpoint     keep y   {addr:#010x} at {locstr}"
                    )
    elif info_tgt.startswith("f"):
        # See comment above
        config = state.debugger.avatar.config  # type: ignore
        symnames = config.get_symbol_list()
        for (n, addr) in symnames:
            if resid_args == "" or re.search(resid_args, n):
                # This name matches, so print it
                print(f"{addr:#x}\t{n}")

    elif info_tgt.startswith("h"):
        hbpts = list(state.debugger.list_hal_breakpoints().items())
        if len(hbpts) == 0:
            print("No HAL breakpoints.")
        else:
            print("Num     Type           Disp Enb Address    How")
            for idx, bpt in state.debugger.list_hal_breakpoints().items():
                if resid_args == "" or int(resid_args) == idx:
                    addr = bpt.address
                    cls = bpt.bp_class
                    hdlr = bpt.bp_handler
                    once = bpt.run_once
                    disp = "del" if once else "keep"
                    cls_mod = type(cls).__module__
                    cls_name = type(cls).__name__
                    hdlr_name = hdlr.__name__
                    # TODO - modify cls_mod to print full path only
                    # when there are multiple locations?
                    # if cls_mod.startswith("halucinator.bp_handlers."):
                    #    cls_mod = cls_mod[len("halucinator.bp_handlers.") :]
                    print(
                        f"{idx:<8}HALbreakpoint  {disp:<4} y   {addr:#010x} with {cls_mod}:{cls_name}.{hdlr_name}"
                    )


@DebugShell.command(["list"])
def command_listi(state: DebugShell, args: str) -> None:
    """ Print assembly listing. """

    if state.listing_addr is None:
        state.listing_addr = state.debugger.read_register(PC_REGISTER, False)
    if args == "":
        # No arguments is a special case and not an error: do it again
        pass
    else:
        if args.startswith("*"):
            try:
                state.listing_addr = int(args[1:], base=0)
            except ValueError:
                print(f"I don't understand how to list {args}")
        else:
            print("TODO - listing by line number not supported.")
    instrs = state.debugger.read_instructions(
        addr=state.listing_addr, num_instr=state.listsize + 1, hex_mode=False
    )

    # Update default start address for next listing to pick up where this left off
    state.listing_addr = int(instrs.pop(-1)[0])
    for (addr, mnem, operands) in instrs:
        locstr = addr_to_symoffs(state, int(addr))
        print(f"  {addr:#x} {locstr}:\t{mnem:<7} {operands}")


@DebugShell.command(["backtrace", "bt", "where"])
def backtrace(state: DebugShell, args: str) -> None:
    """ Prints a stack trace. """

    # This relies on _get_stack_trace() returning a gdb-like
    # call stack. Right now it does, but if it were changed
    # then the format we are seeing here would change.
    st = state.debugger._get_stack_trace()
    print(st)
