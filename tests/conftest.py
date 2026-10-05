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
    REPO / "state" / "approvals.jsonl",
    REPO / "state" / "sessions.json",
    REPO / "state" / "session_activity.json",   # время её последнего хода (P3.1)
    # эпизоды пишет и мост (task_router.EPISODES_DIR): тест с настоящим роутером подменяет путь
    REPO / "memory" / "episodes" / f"{date.today():%Y-%m}.jsonl",
)


def _sizes():
    return {p: (p.stat().st_size if p.exists() else None) for p in LIVE_JOURNALS}


@pytest.fixture(scope="session", autouse=True)
def live_journals_untouched():
    before = _sizes()
    yield
    changed = [str(p.relative_to(REPO)) for p, size in _sizes().items() if size != before[p]]
    assert not changed, (
        f"тесты дописали в боевые журналы: {changed}. Подпроцессный Guard запускай через "
        "фикстуру guard_copy (копия во временном корне). Если в это время работал бот — "
        "запись могла быть его, перезапусти тесты при остановленном боте.")


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
