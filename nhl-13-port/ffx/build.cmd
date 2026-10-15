@echo off
rem port-ffx: build against the custom SDK (ref\rexglue-sdk-custom), not the nightly.
rem   build.cmd [preset] [configure]   preset default win-amd64-release; see scripts\build_port.cmd
call "%~dp0scripts\build_port.cmd" %*
