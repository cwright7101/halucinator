"""UART-capture intercept for the GRBL CNC firmware.

`usart_putc(char c)` writes a single byte to USART2 and busy-waits on the
TXE status bit. Under emulation that bit never sets, so we intercept the
function: read the byte from r0 (AAPCS arg0), accumulate it, log on each
newline, and return immediately (skipping the spin-wait). This surfaces
the firmware's console output — the GRBL startup banner and `$`-settings
dump — as halucinator log lines.
"""
import logging

from halucinator import hal_log
from halucinator.bp_handlers.bp_handler import BPHandler, HandlerReturn, bp_handler
from halucinator.peripheral_models.uart import UARTPublisher

log = logging.getLogger(__name__)
logger = hal_log.getHalLogger()


class CncUart(BPHandler):
    def __init__(self, impl=UARTPublisher) -> None:
        self.model = impl
        self._line = bytearray()

    @bp_handler(["usart_putc"])
    def putc(self, qemu, bp_addr: int) -> HandlerReturn:
        char = qemu.regs.r0 & 0xFF
        # Publish the raw byte on the UART model so external_devices /
        # zmq consumers see it, mirroring a real serial console.
        self.model.write(0x40004400, bytes([char]))  # USART2 base
        if char == ord("\n"):
            logger.info("UART TX: %s", self._line.decode("latin-1").rstrip("\r"))
            self._line = bytearray()
        elif char != ord("\r"):
            self._line.append(char)
        return True, 0
