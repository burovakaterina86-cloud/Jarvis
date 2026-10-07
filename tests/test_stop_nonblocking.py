"""Остановка хода не замораживает бот и не оставляет процессов-сирот (ревью 2026-10-07)."""
import asyncio
import subprocess
import time

from runtime import claude_bridge, procutil


class FakeProc:
    pid, returncode = 4242, None

    def __init__(self):
        self.killed_after = None

    def kill(self):
        self.killed_after = "killed"


def test_kill_tree_returns_at_once_and_kills_tree_before_the_process(monkeypatch):
    order = []

    def slow_taskkill(cmd, **kw):
        order.append(("taskkill", cmd[0]))
        time.sleep(0.4)                      # раньше цикл событий ждал это время (до 5 с)

    proc = FakeProc()
    monkeypatch.setattr(procutil.sys, "platform", "win32")
    monkeypatch.setattr(procutil.subprocess, "run", slow_taskkill)
    t0 = time.monotonic()
    procutil.kill_tree(proc)
    assert time.monotonic() - t0 < 0.2 and proc.killed_after is None     # не ждали taskkill
    for _ in range(50):
        if proc.killed_after:
            break
        time.sleep(0.05)
    assert order == [("taskkill", "taskkill")] and proc.killed_after == "killed"   # дерево раньше родителя


def test_kill_tree_ignores_finished_process():
    proc = FakeProc()
    proc.returncode = 0
    procutil.kill_tree(proc)
    time.sleep(0.1)
    assert proc.killed_after is None


async def test_stop_between_launches_is_remembered(monkeypatch):
    """Таймаут/`/stop` в паузе между запусками (процесса нет) не теряется: повторный запуск не нужен."""
    claude_bridge._active.add("gap")
    try:
        assert claude_bridge.stop("gap") is True and "gap" in claude_bridge._stopped
    finally:
        claude_bridge._active.discard("gap")
        claude_bridge._stopped.discard("gap")
    assert claude_bridge.stop("never-ran") is False


async def test_cancelled_turn_leaves_no_orphan(monkeypatch):
    killed = []
    monkeypatch.setattr(claude_bridge.procutil, "kill_tree", lambda proc: killed.append(proc))

    class Boom(FakeProc):
        class stdout:
            @staticmethod
            async def readline():
                raise asyncio.CancelledError

        class stderr:
            @staticmethod
            async def read():
                return b""

        class stdin:
            write = staticmethod(lambda b: None)
            drain = staticmethod(lambda: asyncio.sleep(0))
            close = staticmethod(lambda: None)

    proc = Boom()

    async def fake_exec(*a, **kw):
        return proc

    monkeypatch.setattr(claude_bridge.asyncio, "create_subprocess_exec", fake_exec)
    try:
        await claude_bridge._run_once("p", None, None, "r1", "t", {}, ["x"], ".")
    except asyncio.CancelledError:
        pass
    assert killed == [proc]
