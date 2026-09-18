"""Точка входа: `python -m integrations.telegram` (её вызывает start.bat)."""
from __future__ import annotations

import sys

from integrations.telegram.gateway import main

if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
