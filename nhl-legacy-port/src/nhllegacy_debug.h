// Общие отладочные помощники порта (nhllegacy_crash.cpp): стеки и имена функций.
#pragma once

#if defined(_WIN32)

#include <windows.h>

#include <cstdint>
#include <cstdio>
#include <mutex>

std::mutex& NhlLegacyDbghelpMutex();                              // dbghelp не потокобезопасен
void NhlLegacyEnsureSymbols();                                    // SymInitialize один раз
void NhlLegacyWriteFrame(FILE* f, int i, DWORD64 addr);           // «#NN модуль!функция+смещение (файл:строка)»
int NhlLegacyCaptureStack(CONTEXT ctx, DWORD64* out, int max);    // раскрутка без выделения памяти
void NhlLegacyWriteSnapshot(const char* reason);                  // слепок процесса в папку dumps (игра замирает)
bool NhlLegacyWatchPage(uint32_t guest, bool (*filter)(uint32_t)); // записи в страницу (фильтр) — в nhllegacy_watch.log

#endif
