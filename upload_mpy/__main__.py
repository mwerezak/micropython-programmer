from __future__ import annotations

import os
import shutil
import logging
import subprocess
from argparse import ArgumentParser
from configparser import ConfigParser
from tempfile import TemporaryDirectory
from typing import TYPE_CHECKING

from serial import Serial

from config import DEFAULT_CONFIG, ProjectConfig
from remote import RemoteREPL
from upload import clean_fs, write_file

if TYPE_CHECKING:
    from typing import Any, Optional, Iterable


DEFAULT_DEVICE = '/dev/ttyACM0'
DEFAULT_CFGFILE = 'deploy.cfg'
DEFAULT_PKGCACHE = '.pkgcache'
TMP_IMAGE = ':tmp:'
DEFAULT_IMAGE = TMP_IMAGE


_log = logging.getLogger()

def setup_cli() -> ArgumentParser:
    cli = ArgumentParser(
        description = "Upload micropython applications to a Raspberry Pi Pico over USB serial.",
    )

    cli.add_argument(
        '-d', '--device',
        default = DEFAULT_DEVICE,
        help = f"Serial device to communicate with RP2040 (default={DEFAULT_DEVICE})",
        metavar = "DEVICE",
        dest = 'device',
    )
    cli.add_argument(
        '-c', '--config',
        default = DEFAULT_CFGFILE,
        help = (
            "Path to the project config file. If the config file does not exist, "
            f"a new default configuration will be created (default={DEFAULT_CFGFILE})"
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
        '--root-dir',
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
            f"This is ignored if --no-cache is set. (default={DEFAULT_PKGCACHE})"
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
        '--no-clean',
        action = 'store_false',
        help = (
            "Do not clean the target filesystem before uploading. Existing files may be "
            "overwritten, but others will be left unchanged."
        ),
        dest = 'clean_target',
    )
    cli.add_argument(
        '--image-dir',
        default = DEFAULT_IMAGE,
        help = (
            "The directory where the image will be built before uploading to the target device."
            f"If set to '{TMP_IMAGE}' then a temporary directory will be used and removed after "
            f"upload is complete. Otherwise the image directory will be left as-is. (default={DEFAULT_IMAGE})"
        ),
        metavar = "FOLDER",
        dest = 'image_dir',
    )
    cli.add_argument(
        '--keep-src',
        action = 'store_true',
        help = (
            "Script files compiled with mpy-cross will be kept in the image and uploaded along "
            "with the compiled .mpy files."
        ),
        dest = 'keep_src',
    )

    return cli

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
            config.write(f)
        raise SystemExit(1)

    return config

_MPY_CROSS = 'mpy-cross'
def cross_compile_script(script_path: str, *, compile_args: Iterable[str] = (), delete: bool = False) -> bool:
    cmd = [_MPY_CROSS, *compile_args, script_path]
    result = subprocess.run(cmd, text=True)

    if result.returncode != 0:
        _log.warning(f"Failed to compile script '{script_path}' (code {result.returncode})")
        _log.debug(result.stderr.encode(errors='replace'))
        return False

    if delete:
        os.remove(script_path)
    return True


def main(args: Any) -> None:
    cfg_path = args.cfg_path
    root_dir = args.search_dir or os.path.dirname(args.cfg_path)

    temp_dir: Optional[TemporaryDirectory] = None
    if args.image_dir == TMP_IMAGE:
        temp_dir = TemporaryDirectory()
        image_dir = temp_dir.name
    else:
        image_dir = args.image_dir
        if not os.path.exists(image_dir):
            os.makedirs(image_dir)

    try:
        config = ProjectConfig.load(load_config(cfg_path))

        ## Copy project files
        _log.info(f"Copying project files to image...")
        file_count = 0
        for file_path in config.find_files(root_dir):
            if os.path.isfile(file_path):
                src_path = os.path.join(root_dir, file_path)
                dst_path = os.path.join(image_dir, file_path)
                _log.debug(f"Copy file: {src_path}")
                shutil.copyfile(src_path, dst_path)
                file_count += 1
        _log.info(f"Copied {file_count} files to image directory.")

        ## Cross compile scripts
        _log.info(f"Compiling script files...")
        compile_count = 0
        for file_path in config.find_scripts(image_dir):
            if os.path.isfile(file_path):
                src_path = os.path.join(image_dir, file_path)
                _log.debug(f"Compile: {src_path}")
                if cross_compile_script(src_path, compile_args=config.compile_args, delete=not args.keep_src):
                    compile_count += 1
        _log.info(f"Compiled {compile_count} script files.")

        ## Upload image
        serial = Serial(args.device, timeout=1)
        remote = RemoteREPL(serial)
        if args.clean_target:
            _log.info(f"Cleaning target filesystem...")
            clean_fs(remote)
        for dirpath, dirnames, filenames in os.walk(image_dir):
            for filename in filenames:
                src_path = os.path.join(dirpath, filename)
                tgt_path = os.path.relpath(src_path, image_dir)
                with open(src_path, 'rb') as file:
                    _log.debug(f"Upload: {tgt_path}")
                    write_file(remote, tgt_path, file)

        _log.info("Soft reset device.")
        remote.exec("import os; if hasattr(os, 'sync'): os.sync()")
        remote.exec("import machine; machine.soft_reset()")

    finally:
        if temp_dir is not None:
            temp_dir.cleanup()


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
        if args.verbosity:
            _log.error(err, exc_info=err)
        else:
            _log.error(err)
        sys.exit(1)
