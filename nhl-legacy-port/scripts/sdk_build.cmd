@echo off
rem Fetch, configure, build and install the custom ReXGlue SDK (docs/sdk-build.md):
rem bd833a2 (= nightly 0.10.0.24) + D3D12 and Vulkan backends + FSR 1 / CAS presenter
rem effects (REXGLUE_ENABLE_FIDELITYFX=ON, backend "none" = no ffx-api runtime DLL).
rem   sdk_build.cmd [fetch|configure|build|all]   default: all (fetch + configure + build + install)
rem   env: JOBS (8), SDK_CONFIGS ("Release"; "Release RelWithDebInfo" also serves the port's
rem        relwithdebinfo preset), NHLLEG_NORMALPRIO=1 keeps normal priority (default: below normal).
setlocal
call "%~dp0sdk_env.cmd" || exit /b 1
if "%NHLLEG_NORMALPRIO%"=="1" goto :main
if "%NHLLEG_LOWPRIO%"=="1" goto :main
set "NHLLEG_LOWPRIO=1"
start "" /belownormal /wait /b "%ComSpec%" /d /c call "%~f0" %*
exit /b %errorlevel%

:main
set "STEP=%~1"
if "%STEP%"=="" set "STEP=all"
if not defined SDK_CONFIGS set "SDK_CONFIGS=Release"

if /i "%STEP%"=="fetch" goto :fetch
if /i "%STEP%"=="all" goto :fetch
if /i "%STEP%"=="configure" goto :configure
if /i "%STEP%"=="build" goto :build
echo unknown step "%STEP%" (fetch, configure, build, all)
exit /b 2

:fetch
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0sdk_fetch.ps1" -SdkSrc "%SDK_SRC%" -Pin %SDK_PIN% || exit /b 1
if /i "%STEP%"=="fetch" exit /b 0

:configure
rem Same cache variables as the SDK's win-amd64 preset (what CI builds the nightly with),
rem plus Vulkan, FidelityFX (spatial only) and no CMake package registry entry.
cmake -S "%SDK_SRC%" -B "%SDK_BUILD%" -G "Ninja Multi-Config" ^
  -DCMAKE_C_COMPILER=clang -DCMAKE_CXX_COMPILER=clang++ ^
  "-DCMAKE_C_FLAGS=-march=x86-64-v2" "-DCMAKE_CXX_FLAGS=-march=x86-64-v2" ^
  -DCMAKE_CXX_STANDARD=23 ^
  "-DCMAKE_CONFIGURATION_TYPES=Debug;Release;RelWithDebInfo" ^
  -DCMAKE_CROSS_CONFIGS=all -DCMAKE_DEFAULT_CONFIGS=all -DCMAKE_DEFAULT_BUILD_TYPE=Release ^
  "-DCMAKE_INSTALL_PREFIX=%SDK_PREFIX%" ^
  -DREXGLUE_USE_D3D12=ON -DREXGLUE_USE_VULKAN=ON ^
  -DREXGLUE_ENABLE_FIDELITYFX=ON -DREXGLUE_FIDELITYFX_BACKEND=none ^
  -DREXGLUE_REGISTER_PACKAGE=OFF || exit /b 1
if /i "%STEP%"=="configure" exit /b 0

:build
for %%c in (%SDK_CONFIGS%) do (
  echo [sdk] build %%c, %JOBS% jobs
  cmake --build "%SDK_BUILD%" --config %%c -j %JOBS% || exit /b 1
  echo [sdk] install %%c -^> %SDK_PREFIX%
  cmake --install "%SDK_BUILD%" --config %%c || exit /b 1
)
exit /b 0
