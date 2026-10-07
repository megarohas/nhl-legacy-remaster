# nhl13 - ReXGlue Recompiled Project
#
# SDK boilerplate lives in generated/rexglue.cmake.

cmake_minimum_required(VERSION 3.25)
project(nhl13 LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 23)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

include(generated/rexglue.cmake)

# Sources
set(NHL13_SOURCES
    src/main.cpp
    src/nhl13_imports.cpp
    src/nhl13_crash.cpp
)

if(WIN32)
    add_executable(nhl13 WIN32 ${NHL13_SOURCES})
else()
    add_executable(nhl13 ${NHL13_SOURCES})
endif()

rexglue_setup_target(nhl13 GPU_PLUGINS xenos)

if(WIN32)
    target_link_libraries(nhl13 PRIVATE dbghelp)  # стек в отчёте о падении
endif()
