from __future__ import annotations

import re
import os
import logging
from glob import iglob
from collections.abc import Sequence
from configparser import ConfigParser
import subprocess
import shlex
from typing import TYPE_CHECKING, NamedTuple

if TYPE_CHECKING:
    from typing import Any, Optional
    from collections.abc import Iterator, Iterable
    from subprocess import CompletedProcess

__all__ = (
    'load_config',
    'PackageSpec',
    'ProjectConfig',
)

_log = logging.getLogger(__name__)

CONFIG_VERSION = '1'
DEFAULT_CONFIG = {
    'dependencies': {
        'packages': '', # whitespace/comma separated list
    },
    'deploy': {
        'files': '**.py', # whitespace/comma separated list
        'exclude-files': '',
        'mpy-cc': 'mpy-cross -O3 {scriptpath}',  # cross compiler command, must be in PATH
        'compile': '**.py',
        'exclude-compile': 'main.py',
    }
}

def load_config(cfg_path: str) -> ConfigParser:
    config = ConfigParser()
    config.read_dict(DEFAULT_CONFIG)

    # load config or create file if it does not exist
    if os.path.exists(cfg_path):
        if not os.path.isfile(cfg_path):
            raise RuntimeError(f"Can't read config, '{cfg_path}' is not a regular file!")
        _log.debug(f"Reading config from '{cfg_path}'")
        with open(cfg_path, 'rt') as f:
            config.read_file(f)
    else:
        _log.warning(f"Config file not found. Writing default config to '{cfg_path}' and exiting.")
        with open(cfg_path, 'wt') as f:
            config.add_section('config')
            config['config']['version'] = CONFIG_VERSION
            config.write(f)
        raise SystemExit(0)
    return config


def _split_list(strlist: str) -> list[str]:
    return [
        s.strip()
        for s in strlist
            .translate(str.maketrans(',', ' '))
            .split()
    ]

class PackageSpec(NamedTuple):
    name: str                      # package name for upip
    version: Optional[str] = None  # PEP440 version specifier

    def __str__(self) -> str:
        if self.version is not None:
            return self.name + self.version
        return self.name

    _version_pat = re.compile(r'(?P<name>\w+?)(?P<version>(~=|==|!=|<=|>=|<|>|===)\S+)?')
    @classmethod
    def parse(cls, s: str) -> PackageSpec:
        match = re.fullmatch(cls._version_pat, s)
        if match is None:
            raise ValueError(f'invalid package specifier: {s}')
        return cls(**match.groupdict())

class ConfigError(Exception): pass

class ProjectConfig(NamedTuple):
    search_files: Sequence[str]  # file patterns, supports glob
    exclude_files: Sequence[str]
    search_compile: Sequence[str]
    exclude_compile: Sequence[str]
    compile_cmd: str
    packages: Sequence[PackageSpec]

    @staticmethod
    def load(cfg: ConfigParser) -> ProjectConfig:
        if 'config' not in cfg or 'version' not in cfg['config']:
            raise ConfigError(f"could not read config version")

        version = cfg['config']['version']
        if version != CONFIG_VERSION:
            raise ConfigError(f"invalid config version '{version}'")

        packages = [
            PackageSpec.parse(pkg)
            for pkg in _split_list(cfg['dependencies']['packages'])
        ]

        return ProjectConfig(
            search_files = _split_list(cfg['deploy']['files']),
            exclude_files = _split_list(cfg['deploy']['exclude-files']),
            search_compile = _split_list(cfg['deploy']['compile']),
            exclude_compile = _split_list(cfg['deploy']['exclude-compile']),
            compile_cmd = cfg['deploy']['mpy-cc'],
            packages = packages,
        )

    @staticmethod
    def _search_files(root_dir: str, patterns: Iterable[str], exclude_patterns: Iterable[str]) -> Iterator[str]:
        exclude = set()
        for pattern in exclude_patterns:
            exclude.update(iglob(pattern))

        for pattern in patterns:
            for filename in iglob(pattern, root_dir=root_dir, recursive=True):
                if filename not in exclude:
                    yield filename

    def find_files(self, root_dir: str) -> Iterator[str]:
        return self._search_files(root_dir, self.search_files, self.exclude_files)

    def find_scripts(self, root_dir: str) -> Iterator[str]:
        return self._search_files(root_dir, self.search_compile, self.exclude_compile)

    def invoke_cc(self, script_path, **kwargs: Any) -> CompletedProcess:
        cmd = self.compile_cmd.format(scriptpath=script_path)
        return subprocess.run(shlex.split(cmd), **kwargs)

