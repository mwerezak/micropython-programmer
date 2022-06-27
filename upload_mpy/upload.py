from __future__ import annotations

import struct
import logging
from enum import Enum
from serial import Serial
from typing import TYPE_CHECKING, NamedTuple

if TYPE_CHECKING:
    from typing import Optional


_log = logging.getLogger(__name__)

class Control(Enum):
    SOH = b'\x01'  # Ctrl-A
    ETX = b'\x03'  # Ctrl-C
    EOT = b'\x04'  # Ctrl-D
    ENQ = b'\x05'  # Ctrl-E

class ExecResult(NamedTuple):
    output: str
    exception: Optional[str]

class REPLError(Exception): pass

class MPyREPL:
    _linesep = b'\r\n'

    def __init__(self, serial: Serial):
        self.serial = serial
        self.use_raw_paste = True

    def interrupt_program(self) -> None:
        self.serial.write(Control.ETX.value)

    def _read_all(self, expected: bytes) -> bytes:
        result = b''
        while len(reply := self.serial.read_until(expected)):
            result += reply
        return result

    def _read_until(self, expected: bytes) -> bytes:
        result = bytearray()
        while not result.endswith(expected):
            result += self.serial.read_until(expected)
        return bytes(result)

    def _read_discard(self) -> None:
        while self.serial.in_waiting > 0:
            self.serial.read(self.serial.in_waiting)

    _raw_input_success = b'raw REPL; CTRL-B to exit\r\n>'
    def remote_exec(self, script_text: str) -> ExecResult:
        self.interrupt_program()
        self._read_discard()

        ## Enter raw input mode
        self.serial.write(Control.SOH.value)
        reply = self._read_all(b'>')
        if not reply.endswith(b'>'):
            raise REPLError('failed to enter raw input mode')

        ## try to use raw paste mode
        if self.use_raw_paste:
            try:
                session = RawPasteSession(self.serial)
                session.begin()
            except RawPasteError:
                self.use_raw_paste = False
                self._read_discard()
            else:
                session.write(script_text.encode())

                reply = self._read_until(Control.EOT.value)
                if not reply.endswith(Control.EOT.value):
                    raise REPLError(f'failed to execute command (response: {reply!r})')
                return self._collect_exec_result()

        ## fallback to regular raw input mode
        self.serial.write(script_text.encode())
        self.serial.write(Control.EOT.value)

        reply = self.serial.read(2)
        if reply != b'OK':
            raise REPLError(f'failed to execute command (response: {reply!r})')
        return self._collect_exec_result()

    def _collect_exec_result(self) -> ExecResult:
        output = bytearray()
        try:
            while not output.endswith(Control.EOT.value):
                output += self.serial.read_until(Control.EOT.value)
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

        return ExecResult(output, exception)


class RawPasteError(Exception): pass

class RawPasteSession:
    def __init__(self, serial: Serial):
        self.serial = serial
        self._buf = bytearray()
        self._window_len = None
        self._window = None

    def begin(self) -> None:
        self.serial.write(Control.ENQ.value)
        self.serial.write(b'A')
        self.serial.write(Control.SOH.value)
        reply = self.serial.read(2)
        if reply == b'R\x00':
            raise RawPasteError('the device understands the command but doesn’t support raw paste')
        elif reply != b'R\x01':
            raise RawPasteError('the device does not support raw paste')

        window_len = self.serial.read(2)
        self._window_len = struct.unpack('<H', window_len)[0]
        self._window = self._window_len

    def write(self, payload: bytes) -> None:
        self._buf += payload
        while len(self._buf) > 0:
            while self._window == 0 or self.serial.in_waiting > 0:
                reply = self.serial.read(1)
                if reply == Control.SOH.value:
                    self._window += self._window_len
                elif reply == Control.EOT.value:
                    self.serial.write(Control.EOT.value)
                    raise RawPasteError('device indicated abrupt end of input')
                else:
                    raise RawPasteError(f'unexpected reply: {reply!r}')

            nwrite = self.serial.write(self._buf[:self._window])
            self._window -= nwrite
            del self._buf[:nwrite]

        # end of data
        self.serial.write(Control.EOT.value)





if __name__ == '__main__':
    serial = Serial('/dev/ttyACM0', timeout=2)
    repl = MPyREPL(serial)
    # result = repl.remote_exec("print('Hello World!')")

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
