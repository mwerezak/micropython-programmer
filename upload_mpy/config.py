from __future__ import annotations

import re
from glob import iglob
from collections.abc import Sequence
from typing import TYPE_CHECKING, NamedTuple

if TYPE_CHECKING:
    from typing import Optional
    from configparser import ConfigParser
    from collections.abc import Iterator, Iterable

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
        'exclude-files': '',
        'compile': '**.py',
        'exclude-compile': 'main.py',
        'compile-args': '-O3'
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
    search_files: Sequence[str]  # file patterns, supports glob
    exclude_files: Sequence[str]
    search_compile: Sequence[str]
    exclude_compile: Sequence[str]
    compile_args: Sequence[str]
    packages: Sequence[PackageSpec]

    @staticmethod
    def load(cfg: ConfigParser) -> ProjectConfig:
        packages = [
            PackageSpec.parse(pkg)
            for pkg in _split_list(cfg['dependencies']['packages'])
        ]

        return ProjectConfig(
            search_files = _split_list(cfg['deploy']['files']),
            exclude_files = _split_list(cfg['deploy']['exclude-files']),
            search_compile = _split_list(cfg['deploy']['compile']),
            exclude_compile = _split_list(cfg['deploy']['exclude-compile']),
            compile_args = cfg['deploy']['compile-args'].split(),
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



