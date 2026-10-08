@echo off
rem Сборка порта NHL Legacy (docs/legacy-port.md): MSVC-окружение + Clang, CMake, Ninja.
rem   build.cmd [preset] [configure]
rem     preset win-amd64-release        (по умолчанию) свой SDK ref\rexglue-sdk-custom: D3D12 + Vulkan, FSR 1 / CAS
rem     preset win-amd64-relwithdebinfo ночной SDK ref\rexglue-sdk-0.10.0.24 (только D3D12), с символами — для отладки
rem   env: JOBS (по умолчанию 8), KEEP_GOING=1 (ninja -k 0), NHLLEG_NORMALPRIO=1 — без понижения приоритета.
rem Первая сборка в новом дереве один раз запускает кодоген: если входы не менялись
rem (generated\default\codegen.stamp), он ничего не пишет.
setlocal
if "%NHLLEG_NORMALPRIO%"=="1" goto :main
if "%NHLLEG_LOWPRIO%"=="1" goto :main
set "NHLLEG_LOWPRIO=1"
start "" /belownormal /wait /b "%ComSpec%" /d /c call "%~f0" %*
exit /b %errorlevel%

:main
set "PRESET=%~1"
if "%PRESET%"=="" set "PRESET=win-amd64-release"
for %%i in ("%~dp0..") do set "REPO=%%~fi"
if /i "%PRESET%"=="win-amd64-release" (
  set "SDK_PREFIX=%REPO%\ref\rexglue-sdk-custom\install\win-amd64"
) else (
  set "SDK_PREFIX=%REPO%\ref\rexglue-sdk-0.10.0.24\win-amd64"
)
if "%JOBS%"=="" set "JOBS=8"
if not exist "%SDK_PREFIX%\lib\cmake\rexglue\rexglueConfig.cmake" (
  echo SDK not found at %SDK_PREFIX%
  exit /b 1
)
set "PATH=%ProgramFiles(x86)%\Microsoft Visual Studio\Installer;%PATH%"
call "C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools\VC\Auxiliary\Build\vcvars64.bat" >nul || exit /b 1
set "PATH=C:\Program Files\LLVM\bin;C:\Program Files\CMake\bin;%LOCALAPPDATA%\Microsoft\WinGet\Packages\Ninja-build.Ninja_Microsoft.Winget.Source_8wekyb3d8bbwe;%PATH%"
cd /d "%~dp0"
rem CMAKE_FIND_USE_PACKAGE_REGISTRY=OFF: только этот SDK, никогда не зарегистрированный в реестре.
cmake --preset %PRESET% "-DCMAKE_PREFIX_PATH=%SDK_PREFIX%" -DCMAKE_FIND_USE_PACKAGE_REGISTRY=OFF || exit /b 1
if /i "%~2"=="configure" exit /b 0
set "EXTRA="
if "%KEEP_GOING%"=="1" set "EXTRA=-- -k 0"
cmake --build out/build/%PRESET% -j %JOBS% %EXTRA% || exit /b 1
if not exist "out\build\%PRESET%\nhllegacy.toml" copy /y "nhllegacy.example.toml" "out\build\%PRESET%\nhllegacy.toml" >nul
exit /b 0
