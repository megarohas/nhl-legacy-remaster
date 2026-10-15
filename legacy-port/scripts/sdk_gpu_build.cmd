@echo off
rem Пересборка только GPU-плагина своего SDK (rexgpu-xenos.dll) после правки патчей scripts\sdk-patches\0005+
rem (docs/legacy-port.md, «Порча текстур в первом матче сессии»). Установка SDK (install\win-amd64) не меняется:
rem DLL — в ref\rexglue-sdk-custom\src\out\win-amd64\Release\rexgpu-xenos.dll, копировать к тестовому exe вручную.
rem Полная пересборка с установкой — scripts\sdk_build.cmd build, с нуля — scripts\sdk_build.cmd (docs/sdk-build.md).
rem   env: JOBS (по умолчанию 8), NHLLEG_NORMALPRIO=1 — без понижения приоритета.
setlocal
if "%NHLLEG_NORMALPRIO%"=="1" goto :main
if "%NHLLEG_LOWPRIO%"=="1" goto :main
set "NHLLEG_LOWPRIO=1"
start "" /belownormal /wait /b "%ComSpec%" /d /c call "%~f0" %*
exit /b %errorlevel%

:main
if "%JOBS%"=="" set "JOBS=8"
call "%~dp0sdk_env.cmd" || exit /b 1
cmake --build "%SDK_BUILD%" --config Release --target rexgpu-xenos -j %JOBS%
set "RC=%ERRORLEVEL%"
echo EXIT %RC%
exit /b %RC%
