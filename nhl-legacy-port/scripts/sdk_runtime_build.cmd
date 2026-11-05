@echo off
rem Rebuild only the runtime of the custom SDK (rexruntime.dll) after editing scripts\sdk-patches\0007+
rem (docs/legacy-port.md, "Saves folder"). The SDK install (install\win-amd64) is not changed: the DLL is
rem ref\rexglue-sdk-custom\src\out\win-amd64\Release\rexruntime.dll; copy it next to the exe by hand. The port links against install\win-amd64\lib\rexruntime.lib: patches that add no exports
rem need no relink. Full rebuild with install: scripts\sdk_build.cmd build; from scratch: scripts\sdk_build.cmd.
rem   env: JOBS (default 8), NHLLEG_NORMALPRIO=1 keeps normal priority.
setlocal
if "%NHLLEG_NORMALPRIO%"=="1" goto :main
if "%NHLLEG_LOWPRIO%"=="1" goto :main
set "NHLLEG_LOWPRIO=1"
start "" /belownormal /wait /b "%ComSpec%" /d /c call "%~f0" %*
exit /b %errorlevel%

:main
if "%JOBS%"=="" set "JOBS=8"
call "%~dp0sdk_env.cmd" || exit /b 1
cmake --build "%SDK_BUILD%" --config Release --target rexruntime -j %JOBS%
set "RC=%ERRORLEVEL%"
echo EXIT %RC%
exit /b %RC%
