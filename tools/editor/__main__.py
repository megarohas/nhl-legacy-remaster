"""python tools/editor [--install ПАПКА_ИГРЫ] [--port N] [--no-window] [--lang ru|en] — редактор (docs/editor.md)."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from app import main  # noqa: E402

sys.exit(main())
