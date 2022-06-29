# Upload-MPy

This tool provides an easy way to upload micropython applications 
to a micropython-enabled device using a serial connection to communicate
with the micropython REPL. 

To use this tool, you must have CPython (>=3.8) installed and a working 
micropython port (e.g. the micropython Unix port) on the host computer 
(to "cross-install" packages using upip).

This tool has so far only been tested with the Raspberry Pi Pico, but should
work with any board where you can get the micropython REPL over UART.

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

### Requirements

* Python (>=3.8)
  - `pyserial` 3.5
* micropython port for the host machine with upip installed
  - Source code distribution available at: https://micropython.org/download, 
  - See the README.md for instructions on how to compile.
  - Make sure after compilation that both `micropython` and `mpy-cross` are in your PATH.