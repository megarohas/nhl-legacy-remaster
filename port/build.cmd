@echo off
rem Port build: MSVC environment (Windows SDK, libs) + Clang from LLVM, CMake, Ninja.
rem   build.cmd [preset] [configure]     preset defaults to win-amd64-relwithdebinfo
rem   env: JOBS (default 10), KEEP_GOING=1 to collect all compile errors (ninja -k 0)
setlocal
set "PATH=%ProgramFiles(x86)%\Microsoft Visual Studio\Installer;%PATH%"
call "C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools\VC\Auxiliary\Build\vcvars64.bat" >nul || exit /b 1
set "PATH=C:\Program Files\LLVM\bin;C:\Program Files\CMake\bin;%LOCALAPPDATA%\Microsoft\WinGet\Packages\Ninja-build.Ninja_Microsoft.Winget.Source_8wekyb3d8bbwe;%PATH%"
set "PRESET=%~1"
if "%PRESET%"=="" set "PRESET=win-amd64-relwithdebinfo"
if "%JOBS%"=="" set "JOBS=10"
cd /d "%~dp0"
cmake --preset %PRESET% -DCMAKE_PREFIX_PATH="%~dp0..\ref\rexglue-sdk-0.10.0\win-amd64" || exit /b 1
if /i "%~2"=="configure" exit /b 0
set "EXTRA="
if "%KEEP_GOING%"=="1" set "EXTRA=-- -k 0"
cmake --build out/build/%PRESET% -j %JOBS% %EXTRA% || exit /b 1
if not exist "out\build\%PRESET%\nhl13.toml" copy /y "nhl13.example.toml" "out\build\%PRESET%\nhl13.toml" >nul
