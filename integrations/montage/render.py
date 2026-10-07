"""Покадровый рендер оверлея: Node + puppeteer-core + Edge/Chrome. Кадры — прозрачные PNG 1080×1920."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

from runtime import procutil, secretenv

from . import config

MJS = config.TEMPLATES / "render.mjs"


def allowed_roots(html: Path) -> list[Path]:
    """Папки, из которых странице оверлея можно читать файлы: шрифты, логотипы, шаблоны и она сама."""
    return [config.ASSETS, config.LOGO_CACHE, config.TEMPLATES, Path(html).resolve().parent]


def env_for(html: Path, frames: Path, dur: float, fps: int = config.FPS, t0=None, t1=None) -> dict:
    env = secretenv.scrub()   # node и браузер страницы: никаких ключей
    env.update(MONTAGE_PUPPETEER=config.find_puppeteer(), MONTAGE_BROWSER=config.find_browser(), MONTAGE_HTML=str(Path(html).resolve()),
               MONTAGE_FRAMES=str(Path(frames).resolve()), MONTAGE_FPS=str(fps), MONTAGE_DUR=str(dur),
               MONTAGE_ALLOW=json.dumps([str(p) for p in allowed_roots(html)]))
    if t0 is not None:
        env["MONTAGE_T0"] = str(t0)
    if t1 is not None:
        env["MONTAGE_T1"] = str(t1)
    return env


LOCK_NAME = ".build.lock"
LOCK_STALE_SEC = 2 * 60 * 60
RENDER_TIMEOUT_SEC = 60 * 60     # покадровый рендер дольше часа — завис
FRAME_TOLERANCE = 3          # допустимый недобор кадров из-за округления длительности


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
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


class BuildBusy(RuntimeError):
    """В этой рабочей папке уже идёт сборка — вторая испортила бы кадры первой."""


def acquire_lock(work: Path, alive=pid_alive, now=time.time) -> Path:
    """Замок сборки: два рендера в одну папку стирали друг другу кадры (2026-10-06). Чужой живой — отказ, мёртвый — снимаем."""
    lock = Path(work) / LOCK_NAME
    for _ in range(3):
        try:
            # O_EXCL: создание и проверка — одна операция, две сборки не пройдут замок одновременно
            fd = os.open(lock, os.O_WRONLY | os.O_CREAT | os.O_EXCL)
        except FileExistsError:
            pid = "?"
            try:
                pid, started = (lock.read_text(encoding="utf-8").split() + ["0", "0"])[:2]
                busy = alive(int(pid)) and now() - float(started) < LOCK_STALE_SEC
            except (OSError, ValueError):
                busy = False
            if busy:
                raise BuildBusy(f"сборка в {Path(work).name} уже идёт (процесс {pid}); дождись её или останови")
            lock.unlink(missing_ok=True)      # замок мёртвой или зависшей сборки — снимаем и пробуем снова
            continue
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(f"{os.getpid()} {now()}")
        return lock
    raise BuildBusy(f"не удалось взять замок сборки в {Path(work).name}")


def rmtree_retry(path: Path, tries: int = 6, pause: float = 1.0, sleep=time.sleep) -> None:
    """Стереть папку, переждав занятые файлы: на Windows хвост оборванного рендера ещё держит кадры."""
    for attempt in range(tries):
        try:
            shutil.rmtree(path)
            return
        except FileNotFoundError:
            return
        except OSError:
            if attempt == tries - 1:
                raise
            sleep(pause)


def kill_orphans() -> None:
    """Добить хвосты оборванной сборки (node render.mjs и его браузер), чтобы они не писали в чужие кадры."""
    if sys.platform != "win32":
        return
    script = ("Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -match 'montage.templates.render\\.mjs' } "
              "| ForEach-Object { taskkill /T /F /PID $_.ProcessId | Out-Null }")
    try:
        subprocess.run(["powershell", "-NoProfile", "-Command", script], capture_output=True, timeout=30,
                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except (OSError, subprocess.SubprocessError):
        pass


def other_builds_alive(parent: Path, exclude: Path, alive=pid_alive) -> bool:
    """Идёт ли сборка в соседней рабочей папке: её рендер добивать нельзя."""
    for lock in Path(parent).glob(f"*/{LOCK_NAME}"):
        if lock.parent.resolve() == Path(exclude).resolve():
            continue
        try:
            if alive(int(lock.read_text(encoding="utf-8").split()[0])):
                return True
        except (OSError, ValueError, IndexError):
            continue
    return False


def count_frames(frames: Path) -> int:
    return sum(1 for _ in Path(frames).glob("*.png")) if Path(frames).is_dir() else 0


def render_frames(work: Path, dur: float, fps: int = config.FPS, t0=None, t1=None, progress=print) -> Path:
    """work/overlay.html → work/frames/00001.png … Возвращает папку с кадрами.

    Защита от оборванной сборки (её требование 2026-10-06, «две фоновые сборки оборвались и испортили кадры»):
    замок на рабочую папку, добивание хвостов старого рендера, стирание старых кадров с повторами и проверка,
    что кадров набралось ровно столько, сколько нужно, до того как их возьмёт ffmpeg."""
    work = Path(work)
    frames = work / "frames"
    lock = acquire_lock(work)
    try:
        if t0 is None:
            if not other_builds_alive(work.parent, work):
                kill_orphans()
            rmtree_retry(frames)
        proc = subprocess.Popen(["node", str(MJS)], env=env_for(work / "overlay.html", frames, dur, fps, t0, t1),
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8")
        timed_out = threading.Event()

        def on_timeout():
            timed_out.set()
            procutil.kill_tree(proc)          # вместе с браузером внутри

        timer = threading.Timer(RENDER_TIMEOUT_SEC, on_timeout)
        timer.daemon = True
        timer.start()
        tail = []
        code = None
        try:
            for line in proc.stdout:
                tail.append(line.rstrip())
                if line.startswith(("кадр", "готово")):
                    progress(line.rstrip())
            code = proc.wait()
        finally:
            timer.cancel()
            if code is None:                  # исключение по дороге (Ctrl+C, сбой чтения): процесс не оставляем
                procutil.kill_tree(proc)
        if timed_out.is_set():
            raise RuntimeError(f"рендер кадров не уложился в {RENDER_TIMEOUT_SEC // 60} минут и остановлен")
        if code != 0:
            raise RuntimeError("рендер кадров упал:\n" + "\n".join(tail[-12:]))
        if t0 is None:
            have, need = count_frames(frames), round(dur * fps)
            if have < need - FRAME_TOLERANCE:
                raise RuntimeError(f"кадры неполные: {have} из {need}. Запусти сборку заново целиком (папка кадров очистится сама).")
        return frames
    finally:
        lock.unlink(missing_ok=True)
