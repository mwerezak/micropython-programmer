from __future__ import annotations

import os
import logging
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from typing import Any
    from remote import RemoteREPL, ExecResult

_log = logging.getLogger(__file__)

_SCRIPT_DIR = os.path.join(os.path.dirname(__file__), 'scripts')

def clean_fs(remote: RemoteREPL, *, check: bool = False) -> ExecResult:
    _log.debug(f"clean fs")
    with open(os.path.join(_SCRIPT_DIR, 'clean_fs'), 'rt') as script_file:
        return remote.exec(script_file.read(), check=check)

def write_file(remote: RemoteREPL, target_path: str, f: Any, *, check: bool = False) -> ExecResult:
    _log.debug(f"write file: {target_path}")
    if hasattr(f, 'read'):
        content = f.read()
    else:
        content = f

    if isinstance(content, str):
        mode = 'wt'
    elif isinstance(content, bytes):
        mode = 'wb'
    else:
        raise ValueError('unsupported content')

    with open(os.path.join(_SCRIPT_DIR, 'write_file'), 'rt') as script_file:
        script = script_file.read().format(
            targetpath = target_path,
            mode = mode,
            content = content,
        )
        return remote.exec(script, check=check)

if __name__ == '__main__':
    from serial import Serial
    from remote import RemoteREPL
    serial = Serial('/dev/ttyACM0', timeout=2)
    repl = RemoteREPL(serial)
