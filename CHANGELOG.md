# Changelog

All notable changes to this project will be documented in this file.

## [Unreleased] - cwright/gt-tpcp-port

### Added
- **Multi-architecture support**: MIPS and PPC64 QEMU targets
- **BP handlers**: libopencm3 (ADC, DMA, flash, GPIO, RCC, SPI, timer, USART),
  atmel_asf_v3 (contiki, ethernet_ksz8851, rf233, sd_mmc, and more)
- **Debug adapter**: DAP protocol implementation for IDE debugging
- **Debug shell**: IPython-based interactive debug shell with memory inspection,
  breakpoint management, and register access
- **HAL QEMU base class**: shared logic for all QEMU target architectures
- **Peripheral models**: ADC, timer_model, tcp_stack
- **External devices**: ADC, opendps
- **Utils**: gtirb_common, parse_coverage, parse_stack_trace
- **VSCode extension support**: installer script and vsix_files directory
- **Docker**: updated Dockerfile and run_hal_docker.sh
- **Demo**: opendps firmware rehosting example
- **Extra tools**: BP handler parser, handler path management
- **CI/CD**: GitHub Actions workflow with QEMU build caching, e2e firmware
  tests, pytest with coverage reporting (84% coverage, 28,600+ tests)
- **E2e tests**: STM32 UART, Zephyr filesystem, Zephyr frdm_k64f UART,
  Zephyr olimex STM32 UART, p2im-drone firmware rehosting
- **Pytest markers**: `slow_zmq`, `needs_root` for CI test selection
- **Type annotations** throughout the codebase

### Changed
- Default GDB executable from `arm-none-eabi-gdb` to `gdb-multiarch`
- `main.py` refactored to use `target_archs.py` for architecture config
  instead of redundant inline lookup tables
- `target_archs.py` is now the single source of truth for ISA configuration
- QEMU path resolution uses `HALUCINATOR_QEMU_{ARM,ARM64,MIPS,PPC,PPC64}`
  environment variables
- `peripheral_server.py`: fixed `bytes(key)` to `key.encode("utf-8")` for
  Python 3 zmq compatibility
- `hal_dev_uart`: handles EOFError when stdin is /dev/null

### Fixed
- `gpio.py`: `setsockopt` changed to `setsockopt_string`
- `host_ethernet_server.py`: added `msg_id` parameter, fixed undefined vars
- VxWorks, Zephyr, STM32F4 handler bug fixes from GT/TPCP port

## [1.8.0] - 2024-01-23

### Added
- Ability to intercept code with compiled binary (C intercepts)
- Ability to add QEMU devices to machine
- PowerPC support
- AARCH64 support
- IRQ configuration documentation

### Changed
- Updated avatar-qemu for multi-arch support

## [1.7.0] - 2021-07-08

### Added
- VxWorks RTOS support (boot, dos_fs, errors, ethernet, interrupts,
  ios_dev, posix_logging, scheduler, sys_clock, tasks, ty_dev,
  vx_logging, vx_mem, yaf_fs)
- Docker support with Dockerfile and instructions

### Changed
- Updated avatar2 and avatar-qemu dependencies

## [1.6.0] - 2020-10-15

### Added
- Tutorial documentation (5 parts: prerequisites, overview, running
  UART example, UART deep dive, extending halucinator)
- Zephyr filesystem and UART support

## [1.5.0] - 2020-09-15

### Changed
- Updated scapy dependency to latest version
- Maintenance improvements

## [1.4.0] - 2019-11-19

### Fixed
- Python 3 conversion fixes

## [1.3.0] - 2019-07-16

### Changed
- Code reorganization for Python 3 (PR #2 by Teserakt-io)

## [1.2.0] - 2019-07-05

### Added
- Keystone support (dependency of avatar2)
- Safe YAML loading
- ZMQ updates

## [1.1.0] - 2019-07-03

### Added
- Python 3 support
- Code reorganization

## [1.0.0] - 2019-06-06

### Added
- Initial public release
- STM32 UART example
- Breakpoint handler framework
- Peripheral model framework with zmq-based IO
- External device framework (UART, ethernet)
- QEMU ARM target via avatar2
- Configuration via YAML files
