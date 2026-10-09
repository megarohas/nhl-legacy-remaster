@echo off
rem Сборка ooz.dll (Oodle Kraken/Mermaid/Leviathan, powzix/ooz, GPL-3.0) для tools\fb\cas.py.
rem   1) git clone --depth 1 https://github.com/powzix/ooz game\work\nhl24\ooz-src
rem   2) tools\fb\build_ooz.cmd  ->  game\work\nhl24\bin\ooz.dll
rem Нужны VS 2022 Build Tools (заголовки Windows SDK) и LLVM (clang-cl).
setlocal
for %%i in ("%~dp0..\..") do set "REPO=%%~fi"
set "SRC=%REPO%\game\work\nhl24\ooz-src"
set "OUT=%REPO%\game\work\nhl24\bin"
if not exist "%SRC%\kraken.cpp" ( echo ooz sources not found: %SRC% & exit /b 1 )
if not exist "%OUT%" mkdir "%OUT%"
set "PATH=%ProgramFiles(x86)%\Microsoft Visual Studio\Installer;%PATH%"
call "%ProgramFiles(x86)%\Microsoft Visual Studio\2022\BuildTools\VC\Auxiliary\Build\vcvars64.bat" >nul || exit /b 1
"%ProgramFiles%\LLVM\bin\clang-cl.exe" /nologo /O2 /EHsc /MT /LD /w -msse4.1 /FIsys/types.h /FIsys/stat.h /I"%SRC%" ^
  "%SRC%\kraken.cpp" "%SRC%\lzna.cpp" "%SRC%\bitknit.cpp" "%~dp0ooz_export.cpp" ^
  /Fo"%OUT%\\" /Fe"%OUT%\ooz.dll" /link /NOLOGO
exit /b %errorlevel%
