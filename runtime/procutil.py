"""Остановка дерева процессов хода (Claude, Codex) без остановки самого бота.

`taskkill /T /F` ждали прямо в цикле событий (`subprocess.run(..., timeout=5)`): на время вызова замирали Telegram,
кнопки подтверждения и Approvals API. Теперь это делает отдельный поток; порядок прежний — сначала дерево
(`taskkill` находит детей, пока жив родитель), потом сам процесс.
"""
from __future__ import annotations

import subprocess
import sys
import threading


def _kill_tree_blocking(proc) -> None:
    if getattr(proc, "returncode", None) is None and sys.platform == "win32":
        try:
            subprocess.run(["taskkill", "/T", "/F", "/PID", str(proc.pid)], stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL, timeout=5,
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        except (OSError, subprocess.SubprocessError):
            pass
    try:
        proc.kill()
    except (ProcessLookupError, OSError):
        pass


def pid_alive(pid: int) -> bool:
    """Жив ли процесс. На Windows `os.kill(pid, 0)` посылает Ctrl+C — поэтому через OpenProcess."""
    if pid <= 0:
        return False
    if sys.platform == "win32":
        import ctypes
        handle = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid)   # PROCESS_QUERY_LIMITED_INFORMATION
        if not handle:
            return False
        ctypes.windll.kernel32.CloseHandle(handle)
        return True
    import os
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def kill_tree(proc) -> None:
    """Убивает процесс и его детей, не блокируя вызывающего (можно из цикла событий)."""
    if getattr(proc, "returncode", None) is not None:
        return
    threading.Thread(target=_kill_tree_blocking, args=(proc,), name="kill-tree", daemon=True).start()
