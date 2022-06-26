#!/usr/bin/python3

from __future__ import annotations

import logging
import re
import os
from glob import iglob
from argparse import ArgumentParser
from configparser import ConfigParser
from collections.abc import Sequence, Iterator
from typing import TYPE_CHECKING, NamedTuple
if TYPE_CHECKING:
    from typing import Any, Optional


_LOG = logging.getLogger()

DEFAULT_CONFIG = {
    'dependencies': {
        'packages': '', # whitespace/comma separated list
    },
    'deploy': {
        'files': '**.py', # whitespace/comma separated list
    }
}

def split_list(strlist: str) -> list[str]:
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
        files = split_list(cfg['deploy']['files'])
        packages = [
            PackageSpec.parse(pkg)
            for pkg in split_list(cfg['dependencies']['packages'])
        ]
        return ProjectConfig(files, packages)

    def find_files(self, root_dir: str) -> Iterator[str]:
        for pattern in self.files:
            yield from iglob(pattern, root_dir=root_dir, recursive=True)


def setup_cli() -> ArgumentParser:
    cli = ArgumentParser(
        description = "Upload micropython applications to a Raspberry Pi Pico over USB serial.",
    )

    cli.add_argument(
        '-d', '--device',
        default = '/dev/ttyACM0',
        help = "Serial device to communicate with RP2040 (default: /dev/ttyACM0)",
        metavar = "DEVICE",
    )
    cli.add_argument(
        '-c', '--config',
        default = 'deploy.cfg',
        help = (
            "Path to the project config file. If the config file does not exist, "
            "a new default configuration will be created (default: deploy.cfg)"
        ),
        metavar = "FILE",
        dest = 'cfg_path',
    )
    cli.add_argument(
        '-v', '--verbose',
        action = 'count',
        help = "Increase verbosity, can be specified more than once.",
        dest = 'verbosity',
    )
    cli.add_argument(
        '--fetch',
        action = 'store_true',
        help = (
            "Force all packages to be fetched and re-downloaded using upip. "
            "This will delete all cached packages. This is done automatically if "
            "any packages are added or removed from the deployment config. "
            "However, if only the required version of packages were changed, "
            "you will have to use this option to manually fetch the new versions."
        ),
        dest = 'force_fetch',
    )
    cli.add_argument(
        '--root',
        default = None,
        help = (
            "Specify the root directory when searching for files. "
            "Defaults to the folder containing the deployment configuration file."
        ),
        metavar = "FOLDER",
        dest = 'search_dir',
    )
    cli.add_argument(
        '--pkg-cache',
        default = '.pkgcache',
        help = (
            "Specify the folder where upip packages will be cached. "
            "This is ignored if --no-cache is set. (default: .pkgcache)"
        ),
        metavar = "FOLDER",
        dest = 'work_dir',
    )

    return cli


def main(args: Any) -> None:
    config = ConfigParser()
    config.read_dict(DEFAULT_CONFIG)

    # load config or create file if it does not exist
    cfg_path = args.cfg_path
    search_dir = args.search_dir
    if os.path.exists(cfg_path):
        if not os.path.isfile(cfg_path):
            raise RuntimeError(f"Can't read config, '{cfg_path}' is not a normal file!")
        _LOG.debug(f"Reading config from '{cfg_path}'")
        with open(cfg_path, 'rt') as f:
            config.read_file(f)
    else:
        _LOG.warning(f"Config file not found. Writing default config to '{cfg_path}' and exiting.")
        with open(cfg_path, 'wt') as f:
            config.write(f)
        return

    if search_dir is None:
        search_dir = os.path.dirname(cfg_path)

    project = ProjectConfig.load(config)
    for file_path in project.find_files(search_dir):
        print(file_path)


if __name__ == '__main__':
    import sys
    cli = setup_cli()
    args = cli.parse_args()

    ## setup logging
    log_levels = {
        1: logging.INFO,
        2: logging.DEBUG,
    }
    log_level = log_levels.get(args.verbosity, logging.WARNING)
    log_format = '%(levelname)s: %(message)s' #if args.verbosity else '%(message)s'
    logging.basicConfig(stream=sys.stdout, format=log_format, level=log_level)

    try:
        main(args)
    except Exception as err:
        _LOG.error(err)
        sys.exit(1)
