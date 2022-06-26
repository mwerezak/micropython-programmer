from __future__ import annotations

import os
import logging
from argparse import ArgumentParser
from configparser import ConfigParser
from typing import TYPE_CHECKING

from upload_mpy.config import DEFAULT_CONFIG, ProjectConfig

if TYPE_CHECKING:
    from typing import Any


DEFAULT_DEVICE = '/dev/ttyACM0'
DEFAULT_CONFIG = 'deploy.cfg'
DEFAULT_PKGCACHE = '.pkgcache'


_log = logging.getLogger()

def setup_cli() -> ArgumentParser:
    cli = ArgumentParser(
        description = "Upload micropython applications to a Raspberry Pi Pico over USB serial.",
    )

    cli.add_argument(
        '-d', '--device',
        default = DEFAULT_DEVICE,
        help = f"Serial device to communicate with RP2040 (default: {DEFAULT_DEVICE})",
        metavar = "DEVICE",
        dest = 'device',
    )
    cli.add_argument(
        '-c', '--config',
        default = DEFAULT_CONFIG,
        help = (
            "Path to the project config file. If the config file does not exist, "
            f"a new default configuration will be created (default: {DEFAULT_CONFIG})"
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
        default = DEFAULT_PKGCACHE,
        help = (
            "The folder where upip packages will be cached. "
            f"This is ignored if --no-cache is set. (default: {DEFAULT_PKGCACHE})"
        ),
        metavar = "FOLDER",
        dest = 'work_dir',
    )
    cli.add_argument(
        '--no-cache',
        action = 'store_false',
        help = (
            "Do not cache upip packages, or do not update the cache if one already exists. "
            "Packages that are not found in the cache will be downloaded using upip."
        ),
        dest = 'use_cache',
    )
    cli.add_argument(
        '--image-dir',
        default = ':temp:',
        help = (
            ""
        ),
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
        _log.debug(f"Reading config from '{cfg_path}'")
        with open(cfg_path, 'rt') as f:
            config.read_file(f)
    else:
        _log.warning(f"Config file not found. Writing default config to '{cfg_path}' and exiting.")
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
        _log.error(err)
        sys.exit(1)
