@echo off
rem Check that the custom SDK's rexglue.exe generates byte-identical code to what is in
rem port-ffx\generated\default (made by the nightly's rexglue.exe). Full codegen of a
rem scratch copy in %SDKC%\cgcheck at idle priority, ~9 minutes. Exit 0 = identical.
setlocal
call "%~dp0env.cmd" || exit /b 1
if "%NHLFFX_LOWPRIO%"=="1" goto :main
set "NHLFFX_LOWPRIO=1"
start "" /low /wait /b "%ComSpec%" /d /c call "%~f0" %*
exit /b %errorlevel%

:main
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0codegen_check.ps1" ^
  -Rexglue "%SDK_PREFIX%\bin\rexglue.exe" -PortDir "%PORTFFX%" -WorkDir "%SDKC%\cgcheck"
exit /b %errorlevel%
