"""Врезки сдвига года для порта: находит в образе константы-года и пишет [[midasm_hook]].

    python year_hooks.py IMAGE > nhl-13-port/nhl13_year_hooks.toml      # TOML для ReXGlue
    python year_hooks.py IMAGE --report                          # таблица решений по всем местам
    python year_hooks.py --game legacy LEGACY_IMAGE > nhl-legacy-port/nhllegacy_year_hooks.toml
                                                                 # NHL Legacy: база 2015, свои KEEP/EXTRA

Игра считает «сейчас» от зашитого 2012 (сезон 2012/13): дата «Играть сейчас»
(MakeDate(2012, 8, 14)), год новой франшизы, «номер сезона = год − 2012», «год ≥ 2012 —
сезон лиги, иначе история из базы», возраст проспектов 2012 − 18 = 1994 и т. д. Порт
сдвигает всё это на delta = season_year − 2012 (nhl-13-port/src/nhl13_year.cpp):

- li / subfic rD, …, Y и addi rD, rA, +Y — после инструкции rD += delta;
- addi rD, rA, −Y — после инструкции rD −= delta;
- cmpwi / cmplwi crN, rA, Y — после инструкции crN пересчитывается против Y + delta.

Правило: сдвигаются все li/subfic/cmp* с 2011–2013 и addi ±2011…2013 по всему образу,
кроме KEEP — мест, где число не год лиги (адреса, размеры, онлайн, исторические факты).
Плюс EXTRA — года, производные от 2012 (1962 = 2012 − 50, 1994 = 2012 − 18…). Разбор
каждого места — docs/year-and-date.md. Любое расхождение инструкции с ожидаемой — ошибка.
"""
import struct, sys

BASE = 0x82000000
YEARS = (2011, 2012, 2013)

# Совпадения с годом, которые сдвигать нельзя.
KEEP = {
    # li / cmp
    0x826AF878: 'li r5, 2013 — номер строки в assert',
    0x82D72B78: 'li r3, 2013 — «год продукта» для логов и онлайна (203 вызова)',
    0x83353728: 'li r4, 2012 — метка времени 12.12.2012 (онлайн)',
    0x82A04C88: 'cmpwi 2011 — сезон онлайна (82A2BBF8 = 2011 + x)',
    0x82A05AEC: 'cmpwi 2012 — сезон онлайна',
    0x82A12CD8: 'cmpwi 2012 — сезон онлайна',
    0x82A41198: 'cmpwi 2011 — сезон онлайна',
    0x827E0E5C: 'cmpwi 2011 — переезд Атланты в Виннипег (исторический факт)',
    0x82BC3238: 'cmpwi 2011 — внутри перевода Unix-времени',
    # addi: адреса (lis + addi), смещения в структурах, указатели
    0x82515E24: 'адрес', 0x8252C0F0: 'указатель', 0x8252CC40: 'указатель',
    0x8262A1F0: 'указатель', 0x8262A1F8: 'указатель', 0x826D6B6C: 'адрес', 0x826DA32C: 'адрес',
    0x827E642C: 'смещение в структуре', 0x82828AFC: 'адрес', 0x828323D0: 'адрес',
    0x829B15E0: 'адрес', 0x82AE82E8: 'адрес', 0x82AEE434: 'адрес', 0x82B91B8C: 'адрес',
    0x82D5D470: 'адрес', 0x82F54928: 'адрес', 0x82FF7DD4: 'адрес', 0x8366B838: 'адрес',
    0x836A5F20: 'адрес', 0x8379D038: 'адрес', 0x832A7D70: 'указатель', 0x832A91C8: 'указатель',
    0x832AAA34: 'указатель', 0x832F0A90: 'указатель', 0x832F0D20: 'указатель',
    # addi: онлайн-сезон и парная (де)сериализация поля «год − 2012»
    0x82A2BC1C: 'сезон онлайна 2011 + x', 0x82A4118C: 'сезон онлайна', 0x82A46560: 'сезон онлайна',
    0x82D73034: 'пара с 82D84704: +2012 / −2012 одного поля (сериализация)',
    0x82D84704: 'пара с 82D73034',
}

# Года, производные от базового 2012, — сдвигаются вместе с ним.
EXTRA = {
    0x827A9BE0: 'li r3, 1962 — минимальный год рождения в редакторе (2012 − 50)',
    0x827A9BE8: 'li r3, 1997 — максимальный год рождения (2012 − 15)',
    0x827DEBB8: 'li r11, 1962 — индекс в списке годов рождения',
    0x827DEBBC: 'cmpwi 1962 — то же',
    0x828C5F84: 'li r11, 1962 — год рождения не раньше 2012 − 50',
    0x827BF920: 'li r3, 1994 — FeLeague, слот 16: год рождения 18-летних (2012 − 18)',
    0x82788068: 'li r11, 1993 — год рождения игрока «Стань профи» по умолчанию',
    0x8278807C: 'li r11, 1992 — то же',
    0x82823CB8: 'li r7, 1986 — год рождения созданного игрока по умолчанию',
    0x82823D00: 'li r8, 2006 — год драфта созданного игрока по умолчанию',
    0x827D2F70: 'subfic 2030 — год драфта сгенерированного игрока (2012 + 18 − возраст)',
    0x8284EF78: 'cmplwi 2004 — «недавний драфт» (2012 − 8)',
    0x82985D00: 'cmplwi 2004 — то же в интерфейсе',
    # Пики драфта (leaguedraftpick.year = год − 1900; найдено nhl-legacy-port по Legacy 115/121/2021, проверено
    # 09.10.2026 по сейву: без сдвига у франшизы 2026/27 пики 2013–2018, драфт 2027 их не находит — 82927720
    # пишет выбор в запись [n] за концом массива пиков: порча кучи, повторные выборы, падение).
    0x82807734: 'li r25, 112 — пики при создании лиги: 6 лет начиная с 2012 + 1 − 1900 (828076C8)',
    0x8281E87C: 'addi r29, r31, 118 — пики нового сезона: (год − 2011) + 118 = год + 7 − 1900 (8281E850; '
                'аргумент — от сдвинутого «год − 2011» в 828EDC50)',
    0x8281EA3C: 'addi r11, r31, 2018 — то же полным числом (год + 7)',
}

# NHL Legacy (2015, сезон 2015/16; docs/legacy-port.md): года лиги 2014–2016, свои совпадения и
# производные (перенос KEEP/EXTRA NHL 13 через tools/xmatch.py + разбор новых мест Legacy).
LEGACY_KEEP = {
    # Из KEEP NHL 13 (то же место, число +3)
    0x8315A200: 'li r3, 2016 — «год продукта» для онлайна: год в путях запросов к серверам EA («%d/protected/competition/%d/…»), 64 вызова (NHL 13: 82D72B78 li 2013)',
    0x831E09A4: 'addi r10, r10, 2015 — онлайн-статистика «SetPlayerStat»: пара с 831E2278 — поле year привязки +2015 / −2015 для запроса к серверу (NHL 13: 82D73034)',
    0x831E2278: 'addi r11, r11, -2015 — пара с 831E09A4 (NHL 13: 82D84704)',
    # Факты и не-годы
    0x8297639C: 'cmpwi cr6, r31, 2014 — история названий команд: до 2014 команда 22 — «PhoenixCoyotes» (Phoenix → Arizona Coyotes, исторический факт; рядом 1993/1995/1996/1997/2011 того же списка, NHL 13: 827E0D18)',
    0x8303C5D0: 'cmplwi cr6, r18, 2016 — маска зелёного канала RGB565 0x07E0 (рядом 0x1F и 0xF800) — формат пикселей, не год (NHL 13: 82C59248 — то же число)',
    # Адреса (lis + addi)
    0x8252BAEC: 'addi r3, r11, 2016 — адрес 0x823407E0 «Blaze::GameReporting::ArsonCTF_Derived::»',
    0x8268FBE4: 'addi r11, r11, -2016 — адрес 0x8232F820',
    0x827659B0: 'addi r23, r11, -2016 — адрес 0x8232F820',
    0x82C8E590: 'addi r4, r10, -2016 — адрес 0x8209F820 «QuaternionOut»',
    0x832DC548: 'addi r4, r10, 2016 — адрес 0x821907E0 «GetCategoryMeta»',
    0x833016A0: 'addi r3, r11, -2016 — адрес 0x832EF820',
    0x8340F08C: 'addi r11, r11, 2016 — адрес 0x83C907E0',
    0x8340F638: 'addi r11, r11, 2016 — адрес 0x83C907E0',
    0x835A47EC: 'addi r11, r11, -2016 — адрес 0x83CDF820',
    0x83737A44: 'addi r4, r10, 2016 — адрес 0x823407E0 «Blaze::GameReporting::ArsonCTF_Derived::»',
    0x837F1864: 'addi r3, r11, -2016 — адрес 0x8394F820',
    0x837F6A6C: 'addi r3, r11, 2016 — адрес 0x839507E0',
    0x83837B08: 'addi r3, r11, 2016 — адрес 0x83C907E0',
    0x83877CA0: 'addi r5, r10, 2016 — адрес 0x822507E0 «gFromSittingFallbackMaxFramesToWait»',
    0x83893B34: 'addi r3, r11, 2016 — адрес 0x839707E0',
    0x838E20F0: 'addi r3, r7, -2016 — адрес 0x83CDF820',
    0x838ED218: 'addi r3, r11, -2016 — адрес 0x8397F820',
    0x838F1804: 'addi r3, r11, 2016 — адрес 0x839807E0',
    0x8390637C: 'addi r5, r7, 2016 — адрес 0x822B07E0 «gForecheckLikelihoodDCarriesMinZDist»',
    0x8392AD94: 'addi r11, r7, 2016 — адрес 0x83D307E0',
    0x8395D960: 'addi r3, r10, 2016 — адрес 0x83C907E0',
    0x8397D0C8: 'addi r3, r10, -2016 — адрес 0x83CDF820',
    # Стек: адрес в кадре (addi rD, r1, 2016)
    0x82A18EF0: 'addi r3, r1, 2016 — стек: адрес в кадре',
    0x82A18EFC: 'addi r5, r1, 2016 — стек: адрес в кадре',
    0x82A33538: 'addi r3, r1, 2016 — стек: адрес в кадре',
    0x82A33A24: 'addi r3, r1, 2016 — стек: адрес в кадре',
    0x82B0E988: 'addi r3, r1, 2016 — стек: адрес в кадре',
    0x82B0F584: 'addi r3, r1, 2016 — стек: адрес в кадре',
    0x82B0FE80: 'addi r3, r1, 2016 — стек: адрес в кадре',
    0x82B106CC: 'addi r3, r1, 2016 — стек: адрес в кадре',
    0x82B1354C: 'addi r3, r1, 2016 — стек: адрес в кадре',
    0x82B140D8: 'addi r3, r1, 2016 — стек: адрес в кадре',
    0x82B30868: 'addi r3, r1, 2016 — стек: адрес в кадре',
    0x82B315D8: 'addi r3, r1, 2016 — стек: адрес в кадре',
    0x82BB4864: 'addi r3, r1, 2016 — стек: адрес в кадре',
    0x82BB56B0: 'addi r3, r1, 2016 — стек: адрес в кадре',
    0x82D8577C: 'addi r3, r1, 2016 — стек: адрес в кадре',
    0x82D8578C: 'addi r3, r1, 2016 — стек: адрес в кадре',
    0x82D857AC: 'addi r3, r1, 2016 — стек: адрес в кадре',
    0x83020560: 'addi r3, r1, 2016 — стек: адрес в кадре',
    0x830205B4: 'addi r9, r1, 2016 — стек: адрес в кадре',
    0x83020624: 'addi r11, r1, 2016 — стек: адрес в кадре',
    0x830206B0: 'addi r7, r1, 2016 — стек: адрес в кадре',
    0x83349E38: 'addi r11, r1, 2016 — стек: адрес в кадре',
    0x82712CC4: 'addi r1, r1, 2016 — стек: снятие кадра 2016 байт в эпилоге',
    0x82E50070: 'addi r1, r1, 2016 — стек: снятие кадра 2016 байт в эпилоге',
    # Смещения в структурах
    0x834C2260: 'addi r10, r11, 2016 — смещение 2016 в структуре (массив записей по 76 байт с +2016)',
    0x834C22BC: 'addi r29, r3, 2016 — смещение 2016 в структуре (массив записей по 76 байт с +2016)',
    0x834C22FC: 'addi r3, r11, 2016 — смещение 2016 в структуре (массив записей по 76 байт с +2016)',
    0x834C5AA4: 'addi r30, r3, 2016 — смещение 2016 в структуре (массив записей по 76 байт с +2016)',
}

# Года, производные от 2015, — сдвигаются вместе с ним.
LEGACY_EXTRA = {
    0x829C4EE0: 'li r3, 1965 — минимальный год рождения в редакторе (2015 − 50) (NHL 13: 827A9BE0 li 1962)',
    0x829C4EE8: 'li r3, 2000 — максимальный год рождения в редакторе (2015 − 15) (NHL 13: 827A9BE8 li 1997)',
    0x829F6278: 'li r11, 1965 — индекс в списке годов рождения: год ≥ 1965 → год − 1965 (2015 − 50) (NHL 13: 827DEBB8 li 1962)',
    0x829F627C: 'cmpwi cr6, r29, 1965 — то же, сравнение (NHL 13: 827DEBBC cmpwi 1962)',
    0x82B374C4: 'li r11, 1965 — год рождения не раньше 2015 − 50 (NHL 13: 828C5F84 li 1962)',
    0x829C9278: 'li r3, 1994 — FeLeague слот 16 — год рождения 18-летних; в Legacy не пересчитан (1994 = 2012 − 18, по смыслу было бы 1997), сдвиг сохраняет поведение Legacy (NHL 13: 827BF920 li 1994)',
    0x82ABB4A0: 'li r11, 1996 — год рождения игрока «Стань профи» по умолчанию (2015 − 19) (NHL 13: 82788068 li 1993)',
    0x82ABB4B4: 'li r11, 1995 — то же (2015 − 20) (NHL 13: 8278807C li 1992)',
    0x82A4A6D0: 'li r7, 1986 — год рождения созданного игрока по умолчанию; в Legacy не пересчитан (2015 − 29) (NHL 13: 82823CB8 li 1986)',
    0x82A4A718: 'li r8, 2006 — год драфта созданного игрока по умолчанию; в Legacy не пересчитан (2015 − 9) (NHL 13: 82823D00 li 2006)',
    0x829DB7C4: 'subfic r11, r29, 2033 — год драфта сгенерированного игрока (2015 + 18 − возраст) (NHL 13: 827D2F70 subfic 2030)',
    0x82BA3BE0: 'cmplwi cr6, r11, 2004 — «недавний драфт»: год драфта > 2004; в Legacy не пересчитан (2015 − 11) (NHL 13: 8284EF78 cmplwi 2004)',
    0x82ACEA08: 'cmplwi cr6, r18, 2004 — то же в интерфейсе (NHL 13: 82985D00 cmplwi 2004)',
    0x82A1CCE4: 'li r25, 115 — пики драфта при создании лиги: 6 лет начиная с 115 = 2015 − 1900 (поле year таблицы leaguedraftpick; NHL 13: 82807734 li 112 — в EXTRA NHL 13 нет)',
    0x82A3571C: 'addi r29, r31, 121 — пики драфта, добавляемые при смене сезона: year = (год − 2014) + 121 = год + 7 − 1900 (аргумент сдвигается в 82B4BAE0; NHL 13: 8281E87C addi 118 — в EXTRA NHL 13 нет)',
    0x82A358DC: 'addi r11, r31, 2021 — то же полным числом: (год − 2014) + 2021 = год + 7 (NHL 13: 8281EA3C addi 2018 — в EXTRA NHL 13 нет)',
}

# Справка для --report: места Legacy, которые не перенеслись из врезок NHL 13 автоматически
# (xmatch), — почему сдвигаются (генератор сдвигает всё, что не в KEEP).
LEGACY_SHIFT_NOTES = {
    0x82971508: 'li r30, 2015 — год «без лиги» по умолчанию, при активной лиге — её год (NHL 13: 8276F01C)',
    0x829715D4: 'li r30, 2015 — то же (NHL 13: 8276F0E8)',
    0x82976E18: 'cmpwi cr6, r31, 2014 — статистика FE: год 2014 при совпадении состояния 61 читается как 2015 (прошлый сезон → текущий; новое в Legacy)',
    0x82976E7C: 'li r31, 2015 — то же: подставляемый текущий сезон',
    0x829808FC: 'addi r4, r11, -2015 — номер сезона: год лиги + смещение − 2015 (NHL 13: 827EC198)',
    0x829C8330: 'li r4, 2014 — FeLeague слот 1 (текущая дата): MakeDate(2014, 1, 1), затем дата лиги (NHL 13: 827BEA30 li 2011)',
    0x82A3FC48: 'cmpwi cr6, r4, 2015 — «после первого сезона»: вызов из годового обновления лиги 82B37C68 (NHL 13: 8282D228)',
    0x82A457F4: 'li r5, 2015 — год текущего сезона в запросе статистики 82B37820 (новое в Legacy)',
    0x82A543DC: 'addi r4, r10, -2015 — номер сезона от года лиги (новое в Legacy)',
    0x82A7A8D0: 'addi r3, r10, 2015 — COnlineSession, слот 19: год месяца сезона 2015 + (m + 8 − 1) / 12 (NHL 13: 8286CE40 addi 2011 — там сдвигался; спорное, см. report.md)',
    0x82ACF2B8: 'li r4, 2015 — дата календаря сезона: месяц > 6 (июль–декабрь) → 2015 (новое в Legacy)',
    0x82ACF2C4: 'li r4, 2016 — то же: январь–июнь → 2016',
    0x82AF547C: 'addi r27, r27, -2015 — номер сезона от года-аргумента (NHL 13: 82909FC4)',
    0x82AF8A74: 'cmpwi cr6, r29, 2015 — год ≥ сезона лиги — ветка сезона лиги (NHL 13: 8290C4F0)',
    0x82AFB304: 'li r4, 2015 — MakeDate(2015, 8, 1) (NHL 13: 828DC220)',
    0x82AFFE30: 'addi r9, r30, -2015 — номер сезона от года-аргумента (новое в Legacy)',
    0x82B001E8: 'cmpwi cr6, r11, 2015 — команда игрока и год < 2015 → год + 1 (общая функция 82B001B0; в NHL 13 сравнение стояло в вызывающих: 828C4484, 828C4D2C)',
    0x82B1EA68: 'addi r24, r11, -2015 — номер сезона от года даты: сдвиг ротации таблицы по модулю (аналог NHL 13: 828DB900 / 8286A06C)',
    0x82B219C0: 'addi r6, r20, -2015 — номер сезона от года лиги (NHL 13: 8285F288)',
    0x82B222B0: 'cmpwi cr6, r29, 2015 — команда игрока и год < 2015 → год + 1 (NHL 13: 828BB7E0)',
    0x82B224BC: 'cmpwi cr6, r29, 2015 — то же во второй функции (новое в Legacy)',
    0x82B27F34: 'addi r28, r11, -2015 — номер сезона; −1 = прошлый сезон (новое в Legacy)',
    0x82B2D480: 'addi r30, r11, -2014 — год лиги − 2014 = номер сезона + 1 (NHL 13: 828F85C0 addi −2011)',
    0x82B2E1DC: 'addi r4, r11, -2015 — номер сезона — поле year в запросе к базе (NHL 13: 828C4540)',
    0x82B2E3AC: 'addi r4, r11, -2015 — то же (NHL 13: 828C470C)',
    0x82B2E4F4: 'addi r4, r11, -2015 — то же (NHL 13: 828C4850)',
    0x82B2EC7C: 'addi r9, r9, -2015 — номер сезона (NHL 13: 828C4D90)',
    0x82B2EE84: 'addi r4, r11, -2015 — номер сезона — поле year в запросе (NHL 13: 828C4FA4)',
    0x82B2FBD4: 'addi r4, r9, -2015 — номер сезона от года записи (NHL 13: 828C1148)',
    0x82B31DBC: 'addi r29, r11, -2015 — номер сезона для массива «команда · 25 + сезон» (NHL 13: 828C6734)',
    0x82B32EF4: 'addi r29, r11, -2015 — то же (NHL 13: 828C785C)',
    0x82B37DAC: 'addi r11, r11, -2014 — год лиги − 2014 (NHL 13: 828D54D0 addi −2011)',
    0x82B3BE30: 'addi r11, r11, -2015 — знак (год лиги − 2015): «до первого сезона» (новое в Legacy)',
    0x82B3C668: 'cmplwi cr6, r11, 2015 — год даты = первый сезон → событие 21 календаря (NHL 13: 828B6218 cmplwi 2012)',
    0x82B4017C: 'cmpwi cr6, r27, 2015 — год ≥ сезона лиги (NHL 13: 828D0000)',
    0x82B62678: 'addi r10, r10, -2015 — номер сезона ≥ 1 (новое в Legacy)',
    0x82B6AFF0: 'addi r7, r27, -2015 — номер сезона — аргумент 82A6C4D8 (аналог NHL 13: 8291A060)',
    0x82B707EC: 'addi r10, r25, -2015 — номер сезона ≥ 1 (новое в Legacy)',
    0x82B77DB0: 'addi r4, r11, -2015 — номер сезона (NHL 13: 82932EB0)',
    0x82B7C4C8: 'addi r11, r11, -2015 — номер сезона → индекс таблицы по 8 байт (новое в Legacy)',
    0x82B88924: 'addi r11, r11, -2015 — номер сезона (новое в Legacy)',
    0x82B9B174: 'addi r11, r11, -2015 — номер сезона (новое в Legacy)',
    0x82B9BC8C: 'addi r11, r11, -2015 — номер сезона (новое в Legacy)',
    0x82BA5F58: 'addi r4, r25, -2015 — номер сезона — поле year в запросе (новое в Legacy)',
    0x82BA9298: 'li r27, 2015 — год лиги по умолчанию в leaguestates тип 13 (NHL 13: 82939708)',
    0x8316E10C: 'li r4, 2015 — MakeDate(2015, месяц, день − 1): событие 19 календаря сезона (новое в Legacy)',
    0x831E56B4: 'li r31, 2015 — первый год цикла по сезонам 2015…год лиги (NHL 13: 82D5872C)',
}

PROFILES = {
    'nhl13': dict(years=YEARS, keep=KEEP, extra=EXTRA, prefix='Nhl13', toml='nhl13.toml',
                  cpp='src/nhl13_year.cpp'),
    'legacy': dict(years=(2014, 2015, 2016), keep=LEGACY_KEEP, extra=LEGACY_EXTRA, notes=LEGACY_SHIFT_NOTES,
                   prefix='NhlLegacy',
                   toml='nhllegacy.toml', cpp='src/nhllegacy_year.cpp'),
}
P = PROFILES['nhl13']


def load(path):
    img = open(path, 'rb').read()
    e = struct.unpack('<I', img[0x3C:0x40])[0]
    nsec, optsz = struct.unpack('<H', img[e + 6:e + 8])[0], struct.unpack('<H', img[e + 20:e + 22])[0]
    for i in range(nsec):
        sh = e + 24 + optsz + 40 * i
        if img[sh:sh + 8].rstrip(b'\0') == b'.text':
            vsize, va, rsize = struct.unpack('<III', img[sh + 8:sh + 20])
            return img, BASE + va, BASE + va + min(vsize, rsize)
    raise SystemExit('нет секции .text')

def decode(w):
    """(вид, rD, rA, crN, imm) для li/addi/subfic/cmpwi/cmplwi, иначе None."""
    op, d, a = w >> 26, (w >> 21) & 31, (w >> 16) & 31
    simm = (w & 0xFFFF) - 0x10000 if w & 0x8000 else w & 0xFFFF
    if op == 14:
        return ('li', d, 0, None, simm) if a == 0 else ('addi', d, a, None, simm)
    if op == 8:
        return ('subfic', d, a, None, simm)
    if op == 11 and not d & 1:
        return ('cmpwi', None, a, d >> 2, simm)
    if op == 10 and not d & 1:
        return ('cmplwi', None, a, d >> 2, w & 0xFFFF)
    return None

def leap_math_after(img, addr, reg):
    """Результат дальше делится на 4 или берётся по модулю 4 — похоже на счёт високосных."""
    for k in range(1, 7):
        w = struct.unpack('>I', img[addr + 4 * k - BASE:addr + 4 * k - BASE + 4])[0]
        op, s = w >> 26, (w >> 21) & 31
        if op == 31 and ((w >> 1) & 0x3FF) == 824 and s == reg and ((w >> 11) & 31) == 2:
            return True  # srawi rX, reg, 2
        if op == 21 and s == reg and ((w >> 6) & 31, (w >> 1) & 31) == (30, 31):
            return True  # rlwinm rX, reg, 0, 30, 31 (& 3)
    return False

def sites(img, lo, hi):
    out = []
    for i, (w,) in enumerate(struct.iter_unpack('>I', img[lo - BASE:hi - BASE])):
        a = lo + 4 * i
        dec = decode(w)
        if not dec:
            continue
        kind, d, ra, cr, imm = dec
        if a in P['extra']:
            out.append((a, dec, 'extra'))
        elif kind == 'addi' and abs(imm) in P['years'] or kind != 'addi' and imm in P['years']:
            out.append((a, dec, 'keep' if a in P['keep'] else 'shift'))
    found = {a for a, _, _ in out}
    missing = [a for a in list(P['keep']) + list(P['extra']) if a not in found]
    if missing:
        raise SystemExit('нет ожидаемых инструкций: ' + ', '.join(f'{a:08X}' for a in missing))
    return out

def hook(a, dec):
    kind, d, ra, cr, imm = dec
    if kind in ('li', 'subfic') or kind == 'addi' and imm > 0:
        return f"{P['prefix']}YearAdd", [f'r{d}']
    if kind == 'addi':
        return f"{P['prefix']}YearSub", [f'r{d}']
    sign = 'S' if kind == 'cmpwi' else 'U'
    return f"{P['prefix']}YearCmp{sign}{imm}", [f'r{ra}', f'cr{cr}']

def main():
    global P
    sys.stdout.reconfigure(encoding='utf-8', newline='\n')
    args = sys.argv[1:]
    if '--game' in args:
        i = args.index('--game')
        game = args[i + 1]
        del args[i:i + 2]
        if game not in PROFILES:
            raise SystemExit(f'--game: {game}? ({", ".join(PROFILES)})')
        P = PROFILES[game]
        if not P['keep']:
            raise SystemExit(f'{game}: нет списка KEEP')
    img, lo, hi = load(args[0])
    found = sites(img, lo, hi)
    if '--report' in args:
        for a, (kind, d, ra, cr, imm), what in found:
            note = P['keep'].get(a) or P['extra'].get(a) or P.get('notes', {}).get(a, '')
            print(f'{a:08X}  {what:5}  {kind:6} {imm:6}  {note}')
        return
    shifted = [(a, dec) for a, dec, what in found if what != 'keep']
    for a, dec in shifted:
        if dec[0] in ('li', 'subfic', 'addi') and leap_math_after(img, a, dec[1]):
            raise SystemExit(f'{a:08X}: дальше счёт високосных — проверить вручную')
    print('# Сгенерировано tools/year_hooks.py — не править руками.')
    print(f"# Сдвиг года: {len(shifted)} мест (season_year в {P['toml']}, код — {P['cpp']}).")
    for a, dec in shifted:
        name, regs = hook(a, dec)
        print(f'\n[[midasm_hook]]\naddress = 0x{a:08X}\nname = "{name}"\n'
              f'registers = [{", ".join(chr(34) + r + chr(34) for r in regs)}]\nafter_instruction = true')

if __name__ == '__main__':
    main()
