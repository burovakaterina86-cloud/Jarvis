"""Запускатель фоновых работ внутри бота: берёт запросы агента, запускает, следит, присылает результат.

Бот живёт долго, поэтому процесс работы не умирает вместе с ходом агента (в отличие от запуска из хода).
Каждые ~10 секунд бот зовёт `tick()`:
  1. новые запросы из `jobs/requests/` — перепроверка, запись состояния `state/jobs/<id>.json`, запуск (не больше MAX_RUNNING);
  2. закончившиеся процессы — письмо ей в почтовый ящик: «готово» + файлы или «не получилось» + хвост журнала;
  3. работы со статусом running, которых бот не помнит (перезапуск) — «прервана», чтобы не висели вечно.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

from . import ALLOWED_MODULES, ROOT, validate  # noqa: F401  (ALLOWED_MODULES — для читателя)

MAX_RUNNING = 2
MAX_RUN_SEC = 2 * 60 * 60          # работа дольше двух часов — зависла, останавливаем
LOG_TAIL_LINES = 6


def _python(root: Path) -> str:
    venv = Path(root) / ".venv" / "Scripts" / "python.exe"
    return str(venv) if venv.exists() else sys.executable


def _clean_env() -> dict:
    """Без токенов бота и Claude: работе они не нужны, а ключи сервисов (`APIFY_TOKEN`…) модули берут из `.env` сами."""
    env = dict(os.environ)
    for key in list(env):
        if key.startswith(("TELEGRAM", "CLAUDE", "ANTHROPIC")) and key != "CLAUDE_CODE_GIT_BASH_PATH":
            env.pop(key)
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    return env


class JobRunner:
    def __init__(self, root: Path | str = ROOT, *, post, popen=subprocess.Popen, clock=time.time, env=None):
        self.root = Path(root)
        self.post = post                  # (text, files) -> None : почтовый ящик
        self.popen = popen
        self.clock = clock
        self.env = env if env is not None else _clean_env()
        self.procs: dict[str, object] = {}
        self.requests = self.root / "jobs" / "requests"
        self.state = self.root / "state" / "jobs"

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

    def _take_requests(self) -> None:
        if not self.requests.is_dir():
            return
        for path in sorted(self.requests.glob("*.json")):
            try:
                req = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                path.rename(path.with_suffix(".bad"))
                continue
            problems = validate(req, self.root)
            job_id = path.stem
            if problems:
                path.rename(path.with_suffix(".rejected"))
                self.post(f"Работу «{req.get('title', job_id) if isinstance(req, dict) else job_id}» не запустил: "
                          + "; ".join(problems), [])
                continue
            rec = {"id": job_id, "title": req["title"], "argv": req["argv"], "files": req.get("files", []),
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
                log = open(log_path, "wb")
                proc = self.popen([_python(self.root), *rec["argv"]], cwd=str(self.root), env=self.env, stdout=log,
                                  stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                                  creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            except OSError as exc:
                rec.update(status="failed", finished_at=self.clock(), error=type(exc).__name__)
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

    def _poll(self) -> None:
        for rec in self._records():
            if rec["status"] != "running":
                continue
            proc = self.procs.get(rec["id"])
            if proc is None:                   # бот перезапускался: его дети умерли вместе с ним
                rec.update(status="interrupted", finished_at=self.clock())
                self._save(rec)
                self.post(f"Работа «{rec['title']}» прервалась: бот перезапускался. Скажи, и я поставлю её заново.", [])
                continue
            rc = proc.poll()
            if rc is None:
                if self.clock() - rec.get("started_at", self.clock()) > MAX_RUN_SEC:
                    proc.kill()
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
