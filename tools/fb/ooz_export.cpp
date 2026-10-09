// Экспорт декомпрессора Oodle Kraken из ooz (https://github.com/powzix/ooz, GPL-3.0-or-later)
// в DLL для ctypes (tools/fb/cas.py). Исходники ooz в git не кладём: build_ooz.cmd берёт их из
// game\work\nhl24\ooz-src (git clone --depth 1 https://github.com/powzix/ooz). Только для себя, не распространять.
#include "stdafx.h"

int Kraken_Decompress(const byte *src, size_t src_len, byte *dst, size_t dst_len);

extern "C" __declspec(dllexport) int ooz_kraken_decompress(const byte *src, size_t src_len, byte *dst, size_t dst_len) {
  return Kraken_Decompress(src, src_len, dst, dst_len);
}
