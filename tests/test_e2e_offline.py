"""Сквозной офлайн-тест: Telegram-апдейт → task_router → мост → фейковый claude,
который зовёт настоящий Guard → Approvals API → нажатие кнопки → ответ в чат.

Реальный `claude` не запускается: вместо него скрипт, печатающий stream-json и
вызывающий `.claude/hooks/guard.py` как PreToolUse-хук (подпроцесс, JSON на stdin).
Guard в тесте работает в песочнице: его файл и `runtime/policy.yaml` копируются в
tmp_path, поэтому корень (`parents[2]`) — песочница, а не настоящий проект.
"""
from __future__ import annotations

import asyncio
import json
import os
import shutil
import sys
from pathlib import Path

import pytest

from runtime import claude_bridge, events
from runtime.approvals import ApprovalsServer
from runtime import task_router
from runtime.task_router import Job, TaskRouter
from tests import codescan
from tests.test_telegram import (OWNER, FakeBot, FakeCallback, FakeContext, FakeIncoming,
                                 FakeSessions, FakeUpdate, make_gateway)

ROOT = Path(__file__).resolve().parents[1]

# Отправка ответа в браузере: policy.yaml → EXTERNAL / send_message / ask.
EXTERNAL_TOOL = {"tool_name": "mcp__playwright__browser_click",
                 "tool_input": {"element": "кнопка Отправить", "ref": "e42"}}

FAKE_CLAUDE = '''
"""Фейковый claude: один вызов инструмента через настоящий Guard, потом ответ."""
import json, os, subprocess, sys

root = os.environ["E2E_ROOT"]
guard = os.path.join(root, ".claude", "hooks", "guard.py")
plan = json.loads(os.environ["E2E_TOOL"])
marker = os.environ["E2E_MARKER"]
sid = "e2e-session-1"


def out(obj):
    sys.stdout.buffer.write((json.dumps(obj, ensure_ascii=False) + "\\n").encode("utf-8"))
    sys.stdout.flush()


sys.stdin.buffer.read()
out({"type": "system", "subtype": "init", "session_id": sid})
hook_event = {"hook_event_name": "PreToolUse", "session_id": sid, "cwd": root,
              "tool_name": plan["tool_name"], "tool_input": plan["tool_input"]}
done = subprocess.run([sys.executable, guard],
                      input=json.dumps(hook_event, ensure_ascii=False).encode("utf-8"),
                      stdout=subprocess.PIPE, stderr=subprocess.PIPE)
out({"type": "assistant", "session_id": sid, "message": {"content": [
    {"type": "tool_use", "id": "t1", "name": plan["tool_name"], "input": plan["tool_input"]}]}})
if done.returncode == 0:
    with open(marker, "w", encoding="utf-8") as fh:
        fh.write("выполнено")
    out({"type": "user", "session_id": sid, "message": {"content": [
        {"type": "tool_result", "tool_use_id": "t1", "content": "ok"}]}})
    text = "Готово: ответ отправлен."
else:
    reason = done.stderr.decode("utf-8", "replace").strip()
    out({"type": "user", "session_id": sid, "message": {"content": [
        {"type": "tool_result", "tool_use_id": "t1", "is_error": True, "content": reason}]}})
    text = "Действие не выполнено. " + reason
out({"type": "assistant", "session_id": sid,
     "message": {"content": [{"type": "text", "text": text}]}})
out({"type": "result", "subtype": "success", "is_error": False, "session_id": sid,
     "result": text, "total_cost_usd": 0.001, "duration_ms": 10})
'''


class Sandbox:
    """Песочница с копией Guard и настоящей политикой, сервером Approvals и шлюзом."""

    def __init__(self, root: Path, server: ApprovalsServer, gateway, bot, router, marker: Path):
        self.root, self.server, self.gateway = root, server, gateway
        self.bot, self.router, self.marker = bot, router, marker

    @property
    def done(self) -> bool:
        return self.marker.exists()

    def events(self) -> list[dict]:
        path = self.root / "state" / "events.jsonl"
        if not path.exists():
            return []
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]

    def approvals_log(self) -> list[dict]:
        path = self.root / "state" / "approvals.jsonl"
        if not path.exists():
            return []
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]

    def button(self, label: str) -> str:
        """callback_data кнопки из последнего сообщения с клавиатурой."""
        for msg in reversed(self.bot.sent):
            markup = msg.get("reply_markup")
            for row in getattr(markup, "inline_keyboard", ()) or ():
                for btn in row:
                    if btn.text == label:
                        return btn.callback_data
        raise AssertionError(f"кнопки «{label}» нет ни в одном сообщении бота")


@pytest.fixture
async def sandbox(tmp_path, monkeypatch):
    root = tmp_path / "jarvis"
    (root / ".claude" / "hooks").mkdir(parents=True)
    (root / "runtime").mkdir()
    (root / "state").mkdir()
    shutil.copy2(ROOT / ".claude" / "hooks" / "guard.py", root / ".claude" / "hooks" / "guard.py")
    shutil.copy2(ROOT / "runtime" / "policy.yaml", root / "runtime" / "policy.yaml")
    script = root / "fake_claude_guarded.py"
    script.write_text(FAKE_CLAUDE, encoding="utf-8")
    marker = root / "state" / "action-done.txt"

    monkeypatch.setattr(events, "EVENTS_PATH", root / "state" / "events.jsonl")
    monkeypatch.setattr(task_router, "EPISODES_DIR", root / "memory" / "episodes")
    server = ApprovalsServer(timeout=20.0)
    await server.start(root)

    env = dict(os.environ)
    env.update({"E2E_ROOT": str(root), "E2E_MARKER": str(marker),
                "E2E_TOOL": json.dumps(EXTERNAL_TOOL, ensure_ascii=False)})
    router = TaskRouter(budget_path=root / "state" / "run_budget.json", env=env,
                        claude_cmd=[sys.executable, str(script)], sessions=FakeSessions(),
                        git_status=lambda: set())
    bot = FakeBot()
    gateway = make_gateway(root, router=router, sessions=router.sessions, approvals=server)
    gateway.attach(bot)
    server.on_request(gateway.on_approval_request)
    try:
        yield Sandbox(root, server, gateway, bot, router, marker)
    finally:
        await server.stop()


async def _press(sandbox, label: str) -> None:
    """Ждёт кнопку подтверждения в фейковом боте и нажимает её."""
    async with asyncio.timeout(30):
        while not sandbox.server.pending:
            await asyncio.sleep(0.02)
        while True:
            try:
                data = sandbox.button(label)
                break
            except AssertionError:
                await asyncio.sleep(0.02)
    query = FakeCallback(data)
    await sandbox.gateway.on_callback(FakeUpdate(OWNER, callback_query=query),
                                      FakeContext(bot=sandbox.bot))


async def _turn(sandbox, label: str, text: str = "Отправь ответ на комментарий") -> None:
    ctx = FakeContext(bot=sandbox.bot)
    update = FakeUpdate(OWNER, message=FakeIncoming(text=text))
    turn = asyncio.create_task(sandbox.gateway.on_message(update, ctx))
    await _press(sandbox, label)
    async with asyncio.timeout(60):
        await turn


# ------------------------------------------------------------------ сквозной путь

async def test_confirm_lets_external_action_through_and_answer_reaches_chat(sandbox):
    await _turn(sandbox, "Подтвердить")

    assert sandbox.done, "после «Подтвердить» действие должно выполниться"
    assert any("ответ отправлен" in m["text"] for m in sandbox.bot.sent)
    kinds = [e["type"] for e in sandbox.events()]
    assert "user_message" in kinds and "tool_use" in kinds and "result" in kinds
    assert "blocked" not in kinds
    decisions = [e for e in sandbox.approvals_log() if e["type"] == "decision"]
    assert [d["decision"] for d in decisions] == ["allow"]
    assert sandbox.router.sessions.get(OWNER) == "e2e-session-1"


async def test_reject_blocks_the_action_and_tells_the_owner(sandbox):
    await _turn(sandbox, "Отклонить")

    assert not sandbox.done, "после «Отклонить» действие не должно выполниться"
    answers = " ".join(m["text"] for m in sandbox.bot.sent)
    assert "не выполнено" in answers and "Guard" in answers
    blocked = [e for e in sandbox.events() if e["type"] == "blocked"]
    assert blocked and blocked[-1]["tool"] == EXTERNAL_TOOL["tool_name"]
    decisions = [e for e in sandbox.approvals_log() if e["type"] == "decision"]
    assert [d["decision"] for d in decisions] == ["deny"]


async def test_guard_denies_secret_read_without_asking_the_owner(sandbox):
    """DENY не доходит до Approvals: кнопок нет, ход возвращает отказ."""
    plan = {"tool_name": "Read", "tool_input": {"file_path": ".env"}}
    sandbox.router.env["E2E_TOOL"] = json.dumps(plan, ensure_ascii=False)

    job = Job(prompt="прочитай .env", task="секрет")
    sandbox.router.submit(OWNER, job)
    async with asyncio.timeout(60):
        result = await job.result

    assert result.status == "ok"  # ход прошёл, но инструмент отклонён
    assert not sandbox.done
    assert "Guard" in result.text and "не выполнено" in result.text
    assert sandbox.server.pending == []
    assert not [e for e in sandbox.approvals_log() if e["type"] == "request"]


# ------------------------------------------------------------------ статические проверки

def test_no_permission_bypass_anywhere_in_code():
    assert codescan.bypass_hits() == []


def test_bridge_starts_claude_without_bypass_and_with_jarvis_settings():
    args = claude_bridge.build_args("sid-1")
    assert "--permission-mode" in args and args[args.index("--permission-mode") + 1] == "dontAsk"
    assert str(claude_bridge.SETTINGS_FILE) in args
    assert not any("dangerous" in a or "bypass" in a.lower() for a in args)


def test_context_budget_script_is_green():
    sys.path.insert(0, str(ROOT / "scripts"))
    try:
        import check_context_size
    finally:
        sys.path.pop(0)
    assert check_context_size.check(ROOT) is True


DB_SERVERS = ("psycopg", "pymysql", "mysqlclient", "asyncpg", "sqlalchemy", "redis",
              "pymongo", "motor", "django", "flask", "fastapi", "uvicorn", "streamlit",
              "gradio", "dash", "sqlmodel", "tortoise")


def test_no_database_server_and_no_web_dashboard():
    """R28: состояние — только файлы, ни СУБД, ни веб-панели."""
    requirements = (ROOT / "requirements.txt").read_text(encoding="utf-8").lower()
    assert [name for name in DB_SERVERS if name in requirements] == []

    db_needles = ("import " + "sqlite3", "sqlalchemy", "psyco" + "pg2")
    for path in codescan.code_files(suffixes={".py"}):
        text = path.read_text(encoding="utf-8", errors="replace").lower()
        assert [n for n in db_needles if n in text] == [], path

    own = [p for p in ROOT.rglob("*.sqlite*")
           if not codescan.SKIP_DIRS & set(p.relative_to(ROOT).parts)]
    assert own == [] and list(ROOT.glob("*.mdb")) == []


def test_state_is_plain_files_and_approvals_listens_only_on_loopback(sandbox):
    """Единственный HTTP-слушатель — Approvals на петлевом адресе; состояние — файлы в state/."""
    assert {host for host, _ in sandbox.server.addresses} == {"127.0.0.1"}
    state = {p.suffix for p in (sandbox.root / "state").rglob("*") if p.is_file()}
    assert state <= {".port", ".token", ".jsonl", ".json", ".txt", ""}
