"""Общее для тестов: сторож боевых журналов и копия Guard во временном корне."""
import shutil
from datetime import date
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]

# Журналы живого бота. Тесты не должны дописывать в них ни строки: иначе по журналу
# не понять, что делал сам JARVIS (до 2026-10-05 там было 470 строк шума от тестов).
LIVE_JOURNALS = (
    REPO / "state" / "events.jsonl",
    REPO / "state" / "jarvis.log",              # лог бота (gateway.setup_logging)
    REPO / "state" / "errors.jsonl",            # журнал ошибок (runtime/errorlog.py)
    REPO / "state" / "errors_index.json",
    REPO / "state" / "approvals.jsonl",
    REPO / "state" / "sessions.json",
    REPO / "state" / "session_activity.json",   # время её последнего хода (P3.1)
    REPO / "state" / "runtime.json",            # кто работает: Claude или Codex (P4.1)
    REPO / "state" / "limits.json",
    REPO / "state" / "deferred.json",
    REPO / "state" / "codex_canary.json",
    # эпизоды пишет и мост (task_router.EPISODES_DIR): тест с настоящим роутером подменяет путь
    REPO / "memory" / "episodes" / f"{date.today():%Y-%m}.jsonl",
)


def _sizes():
    return {p: (p.stat().st_size if p.exists() else None) for p in LIVE_JOURNALS}


@pytest.fixture(scope="session", autouse=True)
def live_journals_untouched():
    if (REPO / "state" / "approvals.port").exists():
        # Бот запущен и сам пишет в журналы — сравнение размеров ничего не докажет.
        yield
        return
    before = _sizes()
    yield
    changed = [str(p.relative_to(REPO)) for p, size in _sizes().items() if size != before[p]]
    assert not changed, (
        f"тесты дописали в боевые журналы: {changed}. Подпроцессный Guard запускай через "
        "фикстуру guard_copy (копия во временном корне). Если в это время работал бот — "
        "запись могла быть его, перезапусти тесты при остановленном боте.")


@pytest.fixture(autouse=True)
def isolated_worker_state(tmp_path, monkeypatch):
    """Кто работает (Claude/Codex), лимиты, предложения и отложенные задачи — во временной папке."""
    from runtime import worker
    monkeypatch.setattr(worker, "STATE_DIR", tmp_path / "worker-state")


@pytest.fixture(autouse=True)
def isolated_dialogue_context(tmp_path, monkeypatch):
    """Тестовые ходы не подмешивают поправки из живого разговора владелицы."""
    from runtime import task_router
    monkeypatch.setattr(task_router, "ROOT", tmp_path)


@pytest.fixture(autouse=True)
def isolated_logging(tmp_path, monkeypatch):
    """Лог бота в тестах — во временной папке. Тест `gateway.main` зовёт `setup_logging()` с путём по умолчанию, и
    к корневому логгеру цепляется файловый обработчик боевого `state/jarvis.log`: трассировки тестов попадали в
    живой журнал бота. Обработчики, добавленные тестом, после него снимаются."""
    import logging

    from integrations.telegram import gateway
    real = gateway.setup_logging
    monkeypatch.setattr(gateway, "setup_logging", lambda path=None: real(path or tmp_path / "state" / "jarvis.log"))
    root = logging.getLogger()
    before = list(root.handlers)
    yield
    for handler in list(root.handlers):
        if handler not in before:
            root.removeHandler(handler)
            handler.close()


@pytest.fixture(autouse=True)
def isolated_errorlog(tmp_path, monkeypatch):
    """Журнал ошибок — во временной папке: ни логгер, ни мост в тесте не пишут в боевой state/."""
    from runtime import errorlog
    monkeypatch.setattr(errorlog, "ERRORS_PATH", tmp_path / "errlog" / "errors.jsonl")
    monkeypatch.setattr(errorlog, "INDEX_PATH", tmp_path / "errlog" / "errors_index.json")


@pytest.fixture
def guard_copy(tmp_path):
    """Путь к копии guard.py во временном корне: guard.py берёт корень из своего
    расположения (parents[2]), поэтому и журнал, и policy у копии — временные."""
    (tmp_path / ".claude" / "hooks").mkdir(parents=True)
    (tmp_path / "runtime").mkdir()
    (tmp_path / "state" / "secrets").mkdir(parents=True)
    shutil.copy(REPO / ".claude" / "hooks" / "guard.py", tmp_path / ".claude" / "hooks" / "guard.py")
    shutil.copy(REPO / "runtime" / "policy.yaml", tmp_path / "runtime" / "policy.yaml")
    # маскировка причин в журнале копии — тем же модулем, что и в проекте
    shutil.copy(REPO / "runtime" / "redact.py", tmp_path / "runtime" / "redact.py")
    (tmp_path / "runtime" / "__init__.py").write_text("", encoding="utf-8")
    return tmp_path / ".claude" / "hooks" / "guard.py"
