from __future__ import annotations

import struct
import logging
from enum import Enum
from contextlib import contextmanager
from serial import Serial, SerialException
from typing import TYPE_CHECKING, NamedTuple

if TYPE_CHECKING:
    from typing import Optional, ContextManager


_log = logging.getLogger(__name__)

class Control(Enum):
    SOH = b'\x01'  # Ctrl-A
    STX = b'\x02'  # Ctrl-B
    ETX = b'\x03'  # Ctrl-C
    EOT = b'\x04'  # Ctrl-D
    ENQ = b'\x05'  # Ctrl-E

def _read_all(serial: Serial, expected: bytes) -> bytes:
    result = b''
    while serial.in_waiting > 0:
        result += serial.read_until(expected)
    return result

def _read_until(serial: Serial, expected: bytes) -> bytes:
    result = bytearray()
    while not result.endswith(expected) and serial.in_waiting > 0:
        result += serial.read_until(expected)
    return bytes(result)

def _read_discard(serial: Serial) -> None:
    while serial.in_waiting > 0:
        serial.read(serial.in_waiting)


class RemoteExecError(Exception): pass

class ExecResult(NamedTuple):
    output: str
    exception: Optional[str]

    def check(self) -> None:
        if self.exception is not None:
            raise RemoteExecError

class REPLError(Exception): pass
class RawPasteNotSupported(Exception): pass

class RemoteREPL:
    _linesep = b'\r\n'

    def __init__(self, serial: Serial):
        self.serial = serial
        self.use_raw_paste = True

    def interrupt_program(self) -> None:
        self.serial.write(Control.ETX.value)

    # useful since machine.soft_reset() seems to not work in raw input mode
    def soft_reset(self) -> None:
        self.interrupt_program()
        self.serial.write(Control.STX.value)
        self.serial.write(Control.EOT.value)

    def hard_reset(self) -> None:
        try:
            self.exec("import machine; machine.reset()")
        except SerialException:
            pass

    _raw_input_success = b'raw REPL; CTRL-B to exit\r\n>'
    @contextmanager
    def _raw_input_mode(self) -> ContextManager:
        ## Enter raw input mode
        self.serial.write(Control.SOH.value)
        reply = _read_all(self.serial, b'>')
        if not reply.endswith(b'>'):
            raise REPLError('failed to enter raw input mode')

        try:
            yield
        finally:
            self.serial.write(Control.STX.value)

    def exec(self, script_text: str, *, check: bool = False) -> ExecResult:
        self.interrupt_program()
        _read_discard(self.serial)

        with self._raw_input_mode():
            ## try to use raw paste mode
            payload = script_text.encode()
            if self.use_raw_paste:
                try:
                    self._raw_paste_write(payload)
                except RawPasteNotSupported:
                    self.use_raw_paste = False
                    _read_discard(self.serial)
                else:
                    return self._collect_exec_result(check)

            ## fallback to regular raw input mode
            self._regular_raw_write(payload)
            return self._collect_exec_result(check)

    def _regular_raw_write(self, payload: bytes):
        self.serial.write(payload)
        self.serial.write(Control.EOT.value)

        reply = self.serial.read(2)
        if reply != b'OK':
            raise REPLError(f'failed to execute command (response: {reply!r})')

    def _collect_exec_result(self, check: bool) -> ExecResult:
        output = bytearray()
        try:
            while not output.endswith(Control.EOT.value):
                read = self.serial.read_until(Control.EOT.value)
                output += read
                # _log.debug("Remote: " + read.decode(errors='replace'))
        except KeyboardInterrupt:
            self.interrupt_program()
            output += self.serial.read_until(Control.EOT.value)

        output = output.strip(Control.EOT.value).decode()

        exception = self.serial.read_until(Control.EOT.value)
        exception = exception.strip(Control.EOT.value)
        if len(exception) == 0:
            exception = None
        else:
            exception = exception.decode()

        result = ExecResult(output, exception)
        if check:
            result.check()
        return result

    def _raw_paste_write(self, payload: bytes):
        ## try to enter raw paste mode
        self.serial.write(Control.ENQ.value)
        self.serial.write(b'A')
        self.serial.write(Control.SOH.value)
        reply = self.serial.read(2)
        if reply == b'R\x00':
            raise RawPasteNotSupported('the device understands the command but doesn’t support raw paste')
        elif reply != b'R\x01':
            raise RawPasteNotSupported('the device does not support raw paste')

        win_size = self.serial.read(2)
        win_size = struct.unpack('<H', win_size)[0]

        win_rem = win_size  # bytes remaining in window
        wbuf = bytearray(payload)
        while len(wbuf) > 0:
            while win_rem == 0 or self.serial.in_waiting > 0:
                reply = self.serial.read(1)
                if reply == Control.SOH.value:
                    win_rem += win_size  # new window available
                elif reply == Control.EOT.value:
                    self.serial.write(Control.EOT.value)
                    raise REPLError('device indicated abrupt end of input')
                else:
                    raise REPLError(f'unexpected reply: {reply!r}')

            nwrite = self.serial.write(wbuf[:win_rem])
            win_rem -= nwrite
            del wbuf[:nwrite]

        # end of data
        self.serial.write(Control.EOT.value)
        reply = _read_until(self.serial, Control.EOT.value)
        if not reply.endswith(Control.EOT.value):
            raise REPLError(f'failed to execute command (response: {reply!r})')


if __name__ == '__main__':
    import sys
    import atexit
    # logging.basicConfig(stream=sys.stdout, level=logging.DEBUG)

    serial = Serial('/dev/ttyACM0', timeout=1)
    atexit.register(serial.close)

    repl = RemoteREPL(serial)
    # result = repl.exec("print('Hello World!')")

    blinky = """import time
from machine import Pin

PIN_GP = tuple(Pin(i, Pin.IN) for i in range(30))

SLOW_BLINK   = 1870  #ms
FAST_BLINK   = 170   #ms
STARTUP_TIME = 3000  #ms

PIN_LED = PIN_GP[25]
PIN_LED.init(Pin.OUT, value=False)


def blink(led_pin, interval):
    # (Pin, ms)
    led_pin.value(1)
    time.sleep_ms(interval)
    led_pin.value(0)
    time.sleep_ms(interval)

def elapsed_ms(t):
    # (tick) -> tickdelta
    return time.ticks_diff(time.ticks_ms(), t)

try:
    start_tick = time.ticks_ms()
    while elapsed_ms(start_tick) < STARTUP_TIME:
        blink(PIN_LED, FAST_BLINK//2)

    while True:
        blink(PIN_LED, SLOW_BLINK//2)
finally:
    PIN_LED.value(0)
"""
