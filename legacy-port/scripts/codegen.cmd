@echo off
rem Кодоген порта NHL Legacy отдельно от сборки, с пониженным приоритетом (~15-30 мин):
rem   scripts\codegen.cmd [--force]     лог — out\codegen.log
rem Сборка (build.cmd) запускает тот же кодоген сама; если входы не менялись
rem (generated\default\codegen.stamp), он ничего не пишет.
setlocal
if "%NHLLEG_LOWPRIO%"=="1" goto :main
set "NHLLEG_LOWPRIO=1"
start "" /belownormal /wait /b "%ComSpec%" /d /c call "%~f0" %*
exit /b %errorlevel%

:main
for %%i in ("%~dp0..") do set "PROJ=%%~fi"
for %%i in ("%PROJ%\..") do set "REPO=%%~fi"
set "REXGLUE=%REPO%\ref\rexglue-sdk-custom\install\win-amd64\bin\rexglue.exe"
if not exist "%REXGLUE%" set "REXGLUE=%REPO%\ref\rexglue-sdk-0.10.0.24\win-amd64\bin\rexglue.exe"
cd /d "%PROJ%"
if not exist out mkdir out
"%REXGLUE%" codegen nhllegacy_manifest.toml %* > out\codegen.log 2>&1
set "RC=%errorlevel%"
echo exit %RC% >> out\codegen.log
exit /b %RC%
