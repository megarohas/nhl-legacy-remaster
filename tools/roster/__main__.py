"""Запуск пакета: python tools/roster <этап> … (см. tools/roster/cli.py)."""
import os
import sys

if not __package__:
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from roster.cli import main  # noqa: E402

if __name__ == '__main__':      # процессы-помощники (photos_other.build) импортируют модуль заново
    main()
