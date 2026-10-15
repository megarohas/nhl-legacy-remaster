@echo off
rem Build port-ffx against the custom SDK in ref\rexglue-sdk-custom\install\win-amd64
rem (docs/sdk-build.md). Same toolchain and presets as nhl-13-port\build.cmd.
rem   build_port.cmd [preset] [configure]     preset default: win-amd64-release
rem   env: JOBS (8), KEEP_GOING=1 (ninja -k 0), NHLFFX_NORMALPRIO=1 keeps normal priority.
rem The first build in a fresh tree runs codegen once: it only checks the fingerprint
rem (generated\default\codegen.stamp) and writes nothing if the inputs are unchanged.
setlocal
call "%~dp0env.cmd" || exit /b 1
if "%NHLFFX_NORMALPRIO%"=="1" goto :main
if "%NHLFFX_LOWPRIO%"=="1" goto :main
set "NHLFFX_LOWPRIO=1"
start "" /belownormal /wait /b "%ComSpec%" /d /c call "%~f0" %*
exit /b %errorlevel%

:main
set "PRESET=%~1"
if "%PRESET%"=="" set "PRESET=win-amd64-release"
if not exist "%SDK_PREFIX%\lib\cmake\rexglue\rexglueConfig.cmake" (
  echo custom SDK not installed at %SDK_PREFIX% - run scripts\sdk_build.cmd first
  exit /b 1
)
cd /d "%PORTFFX%"
rem CMAKE_FIND_USE_PACKAGE_REGISTRY=OFF: only the prefix given here, never a registered SDK.
cmake --preset %PRESET% "-DCMAKE_PREFIX_PATH=%SDK_PREFIX%" -DCMAKE_FIND_USE_PACKAGE_REGISTRY=OFF || exit /b 1
if /i "%~2"=="configure" exit /b 0
set "EXTRA="
if "%KEEP_GOING%"=="1" set "EXTRA=-- -k 0"
cmake --build out/build/%PRESET% -j %JOBS% %EXTRA% || exit /b 1
if not exist "out\build\%PRESET%\nhl13.toml" copy /y "nhl13.ffx.toml" "out\build\%PRESET%\nhl13.toml" >nul
exit /b 0
