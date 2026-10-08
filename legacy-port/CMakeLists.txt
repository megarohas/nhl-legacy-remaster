# nhllegacy — свой порт NHL Legacy (Xbox 360, TitleID 454109EC) на ReXGlue SDK 0.10.0.24.
#
# Обвязка — по образцу порта NHL 13 (port/), см. docs/legacy-port.md. Шаблон SDK —
# generated/rexglue.cmake; сгенерированный код generated/default/ (производное от кода игры)
# и сборка out/ — только локально.

cmake_minimum_required(VERSION 3.25)
project(nhllegacy LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 23)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

include(generated/rexglue.cmake)

set(NHLLEGACY_SOURCES
    src/main.cpp
    src/nhllegacy_imports.cpp
    src/nhllegacy_crash.cpp
    src/nhllegacy_watch.cpp
    src/nhllegacy_input_lock.cpp
    src/nhllegacy_fencewait.cpp
    src/nhllegacy_composite.cpp
)

if(WIN32)
    add_executable(nhllegacy WIN32 ${NHLLEGACY_SOURCES})
else()
    add_executable(nhllegacy ${NHLLEGACY_SOURCES})
endif()

rexglue_setup_target(nhllegacy GPU_PLUGINS xenos)

if(WIN32)
    target_link_libraries(nhllegacy PRIVATE dbghelp)  # стек в отчёте о падении
    # nhllegacy_snap.exe — слепок памяти игры снаружи (src/nhllegacy_snap.cpp), рядом с nhllegacy.exe
    add_executable(nhllegacy_snap src/nhllegacy_snap.cpp)
    target_link_libraries(nhllegacy_snap PRIVATE dbghelp)
    set_target_properties(nhllegacy_snap PROPERTIES RUNTIME_OUTPUT_DIRECTORY "$<TARGET_FILE_DIR:nhllegacy>")
    add_dependencies(nhllegacy nhllegacy_snap)
endif()
