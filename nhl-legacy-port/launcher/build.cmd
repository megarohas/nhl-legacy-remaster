@echo off
rem Build the NHL Legacy launcher (docs/launcher.md): MSVC from VS 2022 BuildTools, static CRT,
rem no third-party libraries. Output: nhl-legacy-port\out\launcher\nhllegacy_launcher.exe (not in git).
rem Project version: ..\..\VERSION -> NHL_VERSION (window title and header).
rem Icon: tools\make_icon.py -> icon\nhllegacy.ico (not in git, drawn from the game's fonts) -> resource id 1.
setlocal
set "PATH=%ProgramFiles(x86)%\Microsoft Visual Studio\Installer;%PATH%"
call "C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools\VC\Auxiliary\Build\vcvars64.bat" >nul || exit /b 1
set "OUT=%~dp0..\out\launcher"
if not exist "%OUT%" mkdir "%OUT%"
set "VER=dev"
if exist "%~dp0..\..\VERSION" set /p VER=<"%~dp0..\..\VERSION"
> "%OUT%\nhl_version.h" echo #define NHL_VERSION L"%VER%"
set "RES="
set "ICO=%~dp0icon\nhllegacy.ico"
if not exist "%ICO%" goto :noicon
rem rc treats backslashes in strings as escapes - use forward slashes
set "ICO=%ICO:\=/%"
> "%OUT%\nhllegacy_launcher.rc" echo 1 ICON "%ICO%"
rc /nologo /fo "%OUT%\nhllegacy_launcher.res" "%OUT%\nhllegacy_launcher.rc"
if errorlevel 1 exit /b 1
set "RES=%OUT%\nhllegacy_launcher.res"
:noicon
cl /nologo /utf-8 /std:c++17 /O1 /MT /EHsc /W4 /permissive- /DNDEBUG /I"%OUT%" "%~dp0nhllegacy_launcher.cpp" %RES% /Fo"%OUT%\\" /Fe"%OUT%\nhllegacy_launcher.exe" /link /SUBSYSTEM:WINDOWS /MANIFEST:EMBED || exit /b 1
exit /b 0
