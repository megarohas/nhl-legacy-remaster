@echo off
rem Shared environment for the custom SDK scripts of the NHL Legacy port (docs/sdk-build.md). Use via "call".
rem Any variable may be preset by the caller; it is not overwritten then.
rem   PROJ        the port project (nhl-legacy-port)
rem   SDKC        ref\rexglue-sdk-custom: SDK sources, build tree and install
rem   SDK_SRC     rexglue-sdk clone at SDK_PIN + scripts\sdk-patches\*.patch
rem   SDK_BUILD   SDK build tree (Ninja Multi-Config)
rem   SDK_PREFIX  SDK install prefix (same layout as the nightly zip: bin, lib, include, share)
rem   JOBS        parallel jobs (default 8 of 12 threads)
for %%i in ("%~dp0..") do set "PROJ=%%~fi"
for %%i in ("%PROJ%\..") do set "REPO=%%~fi"
if not defined SDKC set "SDKC=%REPO%\ref\rexglue-sdk-custom"
if not defined SDK_SRC set "SDK_SRC=%SDKC%\src"
if not defined SDK_BUILD set "SDK_BUILD=%SDKC%\build\win-amd64"
if not defined SDK_PREFIX set "SDK_PREFIX=%SDKC%\install\win-amd64"
rem bd833a2 = nightly 0.10.0.24-dev.gbd833a2 (branch development), same as ref\rexglue-sdk-0.10.0.24
if not defined SDK_PIN set "SDK_PIN=bd833a2ab69d305f99ddf57418fc38ffec8af93d"
if not defined JOBS set "JOBS=8"

if defined NHLLEG_SDK_ENV_READY exit /b 0
set "PATH=%ProgramFiles(x86)%\Microsoft Visual Studio\Installer;%PATH%"
call "C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools\VC\Auxiliary\Build\vcvars64.bat" >nul || exit /b 1
set "PATH=C:\Program Files\LLVM\bin;C:\Program Files\CMake\bin;%LOCALAPPDATA%\Microsoft\WinGet\Packages\Ninja-build.Ninja_Microsoft.Winget.Source_8wekyb3d8bbwe;%PATH%"
set "NHLLEG_SDK_ENV_READY=1"
exit /b 0
