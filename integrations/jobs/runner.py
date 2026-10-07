"""Запускатель фоновых работ внутри бота: берёт запросы агента, запускает, следит, присылает результат.

Бот живёт долго, поэтому процесс работы не умирает вместе с ходом агента (в отличие от запуска из хода).
Каждые ~10 секунд бот зовёт `tick()`:
  1. новые запросы из `jobs/requests/` — перепроверка, запись состояния `state/jobs/<id>.json`, запуск (не больше MAX_RUNNING);
  2. закончившиеся процессы — письмо ей в почтовый ящик: «готово» + файлы или «не получилось» + хвост журнала;
  3. работы со статусом running, которых бот не помнит (перезапуск) — «прервана», чтобы не висели вечно.
"""
from __future__ import annotations

import json
import asyncio
import os
import subprocess
import sys
import time
import uuid
from pathlib import Path

from runtime import errorlog, procutil, secretenv

from . import ALLOWED_MODULES, ROOT, validate  # noqa: F401  (ALLOWED_MODULES — для читателя)

MAX_RUNNING = 2
MAX_RUN_SEC = 2 * 60 * 60          # работа дольше двух часов — зависла, останавливаем
LOG_TAIL_LINES = 6


def _python(root: Path) -> str:
    venv = Path(root) / ".venv" / "Scripts" / "python.exe"
    return str(venv) if venv.exists() else sys.executable


# `python -m модуль` ставит текущую папку первой в sys.path: положенный в корень проекта argparse.py или json.py
# подменил бы стандартный модуль внутри белого списка. Здесь корень идёт после стандартной библиотеки.
_BOOT = ("import runpy, sys; sys.path.append(sys.argv.pop(1)); "
         "m = sys.argv[1]; sys.argv[0:2] = [m]; runpy.run_module(m, run_name='__main__', alter_sys=True)")


def _command(root: Path, argv: list[str]) -> list[str]:
    """Команда запуска работы: `-m модуль аргументы…` → безопасный запуск того же модуля."""
    if len(argv) >= 2 and argv[0] == "-m":
        return [_python(root), "-P", "-c", _BOOT, str(root), *argv[1:]]
    return [_python(root), *argv]


def _clean_env() -> dict:
    """Без токенов бота и Claude: работе они не нужны, а ключи сервисов (`APIFY_TOKEN`…) модули берут из `.env` сами."""
    env = secretenv.scrub()
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    return env


class JobRunner:
    def __init__(self, root: Path | str = ROOT, *, post, popen=subprocess.Popen, clock=time.time, env=None, owner_chat=None):
        self.root = Path(root)
        self.post = post                  # (text, files) -> None : почтовый ящик
        self.popen = popen
        self.clock = clock
        self.env = env if env is not None else _clean_env()
        self.owner_chat = str(owner_chat) if owner_chat is not None else None
        self.procs: dict[str, object] = {}
        self.requests = self.root / "jobs" / "requests"
        self.state = self.root / "state" / "jobs"

    def cancel_chat(self, chat_id: str) -> list[str]:
        self._take_requests()
        ids = []
        for rec in self._records():
            legacy = not rec.get("chat") and self.owner_chat == str(chat_id)
            if (str(rec.get("chat")) != str(chat_id) and not legacy) or rec["status"] not in ("queued", "running"):
                continue
            ids.append(rec["id"])
            rec.update(status="stopped", finished_at=self.clock(), legacy_owner=legacy)
            self._save(rec)
            proc = self.procs.get(rec["id"])
            if proc is not None:
                procutil.kill_tree(proc)
            elif rec.get("pid") and procutil.pid_alive(rec["pid"]):
                class Orphan:
                    pid = rec["pid"]
                    returncode = None
                    def kill(self):
                        pass
                procutil.kill_tree(Orphan())
        return ids

    async def wait_stopped(self, job_ids: list[str], timeout: float) -> bool:
        deadline = time.monotonic() + timeout
        while True:
            alive = False
            for job_id in job_ids:
                proc = self.procs.get(job_id)
                rec = next((r for r in self._records() if r["id"] == job_id), {})
                if proc is not None:
                    alive |= proc.poll() is None
                elif rec.get("pid"):
                    alive |= procutil.pid_alive(rec["pid"])
            if not alive:
                return True
            if time.monotonic() >= deadline:
                return False
            await asyncio.sleep(0.05)

    # ---- состояние

    def _path(self, job_id: str) -> Path:
        return self.state / f"{job_id}.json"

    def _save(self, rec: dict) -> None:
        self.state.mkdir(parents=True, exist_ok=True)
        tmp = self._path(rec["id"]).with_suffix(".tmp")
        tmp.write_text(json.dumps(rec, ensure_ascii=False, indent=1), encoding="utf-8")
        os.replace(tmp, self._path(rec["id"]))

    def _records(self) -> list[dict]:
        out = []
        for path in sorted(self.state.glob("*.json")) if self.state.is_dir() else []:
            try:
                out.append(json.loads(path.read_text(encoding="utf-8")))
            except (OSError, ValueError):
                continue
        return out

    # ---- шаги

    def _set_aside(self, path: Path, suffix: str) -> None:
        """Убирает обработанный запрос под уникальное имя: Windows не даёт rename поверх существующего файла,
        и один повторный запрос навсегда ломал бы опрос."""
        os.replace(path, path.with_name(f"{path.stem}-{uuid.uuid4().hex[:6]}{suffix}"))

    def _take_requests(self) -> None:
        if not self.requests.is_dir():
            return
        for path in sorted(self.requests.glob("*.json")):
            try:
                self._take_request(path)
            except Exception as exc:  # noqa: BLE001 — один плохой файл не должен останавливать остальные
                errorlog.record("jobs.take_request", exc, file=path.name)
                try:
                    self._set_aside(path, ".bad")
                except OSError:
                    pass

    def _take_request(self, path: Path) -> None:
        try:
            req = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            self._set_aside(path, ".bad")
            errorlog.record("jobs.bad_request", exc, file=path.name)
            self.post(f"Запрос на работу {path.name} не читается (битый JSON), не запустил.", [])
            return
        problems = validate(req, self.root)
        job_id = path.stem
        if self._path(job_id).exists():       # то же имя у уже идущей работы: не затираем её запись
            job_id = f"{job_id}-{uuid.uuid4().hex[:6]}"
        if problems:
            self._set_aside(path, ".rejected")
            self.post(f"Работу «{req.get('title', job_id) if isinstance(req, dict) else job_id}» не запустил: "
                      + "; ".join(problems), [])
            return
        rec = {"id": job_id, "title": req["title"], "argv": req["argv"], "files": req.get("files", []),
               "chat": req.get("chat", ""), "task_id": req.get("task_id", ""),
               "done": req.get("done", ""), "fail": req.get("fail", ""), "status": "queued",
               "queued_at": self.clock()}
        self._save(rec)
        path.unlink(missing_ok=True)

    def _start_queued(self) -> None:
        running = sum(1 for r in self._records() if r["status"] == "running")
        for rec in self._records():
            if rec["status"] != "queued" or running >= MAX_RUNNING:
                continue
            self.state.mkdir(parents=True, exist_ok=True)
            log_path = self.state / f"{rec['id']}.log"
            try:
                with open(log_path, "wb") as log:    # потомок получает свой дескриптор, наш закрываем сразу
                    proc = self.popen(_command(self.root, rec["argv"]), cwd=str(self.root), env=self.env,
                                      stdout=log, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                                      creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            except OSError as exc:
                errorlog.record("jobs.start", exc, job=rec["id"])
                rec.update(status="failed", finished_at=self.clock(), error=f"{type(exc).__name__}: {exc}"[:200])
                self._save(rec)
                self.post(f"Работа «{rec['title']}» не запустилась: {type(exc).__name__}.", [])
                continue
            self.procs[rec["id"]] = proc
            rec.update(status="running", started_at=self.clock(), pid=getattr(proc, "pid", None), log=str(log_path))
            self._save(rec)
            running += 1

    def _tail(self, rec: dict) -> str:
        try:
            lines = Path(rec["log"]).read_text(encoding="utf-8", errors="replace").strip().splitlines()
        except (OSError, KeyError):
            return ""
        from runtime.redact import redact
        return redact("\n".join(lines[-LOG_TAIL_LINES:]))

    def _finish(self, rec: dict, rc: int) -> None:
        if rec.get("status") == "stopped":
            return
        rec.update(status="done" if rc == 0 else "failed", rc=rc, finished_at=self.clock())
        self._save(rec)
        minutes = max(1, round((rec["finished_at"] - rec.get("started_at", rec["finished_at"])) / 60))
        if rc == 0:
            files = [f for f in rec["files"] if (self.root / f).is_file()]
            text = f"Готово: {rec['title']} ({minutes} мин)."
            if rec.get("done"):
                text += " " + rec["done"]
            missing = [f for f in rec["files"] if f not in files]
            if missing:
                text += " Но файла нет: " + ", ".join(missing) + " — загляни в журнал или скажи мне."
            self.post(text, files)
        else:
            text = f"Не получилось: {rec['title']} (код {rc})."
            tail = self._tail(rec)
            if rec.get("fail"):
                text += " " + rec["fail"]
            if tail:
                text += "\nКонец журнала:\n" + tail
            self.post(text, [])

    def _poll_orphan(self, rec: dict) -> None:
        """Работа, начатая до перезапуска бота. На Windows дети не умирают вместе с родителем: пока процесс жив,
        ждём, а не помечаем «прервана» (иначе она поставила бы вторую копию в ту же папку)."""
        pid, started = rec.get("pid"), rec.get("started_at", self.clock())
        too_long = self.clock() - started > MAX_RUN_SEC
        if isinstance(pid, int) and procutil.pid_alive(pid) and not too_long:
            return
        files = rec.get("files") or []
        done = (bool(files) and not too_long
                and all((self.root / f).is_file() and (self.root / f).stat().st_mtime >= started for f in files))
        if done and isinstance(pid, int):   # процесс закончился, пока бота не было, и результат на месте
            self._finish(rec, 0)
            return
        rec.update(status="interrupted", finished_at=self.clock())
        self._save(rec)
        self.post(f"Работа «{rec['title']}» прервалась: бот перезапускался. Скажи, и я поставлю её заново.", [])

    def _poll(self) -> None:
        for rec in self._records():
            if rec["status"] != "running":
                continue
            proc = self.procs.get(rec["id"])
            if proc is None:                   # бот перезапускался
                self._poll_orphan(rec)
                continue
            rc = proc.poll()
            if rc is None:
                if self.clock() - rec.get("started_at", self.clock()) > MAX_RUN_SEC:
                    procutil.kill_tree(proc)    # вместе с ffmpeg и браузером внутри работы
                    self.procs.pop(rec["id"], None)
                    rec.update(status="failed", rc=-9, finished_at=self.clock())
                    self._save(rec)
                    self.post(f"Работа «{rec['title']}» шла больше двух часов, остановил.", [])
                continue
            self.procs.pop(rec["id"], None)
            self._finish(rec, rc)

    def tick(self) -> None:
        self._poll()
        self._take_requests()
        self._start_queued()
