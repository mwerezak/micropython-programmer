from __future__ import annotations

import re
from glob import iglob
from collections.abc import Sequence
from typing import TYPE_CHECKING, NamedTuple

if TYPE_CHECKING:
    from typing import Optional
    from configparser import ConfigParser
    from collections.abc import Iterator

__all__ = (
    'DEFAULT_CONFIG',
    'PackageSpec',
    'ProjectConfig',
)


DEFAULT_CONFIG = {
    'dependencies': {
        'packages': '', # whitespace/comma separated list
    },
    'deploy': {
        'files': '**.py', # whitespace/comma separated list
    }
}

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

class ProjectConfig(NamedTuple):
    files: Sequence[str]  # file patterns, supports glob
    packages: Sequence[PackageSpec]

    @staticmethod
    def load(cfg: ConfigParser) -> ProjectConfig:
        files = _split_list(cfg['deploy']['files'])
        packages = [
            PackageSpec.parse(pkg)
            for pkg in _split_list(cfg['dependencies']['packages'])
        ]
        return ProjectConfig(files, packages)

    def find_files(self, root_dir: str) -> Iterator[str]:
        for pattern in self.files:
            yield from iglob(pattern, root_dir=root_dir, recursive=True)



