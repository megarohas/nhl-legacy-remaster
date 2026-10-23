"""kitport — перенос форм (свитер, гетры, шорты, номера, превью меню) из новых EA NHL в NHL Legacy.

Одна точка входа для стадий: проверка окружения, снимок «было», сборка, сравнение с игрой, установка с копией
заменённого, откат, листы «было | стало», схема развёртки. Что и почему делается — руководство docs/kitport.md
(анатомия формы Legacy, источники, порядок работ, каталог параметров, проверки, грабли).

Запуск — из папки tools/ venv-ом game/work/nhl24/venv:

    python -m kitport doctor                  # python и пакеты, папки источника и Legacy, cache:, игра, git
    python -m kitport status                  # что стоит в игре против сборки, паки, копии, журнал
    python -m kitport snapshot [--tag T]      # «было»: файлы слота форм → compare/kitport/<дата>-T/
    python -m kitport build [--club MIN] [--kits away,home] [--stages kit,slot,pack,overlay] [--meshes]
    python -m kitport diff                    # сборка (legacy-data/out*) против cache: игры
    python -m kitport install --tag T [--yes] # копия заменяемого → backup-cache/user-<дата>-T, установка, сверка
    python -m kitport rollback DIR [--yes]    # вернуть файлы из backup-cache/DIR (игра закрыта)
    python -m kitport sheet [--before DIR]    # листы «было | стало» по последнему снимку
    python -m kitport uvmap [--kit MIN_away]  # схема развёртки свитера Legacy: части тела и зоны номеров
    python -m kitport params                  # каталог параметров формы: значение сейчас, единицы, причина
    python -m kitport check [--clubs TBL]     # лист проверки: ворот, рельеф, зоны рукава, шрифт, превью, замер щита
    python -m kitport present [--clubs TBL]   # лист «ставим или правим»: наша и оригинал, «одетый» свитер, игрок,
                                              # каска, наклейка, шрифт — по листу на форму
    python -m kitport survey [--clubs boston] # обзор форм клубов источника (перед, плечо, ворот) — разбор по типам
    python -m kitport collar --clubs TOR [--source-only]   # ворот крупно: наш и источник с рельефом, прямо и сверху
    python -m kitport yoke --clubs MTL      # кокетка: наша и источник в одних видах, замер края
    python -m kitport lettering [--clubs CHI]   # фамилия, номер и промежутки букв на спине (см) против эталона
    python -m kitport backs [--clubs MIN,BUF]   # спины всех форм слота одним листом — фамилия и номер, как в игре
    python -m kitport profile --club BOS [--write]   # генератор профиля клуба из NHL 27: профиль, номера, каска
    python -m kitport audit [--clubs ANA] [--helmets]   # автопроверка: номера на полосах, спина, низ гетр, каска
"""
