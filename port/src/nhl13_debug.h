// Общие отладочные помощники порта (nhl13_crash.cpp): стеки и имена функций.
#pragma once

#if defined(_WIN32)

#include <windows.h>

#include <cstdint>
#include <cstdio>
#include <mutex>

std::mutex& Nhl13DbghelpMutex();                              // dbghelp не потокобезопасен
void Nhl13EnsureSymbols();                                    // SymInitialize один раз
void Nhl13WriteFrame(FILE* f, int i, DWORD64 addr);           // «#NN модуль!функция+смещение (файл:строка)»
int Nhl13CaptureStack(CONTEXT ctx, DWORD64* out, int max);    // раскрутка без выделения памяти

#endif
