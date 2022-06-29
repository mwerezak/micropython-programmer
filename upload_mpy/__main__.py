from __future__ import annotations

import os
import shutil
import logging
from argparse import ArgumentParser
from tempfile import TemporaryDirectory
from typing import TYPE_CHECKING

from serial import Serial

from config import ProjectConfig, load_config
from remote import RemoteREPL
import upload

if TYPE_CHECKING:
    from typing import Any


TMP_IMAGE = ':tmp:'

DEFAULT_DEVICE = '/dev/ttyACM0'
DEFAULT_CFGFILE = 'deploy.cfg'
DEFAULT_PKGCACHE = '.pkgcache'
DEFAULT_IMAGE = TMP_IMAGE
DEFAULT_TIMEOUT = 5.0
DEFAULT_RESET = 'soft'

_log = logging.getLogger()

def setup_cli() -> ArgumentParser:
    cli = ArgumentParser(
        description = "Upload code to a micropython-enabled device over a serial connection.",
    )

    cli.add_argument(
        '-d', '--device',
        default = DEFAULT_DEVICE,
        help = f"Serial device to communicate with the micropython REPL. (default={DEFAULT_DEVICE})",
        metavar = "DEVICE",
        dest = 'device',
    )
    cli.add_argument(
        '-c', '--config',
        default = DEFAULT_CFGFILE,
        help = (
            "Path to the project config file. If the config file does not exist, "
            f"a new default configuration will be created. (default={DEFAULT_CFGFILE})"
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
        '--reset',
        choices = ('none', 'soft', 'hard'),
        default = DEFAULT_RESET,
        help = f"Specifies how to reset the device after uploading. (default={DEFAULT_RESET})",
        metavar = 'VALUE',
        dest = 'reset',
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
    cli.add_argument(
        '--timeout',
        type = float,
        default = DEFAULT_TIMEOUT,
        help = f"Set the timeout for serial communication. (default={DEFAULT_TIMEOUT:.1f})",
        metavar = "SECONDS",
        dest = 'timeout',
    )

    return cli

def cross_compile_script(config: ProjectConfig, file_name: str, script_path: str, *, delete: bool = False) -> bool:
    result = config.invoke_cc(file_name, script_path, text=True)
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
    config = ProjectConfig.load(load_config(cfg_path))

    temp_dir = None
    if args.image_dir == TMP_IMAGE:
        temp_dir = TemporaryDirectory()
        image_dir = temp_dir.name
    else:
        image_dir = args.image_dir
        if not os.path.exists(image_dir):
            os.makedirs(image_dir)

    try:
        ## Copy project files
        _log.info(f"Copying project files to image...")
        file_count = 0
        for file_path in config.find_files(root_dir):
            if os.path.isfile(file_path):
                src_path = os.path.join(root_dir, file_path)
                dst_path = os.path.join(image_dir, file_path)
                _log.info(f"Copy file: {src_path}")
                shutil.copyfile(src_path, dst_path)
                file_count += 1
        _log.info(f"Copied {file_count} file(s) to image directory.")

        ## Cross compile scripts
        _log.info(f"Compiling script files...")
        compile_count = 0
        for file_path in config.find_scripts(image_dir):
            if os.path.isfile(file_path):
                src_path = os.path.join(image_dir, file_path)
                _log.info(f"Compile: {file_path}")
                if cross_compile_script(config, file_path, src_path, delete=not args.keep_src):
                    compile_count += 1
        _log.info(f"Compiled {compile_count} script file(s).")

        ## Upload image
        with Serial(args.device, timeout=args.timeout) as serial:
            remote = RemoteREPL(serial)
            if args.clean_target:
                _log.info(f"Cleaning target filesystem...")
                upload.clean_fs(remote, check=True)

            _log.info(f"Writing files to device...")
            upload_count = 0
            for dirpath, dirnames, filenames in os.walk(image_dir):
                for filename in filenames:
                    src_path = os.path.join(dirpath, filename)
                    tgt_path = os.path.relpath(src_path, image_dir)
                    with open(src_path, 'rb') as file:
                        _log.info(f"Write: {tgt_path}")
                        upload.write_file(remote, tgt_path, file, check=True)
                        upload_count += 1
            _log.info(f"Wrote {upload_count} file(s) to device filesystem.")

            remote.exec("import os; if hasattr(os, 'sync'): os.sync()")
            if args.reset == 'soft':
                _log.info("Soft reset device.")
                remote.soft_reset()
            elif args.reset == 'hard':
                _log.info("Hard reset device.")
                remote.hard_reset()
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
    log_format = '%(levelname)s: %(message)s'
    logging.basicConfig(stream=sys.stdout, format=log_format, level=log_level)

    try:
        main(args)
    except SystemExit as err:
        raise
    except Exception as err:
        if log_level <= logging.DEBUG:
            _log.error(err, exc_info=err)
        else:
            _log.error(err)
        sys.exit(1)
