@echo off
rem Build the NHL Legacy launcher (docs/launcher.md): MSVC from VS 2022 BuildTools, static CRT,
rem no third-party libraries. Output: nhl-legacy-port\out\launcher\nhllegacy_launcher.exe (not in git).
setlocal
set "PATH=%ProgramFiles(x86)%\Microsoft Visual Studio\Installer;%PATH%"
call "C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools\VC\Auxiliary\Build\vcvars64.bat" >nul || exit /b 1
set "OUT=%~dp0..\out\launcher"
if not exist "%OUT%" mkdir "%OUT%"
cl /nologo /utf-8 /std:c++17 /O1 /MT /EHsc /W4 /permissive- /DNDEBUG "%~dp0nhllegacy_launcher.cpp" /Fo"%OUT%\\" /Fe"%OUT%\nhllegacy_launcher.exe" /link /SUBSYSTEM:WINDOWS /MANIFEST:EMBED || exit /b 1
exit /b 0
