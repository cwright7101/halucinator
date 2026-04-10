# HALucinator - Firmware rehosting through abstraction layer modeling.

## Supported Architectures

- ARM Cortex-M (cortex-m3, cortex-m4, etc.)
- ARM (full, e.g. arm926)
- AARCH64
- MIPS
- PowerPC (PPC)
- PowerPC 64 (PPC64)

## Setup in Docker

Clone this repo and submodules for avatar2 and qemu:
```bash
git clone <this repo>
git submodule update --init
```
A recursive clone can be done, but QEMU will then pull a lot of submodules that
may not be needed. QEMU's build process will pull the needed modules.

Build and run:
```bash
docker build -t halucinator ./
docker run --name halucinator -it halucinator bash
```
Building the Docker image may take a while (QEMU builds for all architectures).

Inside the container, start the UART peripheral device:
```bash
hal_dev_uart -i=1073811456
```

In a separate terminal, exec into the same container and run the firmware:
```bash
docker exec -it halucinator bash
./test/STM32/example/run.sh
```

You will eventually see in both terminals messages containing:
```
 ****UART-Hyperterminal communication based on IT ****
 Enter 10 characters using keyboard :
```

Enter 10 characters in the first terminal running `hal_dev_uart` and press
enter. You should see the text echoed followed by:

```txt
 Example Finished
```

To clean up: `docker rm halucinator`


## Setup in Virtual Environment

Tested on Ubuntu 20.04 and 22.04.

1. Clone the repo and submodules:
    ```bash
    git clone <this repo>
    git submodule update --init
    ```

2. Install system dependencies:
    ```bash
    ./install_deps.sh
    ```

3. Create and activate a Python 3 virtual environment:
    ```bash
    python3 -m venv ~/.virtualenvs/halucinator
    source ~/.virtualenvs/halucinator/bin/activate
    ```
    Or if using virtualenvwrapper: `mkvirtualenv -p $(which python3) halucinator`

4. Install HALucinator and build QEMU:
    ```bash
    ./setup.sh
    ```
    This installs avatar2, halucinator, and builds QEMU for all supported
    architectures. QEMU builds take 20+ minutes the first time.

### Note on setting HALUCINATOR_QEMU_*

You can override the QEMU binary used by HALucinator by setting the
appropriate environment variable for your target architecture:

```sh
export HALUCINATOR_QEMU_ARM=<full path to your qemu-system-arm>
export HALUCINATOR_QEMU_ARM64=<full path to your qemu-system-aarch64>
export HALUCINATOR_QEMU_MIPS=<full path to your qemu-system-mips>
export HALUCINATOR_QEMU_PPC=<full path to your qemu-system-ppc>
export HALUCINATOR_QEMU_PPC64=<full path to your qemu-system-ppc64>
```

If not set, HALucinator looks for QEMU in `deps/build-qemu/<arch>-softmmu/`.

If using virtual environments these can be set in `$VIRTUAL_ENV/bin/postactivate`
and removed in `$VIRTUAL_ENV/bin/predeactivate`.

### Optional: GrammaTech GTIRB Support

HALucinator includes utilities for binary analysis using
[GTIRB](https://github.com/GrammaTech/gtirb) (coverage parsing, stack trace
analysis). These are optional and only needed if you work with GTIRB IR files.

```bash
pip install gtirb gtirb-capstone gtirb-functions
```

This enables:
- `halucinator.util.gtirb_common` — load and query GTIRB IR files
- `halucinator.util.parse_coverage` — coverage analysis from execution traces
- `halucinator.util.parse_stack_trace` — stack trace parsing with GTIRB symbols

### Optional: Symbol Extraction with angr

To auto-generate address files from ELF binaries:

```bash
pip install angr
hal_make_addr -b <path_to_elf> -o addrs.yaml
```

## Running

Running Halucinator requires a configuration file that lists the functions to
intercept and the handler to be called on that interception. These are usually split
across three files for portability.  The files are a memory file that
describes the memory layout, an intercept file that describes what to intercept
and a symbol/address file that maps addresses to symbol names.  Internally, HALucinator
concatenates these configs into one config with the last taking precidence. See the Config
File section below for full details

All of these commands assume you are in your halucinator virtual environment

```sh
halucinator  -c=<memory_file.yaml> -c=<intercept_file.yaml> -c=<address_file.yaml>
```

## Running an Example



###  STM32F469I Uart Example

To give an idea how to use Halucinator an example is provided in `test/STM32/example`.

#### Setup
Note: This was done prior and the files are in the repo in `test/STM32/example`.
If you just want to run the example without building it just go to Running UART Example below.

This procedure should be followed for other binaries.
In list below after the colon (:) denotes the file/cmd .


2. Copy binary to a dir of you choice and cd to it:  `test/STM32/example`
3. Create binary file: `<halucinator_repo_root>/src/tools/make_bin.sh Uart_Hyperterminal_IT_O0.elf` creates `Uart_Hyperterminal_IT_O0.elf.bin`
4. Create Memory Layout (specifies memory map of chip): `Uart_Hyperterminal_IT_O0_memory.yaml`
5. Create Address File (maps function names to address): `Uart_Hyperterminal_IT_O0_addrs.yaml`
6. Create Intercept File (defines functions to intercept and what handler to use for it): `Uart_Hyperterminal_IT_O0_config.yaml`
7. (Optional) create shell script to run it: `run.sh`

Note: Symbols used in the address file can be created from an elf file with symbols
using `hal_make_addr`. This requires installing angr in halucinator's virtual environment.
This was used to create `Uart_Hyperterminal_IT_O0_addrs.yaml`

To use it the first time you would install angr (e.g. `pip install angr` from
the halucinator virtual environment)

```sh
hal_make_addr -b <path to elf file>
```

#### Running UART Example

Start the UART Peripheral device,  this a script that will subscribe to the Uart
on the peripheral server and enable interacting with it.

```bash
hal_dev_uart -i=1073811456
```

In separate terminal start halucinator with the firmware.

```bash
workon halucinator
halucinator -c=test/STM32/example/Uart_Hyperterminal_IT_O0_config.yaml \
  -c=test/STM32/example/Uart_Hyperterminal_IT_O0_addrs.yaml \
  -c=test/STM32/example/Uart_Hyperterminal_IT_O0_memory.yaml --log_blocks -n Uart_Example

# or use the convenience script:
bash test/STM32/example/run.sh
```
Note the `--log_blocks` and `-n` are optional.

You will eventually see in both terminals messages containing
```
 ****UART-Hyperterminal communication based on IT ****
 Enter 10 characters using keyboard :
```

Enter 10 Characters in the first terminal running `hal_dev_uart` press enter
should then see text echoed followed by.

```txt
 Example Finished
```

#### Stopping

Press `ctrl-c`. If for some reason this doesn't work kill it with `ctrl-z`
and `kill %`, or `killall -9 halucinator`

Logs are kept in the `tmp/<value of -n option>`. e.g `tmp/Uart_Example/`

## Config file

How the emulation is performed is controlled by a yaml config file.  It is passed
in using a the -c flag, which can be repeated with the config file being appended
and the later files overwriting any collisions from previous file.  The config
is specified as follows.  Default field values are in () and types are in <>

```yaml
machine:   # Optional, describes qemu machine used in avatar entry optional defaults in ()
           # if never specified default settings as below are used.
  arch: (cortex-m3)<str>,
  cpu_model: (cortex-m3)<str>,
  entry_addr: (None)<int>,  # Initial value to pc reg. Obtained from 0x0000_0004
                        # of memory named init_mem if it exists else memory
                        # named flash
  init_sp: (None)<int>,     # Initial value for sp reg, Obtained from 0x0000_0000
                        # of memory named init_mem if it exists else memory
                        # named flash
  gdb_exe: ('gdb-multiarch')<path> # Path to gdb to use


memories:  #List of the memories to add to the machine
  - name: <str>,       # Required
    base_addr:  <int>, # Required
    size: <int>,       # Required
    perimissions: (rwx)<r--|rw-|r-x>, # Optional
    file: filename<path>   # Optional Filename to populate memory with, use full path or
                      # path relative to this config file, blank memory used if not specified
    emulate: class<AvatarPeripheral subclass>    # Class to emulate memory

peripherals:  # Optional, A list of memories, except emulate field required

intercepts:  # Optional, list of intercepts to places
  - class:  <BPHandler subclass>,  # Required use full import path
    function: <str>     # Required: Function name in @bp_handler([]) used to
                        #   determine class method used to handle this intercept
    addr: (from symbols)<int>  # Optional, Address of where to place this intercept,
                               # generally recommend not setting this value, but
                               # instead setting symbol and adding entry to
                               # symbols for this makes config files more portable
    symbol: (Value of function)<str>  # Optional, Symbol name use to determine address
    class_args: ({})<dict>  # Optional dictionary of args to pass to class's
                       # __init__ method, keys are parameter names
    registration_args: ({})<dict>  # Optional: Arguments passed to register_handler
                              # method when adding this method
    run_once: (false)<bool> # Optional: Set to true if only want intercept to run once
    watchpoint: (false)<bool> # Optional: Set to true if this is a memory watch point

symbols:  # Optional, dictionary mapping addresses to symbol names, used to
          # determine addresses for symbol values in intercepts
  addr0<int>: symbol_name<str>
  addr1<int>: symbol1_name<str>

elf_program:  # For more info on this section see doc/c_intercepts.md
  name:  (None)<str>    #  Required, used to reference symbols from the elf program
                        #  in normal intercepts

  build: {cmd: (None)<str>, dir: (None)<str>, module_relative: (None)<str>}
          # Optional: If specified the cmd: will be executed from dir.
          # dir is relative to the directory of this config
          # If module_relative is not None the string  will be used to import
          # a python module and dir will relative to the directory of that module.

  elf: main.elf  # Path to the elf file (if full path give it is used/else is
                 # assumed to be relative to location of this file

  elf_module_relative: (None)<str>  # The full path for a python module that the
                                    # elf file should be loaded from

  execute_before: (True)<bool>      # This program should execute before the
                                    # entry point specified in config file

  exit_function: (exit)<str>        # Symbol when executed, execution should be
                                    # redirected to entry_ point

  intercepts:                       # Optional, list of intercepts
    - handler: <str>                # Name of the function to redirect execution to
      symbol:  <str>                # Either symbol/addr is required.  Specifies place
      addr: <int>                   # in firmware to be redirected to handler
      options: <arch specific>      # Optional passed to the rewriter to specify
                                    # for example could be use to specify arm/thumb mode

options: # Optional, Key:Value pairs you want accessible during emulation

```

The symbols in the config can also be specified using one or more symbols files
passed in using -s. This is a csv file each line defining a symbol as shown below

```csv
symbol_name<str>, start_addr<int>, last_addr<int>
```

## Testing

HALucinator has a comprehensive test suite with 28,600+ tests achieving 84% code coverage.

### Running Unit Tests

```bash
# Run all CI-safe tests
PYTHONPATH=src:test/pytest/helpers python3 -m pytest test/pytest/ \
  -m "not slow_zmq and not needs_root" \
  -p no:timeout --tb=short

# Run with coverage
PYTHONPATH=src:test/pytest/helpers python3 -m pytest test/pytest/ \
  -m "not slow_zmq and not needs_root" \
  -p no:timeout --cov=halucinator --cov-report=term-missing
```

### Running E2e Firmware Tests

These require a built QEMU (run `./build_qemu.sh` first) and the
`HALUCINATOR_QEMU_ARM` environment variable set.

```bash
export HALUCINATOR_QEMU_ARM=<path to qemu-system-arm>
bash ./test/STM32/example/run_test.bash
bash ./test/zephyr/zephyr_fs/run_tests.bash
bash ./test/zephyr/frdm_k64f_UART_Excellent_Test/run_tests.bash
bash ./test/zephyr/olimex_stm32_h103_UART_Excellent_test/run_tests.bash
bash ./test/firmware-rehosting/p2im-drone/run_tests.bash
```

### Test Markers

Tests are categorized with pytest markers defined in `conftest.py`:

- `slow_zmq`: Tests that use real zmq sockets/threads (may hang in combined runs)
- `needs_root`: Tests that require root privileges (raw sockets, scapy)

### CI/CD

The GitHub Actions workflow (`.github/workflows/virtual-environment-tests.yml`)
runs on every push and pull request to master. It builds QEMU (cached),
runs all e2e firmware tests, and runs the full pytest suite with coverage.

## Available BP Handler Families

- **generic**: Common handlers (ReturnZero, SkipFunc, Counter, Timer, etc.)
- **stm32f4**: STM32F4 HAL (UART, GPIO, SPI, ethernet, timers, WiFi)
- **libopencm3**: libopencm3 (ADC, DMA, flash, GPIO, RCC, SPI, timer, USART)
- **atmel_asf_v3**: Atmel ASF (contiki, ethernet, radio, SD/MMC, timers, USART)
- **mbed**: Mbed OS (boot, serial, timer)
- **vxworks**: VxWorks RTOS (boot, filesystem, ethernet, interrupts, scheduler, tasks)
- **zephyr**: Zephyr RTOS (filesystem, UART)