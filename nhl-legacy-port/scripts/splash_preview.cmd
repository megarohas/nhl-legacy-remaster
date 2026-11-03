@echo off
rem Splash preview without the game (docs/legacy-port.md, "Splash screen"): builds src\nhllegacy_splash.cpp with
rem NHLLEGACY_SPLASH_PREVIEW (no SDK) and writes frames as BMP.
rem   scripts\splash_preview.cmd OUT_DIR [WIDTH HEIGHT [t1 t2 ...]]
rem Defaults: 1280x720, t = 0.0 0.35 0.7 1.05. Convert to PNG/GIF with any image tool (PIL in game\work\nhl24\venv).
setlocal
set "HERE=%~dp0"
set "PATH=%ProgramFiles(x86)%\Microsoft Visual Studio\Installer;%PATH%"
if "%~1"=="" (
  echo usage: splash_preview.cmd OUT_DIR [WIDTH HEIGHT [t1 t2 ...]]
  exit /b 2
)
set "OUT=%~f1"
set "W=%~2"
set "H=%~3"
if "%W%"=="" set "W=1280"
if "%H%"=="" set "H=720"
shift & shift & shift
set "TIMES="
:times
if "%~1"=="" goto :built_times
set "TIMES=%TIMES% %~1"
shift
goto :times
:built_times
if "%TIMES%"=="" set "TIMES=0.0 0.35 0.7 1.05"
if not exist "%OUT%" mkdir "%OUT%"
call "C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools\VC\Auxiliary\Build\vcvars64.bat" >nul || exit /b 1
cl /nologo /utf-8 /std:c++17 /O2 /EHsc /W4 /DNHLLEGACY_SPLASH_PREVIEW /DNOMINMAX /DWIN32_LEAN_AND_MEAN /DUNICODE /D_UNICODE "%HERE%..\src\nhllegacy_splash.cpp" /Fo"%OUT%\\" /Fe"%OUT%\splash_preview.exe" /link user32.lib gdi32.lib >"%OUT%\build.log" || (type "%OUT%\build.log" & exit /b 1)
"%OUT%\splash_preview.exe" "%OUT%" %W% %H% %TIMES%
