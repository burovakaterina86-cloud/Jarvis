"""Второй аккаунт Claude: лимит первого кончился → ход повторяется на втором, чат остаётся на нём до сброса первого."""
import asyncio
import json

import pytest

from runtime import claude2_bridge, claude_bridge, worker
from tests.test_router_codex import FAKE_CLAUDE, calls, router, submit  # noqa: F401  (router — фикстура)

PROMPT = "сделай комплект про ИИ"


def setup_second(router, scenario="ok"):
    folder = router.tmp / "second-account"
    folder.mkdir(exist_ok=True)
    router.env = {**router.env, "JARVIS_CLAUDE2_DIR": str(folder), "FAKE_CLAUDE_SCENARIO": "rate_limit",
                  "FAKE_CLAUDE2_SCENARIO": scenario}
    return folder


async def ask(router, text=PROMPT, chat=1):
    from runtime import task_router
    return await submit(router, task_router.Job(prompt=text, task=text[:30]), chat)


async def test_limit_on_first_account_is_answered_by_the_second(router):
    folder = setup_second(router)
    res = await ask(router)
    assert res.status == "ok" and "второго аккаунта Claude" in res.text
    rows = calls(router, "claude")
    assert len(rows) == 2 and rows[0]["config_dir"] is None and rows[1]["config_dir"] == str(folder)
    assert rows[1]["stdin_len"] > len(PROMPT)                   # второй получил запрос со сводкой, а не пустоту
    assert worker.current("1")["runtime"] == "claude2"          # чат остаётся на втором до сброса первого


async def test_next_messages_go_straight_to_the_second_account_then_back(router):
    folder = setup_second(router)
    await ask(router)
    router.env = {**router.env, "FAKE_CLAUDE_SCENARIO": "ok"}
    before = len(calls(router, "claude"))
    res = await ask(router, "а теперь пост")
    after = calls(router, "claude")
    assert res.status == "ok" and len(after) == before + 1 and after[-1]["config_dir"] == str(folder)
    router.clock_.t += 6 * 3600                                  # первый аккаунт сбросил лимит
    res = await ask(router, "ещё задача")
    last = calls(router, "claude")[-1]
    assert res.switched_back is True and last["config_dir"] is None


async def test_both_accounts_limited_falls_back_to_the_codex_offer(router):
    setup_second(router, scenario="rate_limit")
    res = await ask(router)
    assert res.status == "rate_limited" and res.switch_offer["prompt"] == PROMPT
    assert worker.current("1")["runtime"] == "claude"            # на втором аккаунте не застреваем


async def test_second_account_not_logged_in_keeps_the_old_scheme(router):
    setup_second(router, scenario="auth")
    res = await ask(router)
    assert res.status == "rate_limited" and res.switch_offer is not None
    assert worker.current("1")["runtime"] == "claude"


async def test_without_second_account_nothing_changes(router):
    router.env = {**router.env, "FAKE_CLAUDE_SCENARIO": "rate_limit"}
    res = await ask(router)
    assert res.status == "rate_limited" and len(calls(router, "claude")) == 1


async def test_forced_codex_job_is_not_redirected_to_second_account(router):
    from runtime import task_router
    setup_second(router)
    job = task_router.Job(prompt=PROMPT, task="x", runtime="codex")
    res = await submit(router, job)
    assert res.runtime == "codex" and calls(router, "claude") == []


def test_second_account_needs_an_existing_folder(tmp_path):
    assert not claude2_bridge.available({}) and not claude2_bridge.available({"JARVIS_CLAUDE2_DIR": str(tmp_path / "no")})
    assert claude2_bridge.available({"JARVIS_CLAUDE2_DIR": str(tmp_path)})


def test_second_account_folder_is_not_inherited_from_the_parent_environment(tmp_path):
    env = claude_bridge.build_env({"PATH": "x", "CLAUDE_CONFIG_DIR": "C:/parent", "JARVIS_CLAUDE2_DIR": str(tmp_path)})
    assert "CLAUDE_CONFIG_DIR" not in env           # папку второго аккаунта выставляет только claude2_bridge


async def test_limits_of_both_accounts_are_kept_apart(tmp_path):
    worker.save_limits("claude", {"status": "rejected", "resets_at": 2_000_000_000})
    worker.save_limits("claude2", {"status": "allowed", "resets_at": None})
    text = worker.describe_limits(now=1_000_000_000)
    assert "У Claude лимит закончился" in text and "Второй аккаунт Claude: с лимитом всё хорошо" in text
    assert json.loads(json.dumps(worker.limits())).keys() >= {"claude", "claude2"}
    await asyncio.sleep(0)


async def test_unlogged_second_account_message_tells_what_to_do(tmp_path):
    folder = tmp_path / "acc"
    folder.mkdir()
    assert str(folder) in claude2_bridge.auth_text(folder) and "/login" in claude2_bridge.auth_text(folder)
    res = await claude2_bridge.run_turn("x", env={})
    assert res.status == "error" and res.error == "claude2_not_configured" and res.runtime == "claude2"
    _ = pytest
