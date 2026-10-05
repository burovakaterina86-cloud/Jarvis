"""Мост к Claude Code — шов: run_turn с фейковым исполняемым файлом."""
import asyncio
import json
import os
import sys
from pathlib import Path

import pytest

from runtime import claude_bridge, events

FAKE = [sys.executable, str(Path(__file__).parent / "fake_claude" / "fake_claude.py")]


@pytest.fixture
def fake(tmp_path, monkeypatch):
    log = tmp_path / "calls.jsonl"
    monkeypatch.setattr(events, "EVENTS_PATH", tmp_path / "events.jsonl")
    env = {"PATH": "", "SYSTEMROOT": "C:\\Windows", "FAKE_CLAUDE_LOG": str(log),
           "FAKE_CLAUDE_SCENARIO": "ok"}
    env = {**os.environ, **env}

    class F:
        tmp = tmp_path
        base_env = env

        def calls(self):
            if not log.exists():
                return []
            rows = [json.loads(x) for x in log.read_text(encoding="utf-8").splitlines()]
            return [r for r in rows if "argv" in r]

        def ends(self):
            if not log.exists():
                return []
            rows = [json.loads(x) for x in log.read_text(encoding="utf-8").splitlines()]
            return [r for r in rows if "t_end" in r]

        async def run(self, prompt="привет", session_id=None, scenario="ok", **kw):
            env["FAKE_CLAUDE_SCENARIO"] = scenario
            kw.setdefault("env", env)
            return await claude_bridge.run_turn(prompt, session_id, kw.pop("on_event", None),
                                                claude_cmd=FAKE, **kw)
    return F()


async def test_turn_parses_text_session_and_cost(fake):
    seen = []
    res = await fake.run(on_event=seen.append)
    assert res.status == "ok"
    assert res.text == "Привет, Катерина!"
    assert res.session_id == "sess-new-0001"
    assert res.cost_usd == pytest.approx(0.0123)
    assert res.new_session is True
    assert res.error is None
    assert [e["type"] for e in seen] == ["system", "assistant", "user", "assistant", "result"]


async def test_second_turn_resumes_session(fake):
    first = await fake.run()
    res = await fake.run(session_id=first.session_id)
    argv = fake.calls()[-1]["argv"]
    assert argv[argv.index("--resume") + 1] == "sess-new-0001"
    assert "--resume" not in fake.calls()[0]["argv"]
    assert res.status == "ok" and res.new_session is False


async def test_resume_failure_retries_once_without_resume(fake):
    res = await fake.run(session_id="dead-session", scenario="resume_fail")
    calls = fake.calls()
    assert len(calls) == 2
    assert "--resume" in calls[0]["argv"] and "--resume" not in calls[1]["argv"]
    assert res.status == "ok"
    assert res.new_session is True
    assert res.session_id == "sess-new-0001"


def _events(fake):
    p = fake.tmp / "events.jsonl"
    return [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines()]


async def test_events_written_with_required_fields(fake):
    await fake.run(task="t-1")
    evs = _events(fake)
    types = [e["type"] for e in evs]
    for t in ("tool_use", "tool_result", "assistant_message", "result"):
        assert t in types
    for e in evs:
        assert {"ts", "type", "session", "agent", "task", "status", "progress"} <= set(e)
        assert e["task"] == "t-1"
    res = [e for e in evs if e["type"] == "result"][0]
    assert res["status"] == "done" and res["cost"] == pytest.approx(0.0123)
    assert res["session"] == "sess-new-0001"


async def test_rate_limit_gives_human_status(fake):
    res = await fake.run(scenario="rate_limit")
    assert res.status == "rate_limited"
    assert "лимит" in res.text.lower()
    assert any(e["type"] == "error" for e in _events(fake))


async def test_auth_failure_gives_human_status(fake):
    res = await fake.run(scenario="auth")
    assert res.status == "auth_required"
    assert "войти" in res.text.lower()


async def test_context_overflow_starts_new_session_with_summary(fake):
    res = await fake.run(prompt="сделай отчёт по продажам", session_id="old-sess", scenario="overflow")
    calls = fake.calls()
    assert len(calls) == 2 and "--resume" not in calls[1]["argv"]
    assert "сделай отчёт по продажам" in calls[1]["stdin_tail"]
    assert calls[1]["stdin_len"] > len("сделай отчёт по продажам")
    assert res.status == "ok" and res.new_session is True


async def test_command_line_and_child_env_are_safe(fake):
    env = dict(os.environ)
    env.update({"FAKE_CLAUDE_LOG": str(fake.tmp / "calls.jsonl"), "ANTHROPIC_API_KEY": "x",
                "ANTHROPIC_AUTH_TOKEN": "x", "CLAUDECODE": "1", "CLAUDE_CODE_ENTRYPOINT": "cli",
                "TELEGRAM_BOT_TOKEN": "x", "TELEGRAM_OWNER_ID": "1",
                "JARVIS_PURCHASE_LIMIT_RUB": "5000", "JARVIS_DAILY_RUN_BUDGET": "40"})
    await fake.run(env=env)
    call = fake.calls()[-1]
    argv = call["argv"]
    assert argv[argv.index("--permission-mode") + 1] == "dontAsk"
    joined = " ".join(argv)
    assert "bypass" not in joined.lower() and "dangerously" not in joined.lower()
    assert "-p" in argv and argv[argv.index("--output-format") + 1] == "stream-json"
    assert argv[argv.index("--settings") + 1].replace("\\", "/").endswith("runtime/jarvis-settings.json")
    assert argv[argv.index("--max-turns") + 1] == "60"
    for bad in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "CLAUDECODE", "CLAUDE_CODE_ENTRYPOINT",
                "TELEGRAM_BOT_TOKEN", "TELEGRAM_OWNER_ID"):
        assert bad not in call["env_keys"]
    assert call["env_jarvis"]["JARVIS_PURCHASE_LIMIT_RUB"] == "5000"
    assert "привет" not in joined  # промпт не в командной строке


async def test_large_prompt_goes_through_stdin(fake):
    prompt = "я" * 30000 + "конец"  # > 40 KB в UTF-8
    assert len(prompt.encode("utf-8")) > 40 * 1024
    res = await fake.run(prompt=prompt)
    call = fake.calls()[-1]
    assert res.status == "ok"
    assert call["stdin_len"] == len(prompt) and call["stdin_tail"].endswith("конец")


async def test_stop_kills_running_turn_fast(fake):
    import time
    task = asyncio.create_task(fake.run(scenario="sleep", run_id="r-stop"))
    for _ in range(100):
        await asyncio.sleep(0.05)
        if (fake.tmp / "calls.jsonl").exists():
            break
    t0 = time.monotonic()
    assert claude_bridge.stop("r-stop") is True
    res = await asyncio.wait_for(task, 3)
    assert time.monotonic() - t0 < 3
    assert res.status == "stopped"
    assert claude_bridge.stop("r-stop") is False


def test_sessions_get_set_reset_persist(tmp_path, monkeypatch):
    from runtime import sessions
    path = tmp_path / "state" / "sessions.json"
    monkeypatch.setattr(sessions, "SESSIONS_PATH", path)
    assert sessions.get(42) is None
    sessions.set(42, "sid-a")
    sessions.set("7", "sid-b")
    assert json.loads(path.read_text(encoding="utf-8")) == {"42": "sid-a", "7": "sid-b"}
    assert sessions.get("42") == "sid-a"
    sessions.reset(42)
    assert sessions.get(42) is None and sessions.get(7) == "sid-b"
    assert not list(path.parent.glob("*.tmp"))


def _router(fake, monkeypatch, **kw):
    from runtime import sessions, task_router
    monkeypatch.setattr(sessions, "SESSIONS_PATH", fake.tmp / "sessions.json")
    monkeypatch.setattr(task_router, "EPISODES_DIR", fake.tmp / "episodes")
    env = {**fake.base_env, "FAKE_CLAUDE_SCENARIO": "ok", "FAKE_CLAUDE_DELAY": "0.4"}
    kw.setdefault("git_status", lambda: set())
    return task_router.TaskRouter(env=env, claude_cmd=FAKE, budget_path=fake.tmp / "budget.json", **kw)


async def test_queue_same_chat_is_sequential_and_keeps_session(fake, monkeypatch):
    from runtime import sessions, task_router
    router = _router(fake, monkeypatch)
    j1, j2 = task_router.Job(prompt="первая"), task_router.Job(prompt="вторая")
    assert router.submit(1, j1) == 0
    assert router.submit(1, j2) == 1
    r1, r2 = await asyncio.wait_for(asyncio.gather(j1.result, j2.result), 20)
    assert r1.status == r2.status == "ok"
    starts, ends = fake.calls(), fake.ends()
    assert [c["stdin_tail"] for c in starts] == ["первая", "вторая"]
    assert starts[1]["t_start"] >= ends[0]["t_end"]
    assert "--resume" in starts[1]["argv"]
    assert sessions.get(1) == "sess-new-0001"


async def test_browser_jobs_in_different_chats_are_sequential(fake, monkeypatch):
    from runtime import task_router
    router = _router(fake, monkeypatch)
    j1 = task_router.Job(prompt="браузер-1", uses_browser=True)
    j2 = task_router.Job(prompt="браузер-2", uses_browser=True)
    router.submit(10, j1)
    router.submit(20, j2)
    await asyncio.wait_for(asyncio.gather(j1.result, j2.result), 20)
    starts = sorted(fake.calls(), key=lambda c: c["t_start"])
    ends = sorted(fake.ends(), key=lambda c: c["t_end"])
    assert starts[1]["t_start"] >= ends[0]["t_end"]


async def test_daily_run_budget_blocks_extra_runs(fake, monkeypatch):
    from runtime import task_router
    router = _router(fake, monkeypatch, budget=1)
    j1, j2 = task_router.Job(prompt="раз"), task_router.Job(prompt="два")
    router.submit(5, j1)
    router.submit(5, j2)
    r1, r2 = await asyncio.wait_for(asyncio.gather(j1.result, j2.result), 20)
    assert r1.status == "ok"
    assert r2.status == "error" and r2.error == "daily_budget_exceeded"
    assert len(fake.calls()) == 1


async def test_expired_login_in_result_gives_auth_status(fake):
    res = await fake.run(scenario="auth_result")
    assert res.status == "auth_required"
    assert "войти" in res.text.lower()


async def test_no_retry_after_tools_on_broken_resume(fake):
    res = await fake.run(session_id="dead-session", scenario="resume_fail_after_tools")
    assert len(fake.calls()) == 1  # ход уже действовал — повторять нельзя
    assert res.status == "error"
    assert "повтор" in res.text.lower() or "повтор" in (res.error or "").lower()


async def test_no_retry_after_tools_on_context_overflow(fake):
    res = await fake.run(session_id="live-session", scenario="overflow_after_tools")
    assert len(fake.calls()) == 1
    assert res.status == "error"
    assert res.session_id == "live-session"


async def test_context_phrase_in_answer_does_not_reset_session(fake):
    res = await fake.run(session_id="live-session", scenario="context_in_text")
    assert len(fake.calls()) == 1
    assert res.status == "ok" and res.new_session is False


async def test_parser_survives_garbage_lines(fake, monkeypatch):
    monkeypatch.setattr(claude_bridge, "STREAM_LIMIT", 64 * 1024)
    seen = []
    res = await fake.run(scenario="garbage", on_event=seen.append)
    assert res.status == "ok" and res.text == "Привет, Катерина!"
    assert all(isinstance(e, dict) for e in seen)


async def test_stop_kills_child_process_too(fake):
    import subprocess as sp
    pid_file = fake.tmp / "child.pid"
    env = {**fake.base_env, "FAKE_CLAUDE_CHILD_PID": str(pid_file),
           "FAKE_CLAUDE_SCENARIO": "sleep_child"}
    task = asyncio.create_task(fake.run(scenario="sleep_child", run_id="r-tree", env=env))
    for _ in range(200):
        await asyncio.sleep(0.05)
        if pid_file.exists() and pid_file.read_text(encoding="utf-8").strip():
            break
    child_pid = int(pid_file.read_text(encoding="utf-8").strip())
    assert claude_bridge.stop("r-tree") is True
    res = await asyncio.wait_for(task, 5)
    assert res.status == "stopped"
    await asyncio.sleep(0.5)
    # Байты, а не text=True: когда процесса нет, tasklist пишет локализованную строку
    # в кодировке консоли (cp866), и чтение как UTF-8 роняло поток — stdout становился None.
    raw = sp.run(["tasklist", "/NH", "/FO", "CSV", "/FI", f"PID eq {child_pid}"],
                 capture_output=True).stdout
    listing = raw.decode("ascii", "replace")
    assert f'"{child_pid}"' not in listing


async def test_stopped_run_id_is_forgotten_after_turn(fake):
    task = asyncio.create_task(fake.run(scenario="sleep", run_id="r-clean"))
    for _ in range(100):
        await asyncio.sleep(0.05)
        if fake.calls():
            break
    claude_bridge.stop("r-clean")
    await asyncio.wait_for(task, 5)
    assert "r-clean" not in claude_bridge._stopped


async def test_failed_turn_does_not_spend_daily_budget(fake, monkeypatch):
    from runtime import task_router
    router = _router(fake, monkeypatch, budget=1)
    router.env = {**router.env, "FAKE_CLAUDE_SCENARIO": "rate_limit"}
    j1, j2 = task_router.Job(prompt="раз"), task_router.Job(prompt="два")
    router.submit(9, j1)
    router.submit(9, j2)
    r1, r2 = await asyncio.wait_for(asyncio.gather(j1.result, j2.result), 20)
    assert r1.status == r2.status == "rate_limited"  # бюджет не списан неуспешным ходом
    assert len(fake.calls()) == 2


async def test_host_claude_session_vars_are_stripped(fake):
    env = {**fake.base_env, "ANTHROPIC_BASE_URL": "http://host", "ANTHROPIC_API_KEY": "x",
           "CLAUDE_CODE_MESSAGING_TOKEN": "x", "CLAUDE_CODE_MESSAGING_SOCKET": "x",
           "CLAUDE_CODE_SDK_HAS_HOST_AUTH_REFRESH": "1", "CLAUDE_CODE_OAUTH_SCOPES": "x",
           "CLAUDE_CODE_SESSION_ID": "x", "CLAUDECODE": "1", "CLAUDE_AGENT_SDK_VERSION": "1",
           "CLAUDE_CODE_GIT_BASH_PATH": "C:\bash.exe", "TELEGRAM_BOT_TOKEN": "x",
           "FAKE_CLAUDE_SCENARIO": "ok"}
    await fake.run(env=env)
    keys = fake.calls()[-1]["env_keys"]
    left = [k for k in keys if k.upper().startswith(("CLAUDE", "ANTHROPIC", "TELEGRAM"))]
    assert left == ["CLAUDE_CODE_GIT_BASH_PATH"]


# ---------- таймаут задачи (P1.3) и изолированный контекст (P1.4), аудит 2026-10-05 ----------

async def test_job_timeout_kills_turn_and_queue_moves_on(fake, monkeypatch):
    import time
    from runtime import task_router
    router = _router(fake, monkeypatch)
    router.env = {**router.env, "FAKE_CLAUDE_SCENARIO": "sleep"}
    slow = task_router.Job(prompt="долгая", timeout_sec=1)
    t0 = time.monotonic()
    router.submit(3, slow)
    res = await asyncio.wait_for(slow.result, 15)
    assert time.monotonic() - t0 < 10
    assert res.status == "timeout" and res.error == "timeout"
    assert "1 с" in res.text or "мин" in res.text
    router.env = {**router.env, "FAKE_CLAUDE_SCENARIO": "ok"}
    nxt = task_router.Job(prompt="следующая")
    router.submit(3, nxt)
    assert (await asyncio.wait_for(nxt.result, 15)).status == "ok"
    rows = [json.loads(x) for x in (fake.tmp / "events.jsonl").read_text(encoding="utf-8").splitlines()]
    assert any(r["type"] == "error" and r.get("subtype") == "timeout" for r in rows)


async def test_timed_out_turn_still_spends_daily_budget(fake, monkeypatch):
    from runtime import task_router
    router = _router(fake, monkeypatch, budget=5)
    router.env = {**router.env, "FAKE_CLAUDE_SCENARIO": "sleep"}
    job = task_router.Job(prompt="долгая", timeout_sec=1)
    router.submit(4, job)
    await asyncio.wait_for(job.result, 15)
    data = json.loads((fake.tmp / "budget.json").read_text(encoding="utf-8"))
    assert data["count"] == 1


def test_default_timeout_from_env(monkeypatch):
    from runtime import task_router
    monkeypatch.setenv("JARVIS_TASK_TIMEOUT_SEC", "120")
    assert task_router.TaskRouter().default_timeout == 120
    monkeypatch.setenv("JARVIS_TASK_TIMEOUT_SEC", "мусор")
    assert task_router.TaskRouter().default_timeout == task_router.DEFAULT_TASK_TIMEOUT_SEC
    monkeypatch.delenv("JARVIS_TASK_TIMEOUT_SEC")
    assert task_router.TaskRouter().default_timeout == 2700


async def test_isolated_job_neither_resumes_nor_touches_chat_session(fake, monkeypatch):
    from runtime import sessions, task_router
    router = _router(fake, monkeypatch)
    sessions.set(7, "sid-chat")
    job = task_router.Job(prompt="по расписанию", context="isolated")
    router.submit(7, job)
    res = await asyncio.wait_for(job.result, 15)
    assert res.status == "ok"
    assert "--resume" not in fake.calls()[0]["argv"]
    assert sessions.get(7) == "sid-chat"
    chat = task_router.Job(prompt="она пишет")
    router.submit(7, chat)
    await asyncio.wait_for(chat.result, 15)
    argv = fake.calls()[1]["argv"]
    assert argv[argv.index("--resume") + 1] == "sid-chat"


def test_unknown_context_is_rejected():
    from runtime import task_router
    with pytest.raises(ValueError):
        task_router.Job(prompt="x", context="fork-всё")



# ---------- журнал: task_id, сводки, итог задачи, эпизод (P1.1, P1.2), аудит 2026-10-05 ----------

def _events(fake):
    return [json.loads(x) for x in (fake.tmp / "events.jsonl").read_text(encoding="utf-8").splitlines()]


async def _ledger_job(fake, monkeypatch, git_after=frozenset({"new.txt"})):
    from runtime import task_router
    states = iter([set(), set(git_after)])
    router = _router(fake, monkeypatch, git_status=lambda: next(states))
    router.env = {**router.env, "FAKE_CLAUDE_SCENARIO": "ledger"}
    job = task_router.Job(prompt="сделай пост", task="пост")
    router.submit(9, job)
    res = await asyncio.wait_for(job.result, 15)
    return job, res


async def test_every_event_of_a_task_carries_its_task_id(fake, monkeypatch):
    job, res = await _ledger_job(fake, monkeypatch)
    assert res.status == "ok" and job.task_id
    rows = _events(fake)
    assert rows and all(r.get("task_id") == job.task_id for r in rows)
    assert {"user_message", "tool_use", "result", "task_done"} <= {r["type"] for r in rows}
    assert fake.calls()[0]["env_jarvis"]["JARVIS_TASK_ID"] == job.task_id


async def test_tool_use_summaries_are_safe_and_name_the_subagent(fake, monkeypatch):
    await _ledger_job(fake, monkeypatch)
    uses = [r for r in _events(fake) if r["type"] == "tool_use"]
    by_tool = {r["tool"]: r for r in uses}
    assert "topSecret123" not in json.dumps(uses, ensure_ascii=False)
    assert by_tool["Write"]["summary"] == "essa-ai/content/x/post.md"
    assert "черновик поста" not in json.dumps(uses, ensure_ascii=False)
    assert by_tool["WebFetch"]["summary"] == "stat.ru" and by_tool["WebFetch"]["agent"] == "researcher"
    assert by_tool["Read"]["agent"] == "researcher"
    assert by_tool["Agent"]["agent"] == "jarvis" and "researcher" in by_tool["Agent"]["summary"]


async def test_task_done_says_what_happened(fake, monkeypatch):
    job, _ = await _ledger_job(fake, monkeypatch)
    done = [r for r in _events(fake) if r["type"] == "task_done"]
    assert len(done) == 1
    d = done[0]
    assert d["status"] == "done" and d["result_status"] == "ok"
    assert d["tools"] == 6 and d["attempts"] == 1 and d["context"] == "chat"
    assert d["files_changed"] == ["essa-ai/content/x/post.md", "memory/a.md", "new.txt"]
    assert d["cost"] == 0.02 and isinstance(d["duration"], float)


async def test_episode_line_is_written_by_the_bridge(fake, monkeypatch):
    job, _ = await _ledger_job(fake, monkeypatch)
    files = list((fake.tmp / "episodes").glob("*.jsonl"))
    assert len(files) == 1
    ep = json.loads(files[0].read_text(encoding="utf-8").splitlines()[-1])
    assert ep["task_id"] == job.task_id and ep["trigger"] == "turn_end"
    assert ep["status"] == "ok" and ep["request"] == "сделай пост"
    assert ep["result"].startswith("Готово") and "memory/a.md" in ep["files"]


async def test_no_episode_when_nothing_ran(fake, monkeypatch):
    from runtime import task_router
    router = _router(fake, monkeypatch, budget=0)
    job = task_router.Job(prompt="раз")
    router.submit(11, job)
    res = await asyncio.wait_for(job.result, 15)
    assert res.error == "daily_budget_exceeded"
    assert not (fake.tmp / "episodes").exists()
    assert [r["task_id"] for r in _events(fake) if r["type"] == "error"] == [job.task_id]


async def test_retry_without_resume_counts_two_attempts(fake):
    res = await fake.run(session_id="old-sid", scenario="resume_fail")
    assert res.attempts == 2


def test_emit_masks_secrets_in_any_field(tmp_path, monkeypatch):
    monkeypatch.setattr(events, "EVENTS_PATH", tmp_path / "e.jsonl")
    events.emit("error", error="Bearer abcdefghijk123", nested={"x": "token=zzz999"})
    line = (tmp_path / "e.jsonl").read_text(encoding="utf-8")
    assert "abcdefghijk123" not in line and "zzz999" not in line


def test_task_done_is_a_known_event_type():
    assert "task_done" in events.TYPES
