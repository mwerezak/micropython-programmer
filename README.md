# Upload-MPy

This tool provides an easy way to upload micropython applications 
to a micropython-enabled device using a serial connection to communicate
with the micropython REPL. 

To use this tool, you must have CPython (>=3.8) installed and a working 
micropython port (e.g. the micropython Unix port) on the host computer 
(to "cross-install" packages using upip).

This tool has so far only been tested with the Raspberry Pi Pico, but should
work with any board where you can get the micropython REPL over UART.

### Usage

Just run `upload_mpy` as an executable package from the directory containing your
script files, providing the serial device. For example:

```commandline
python upload_mpy -d /dev/ttyACM0
```

The first time you run `upload_mpy`, it will generate a default config file and exit.
The config allows you to tell `upload_mpy` which files you want to copy (among other things).
By default this is `**.py`.

There are several command line options supported, use the `--help` command to view them.

### How it works

The tool itself is an executable Python module, `upload_mpy`. It uses `upip`
to download micropython packages and cross-install them to a temporary image folder 
(packages are cached so that they are only downloaded once).
It then copies all of your micropython application files (specified by configuration)
into the image folder. Next, the image folder is searched for `.py` files and all
such script files are replaced with compiled `.mpy` bytecode files. Finally, 
the contents of the image folder are uploaded to the micropython device using `pyserial`.

### Configuration
This tool allows you to download all required packages with upip, and 
upload them along with any other files you specify in a single command.

To do this, a deployment configuration file is used to tell `upload_mpy`
which packages to download and which files are part of your application.

By default, `upload_mpy` looks for a config file named `deploy.cfg` 
in the present working directory. If it is not found, a default configuration
file that you can edit will be created for you so you can quickly get started.

#### Config File Reference
##### `[dependencies]`
Key | Default | Description
----|---------|------------
`packages` | `''` | A whitespace/comma separated list of packages to download using upip. All of the usual version specifiers are supported (`~=`, `>=`, etc).  

##### `[deploy]`
Key | Default                      | Description
----|------------------------------|------------
`files` | `**.py` | A whitespace/comma separated list of glob patterns of files to include.
`exclude-files` | `` | A whitespace/comma separated list of glob patterns of files to exclude.
`mpy-cc` | `mpy-cross -O3 {scriptpath}` | Command to invoke cross compiler. Make sure it's in your PATH.
`compile` | `**.py` | A list of glob patterns for files to invoke the cross compiler on. This is only applied to included files.
`exclude-compile` | `boot.py,main.py` | list of glob patterns for files to exclude from cross compilation.

### Requirements

* Python (>=3.8)
  - `pyserial` 3.5
* micropython port for the host machine with upip installed
  - Source code distribution available at: https://micropython.org/download, 
  - See the README.md for instructions on how to compile.
  - Make sure after compilation that both `micropython` and `mpy-cross` are in your PATH.