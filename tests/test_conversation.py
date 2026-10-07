"""Отдельный собеседник: строгие решения и независимость от исполнителя."""
import asyncio
import json

import pytest

from runtime import claude_bridge, conversation
from tests.test_telegram import OWNER, FakeContext, FakeIncoming, FakeRouter, FakeUpdate, make_gateway


def test_light_model_without_tools_or_browser():
    args = claude_bridge.build_args(None, conversation.OPTIONS)
    assert args[args.index("--model") + 1] == "haiku"
    assert args[args.index("--tools") + 1] == ""
    assert "--strict-mcp-config" in args and "--no-session-persistence" in args
    assert "--safe-mode" in args and "--system-prompt-file" in args


def test_account_is_independent_and_second_is_default_when_connected(monkeypatch):
    monkeypatch.setattr(conversation.claude2_bridge, "available", lambda env: True)
    assert conversation.account_for({}) == "claude2"
    assert conversation.account_for({"JARVIS_CONVERSATION_RUNTIME": "claude"}) == "claude"
    monkeypatch.setattr(conversation.claude2_bridge, "available", lambda env: False)
    assert conversation.account_for({}) == "claude"


@pytest.mark.parametrize("data", [None, {}, {"action": "dispatch", "reply": "да", "role": "unknown", "brief": "x"},
    {"action": "dispatch", "reply": "да", "role": "text", "brief": ""},
    {"action": "reply", "reply": "да", "role": "text", "brief": "x"}])
def test_invalid_decision_never_dispatches(data):
    result = claude_bridge.TurnResult("", None, False, None, "ok", structured=data)
    assert conversation.parse(result) is None


def test_history_is_chat_scoped_and_preserves_full_messages(tmp_path):
    original = "требование\n" * 1500
    conversation.remember(tmp_path, 1, original, "ответ")
    assert json.loads(conversation.history(tmp_path, 1))[0]["user"] == original
    assert json.loads(conversation.history(tmp_path, 2)) == []
    saved = json.loads((tmp_path / "state" / "conversation" / "1.jsonl").read_text(encoding="utf-8"))
    assert saved["user"] == original


async def test_conversation_does_not_wait_for_worker_or_consume_its_budget(tmp_path, monkeypatch):
    from runtime import task_router
    from tests.test_telegram import FakeSessions
    monkeypatch.setattr(task_router, "EPISODES_DIR", tmp_path / "episodes")
    class Bridge:
        @staticmethod
        async def run_turn(prompt, sid, on_event, **kwargs):
            assert sid is None
            assert kwargs["options"] is conversation.OPTIONS
            return claude_bridge.TurnResult("", "dialogue", False, None, "ok",
                structured={"action": "reply", "reply": "Я здесь.", "role": "", "brief": ""})
        @staticmethod
        def stop(run_id):
            return True
    router = task_router.TaskRouter(sessions=FakeSessions(), budget=0, budget_path=tmp_path / "budget.json")
    router.runtimes["claude"] = Bridge
    job = task_router.Job("длинный\n" * 100, task="собеседник", context="conversation", queue="conversation", options=conversation.OPTIONS, data_root=tmp_path)
    router.submit(1, job)
    result = await asyncio.wait_for(job.result, 1)
    assert conversation.parse(result)["reply"] == "Я здесь."
    assert not (tmp_path / "budget.json").exists()
    assert router.sessions.store == {}


async def test_question_finishes_while_actual_worker_is_blocked(tmp_path, monkeypatch):
    from runtime import task_router
    from tests.test_telegram import FakeSessions
    monkeypatch.setattr(task_router, "EPISODES_DIR", tmp_path / "episodes")
    monkeypatch.setattr(task_router, "ROOT", tmp_path)
    started, release = asyncio.Event(), asyncio.Event()
    class Bridge:
        @staticmethod
        async def run_turn(prompt, sid, on_event, **kwargs):
            if kwargs["options"] is conversation.OPTIONS:
                return claude_bridge.TurnResult("", None, False, None, "ok", structured={"action": "reply", "reply": "Я здесь.", "role": "", "brief": ""})
            started.set()
            await release.wait()
            return claude_bridge.TurnResult("результат", None, False, None, "ok")
        @staticmethod
        def stop(run_id):
            release.set()
            return True
    router = task_router.TaskRouter(sessions=FakeSessions(), budget_path=tmp_path / "budget.json", git_status=lambda: set(), env={"JARVIS_REVIEW": "off"})
    router.runtimes["claude"] = Bridge
    worker = task_router.Job("долгая работа", context="isolated")
    router.submit(OWNER, worker)
    await asyncio.wait_for(started.wait(), 1)
    gateway = make_gateway(tmp_path, router=router, conversation_enabled=True)
    try:
        await asyncio.wait_for(gateway.on_message(FakeUpdate(OWNER, message=FakeIncoming(text="Сложный\n" * 100 + "вопрос?")), FakeContext()), 1)
        assert not worker.result.done()
    finally:
        release.set()
        await worker.result


async def test_stop_prevents_late_conversation_reply_or_dispatch(tmp_path):
    class SlowRouter(ConversationRouter):
        def submit(self, chat_id, job):
            self.jobs.append((chat_id, job))
            job.result = asyncio.get_running_loop().create_future()
            return 0
    router = SlowRouter(None)
    gateway = make_gateway(tmp_path, router=router, conversation_enabled=True)
    context = FakeContext()
    pending = asyncio.create_task(gateway.on_message(FakeUpdate(OWNER, message=FakeIncoming(text="напиши пост")), context))
    await asyncio.sleep(0)
    gateway._stop_generation[str(OWNER)] = 1
    router.jobs[0][1].result.set_result(claude_bridge.TurnResult("", None, False, None, "ok", structured={"action": "dispatch", "reply": "Передаю", "role": "text", "brief": "Пост"}))
    await pending
    assert len(router.jobs) == 1 and context.bot.sent == []


class ConversationRouter(FakeRouter):
    def __init__(self, decision, *, status="ok"):
        super().__init__(pending=1, events=[])
        self.decision, self.conversation_status = decision, status

    def submit(self, chat_id, job):
        position = super().submit(chat_id, job)
        if job.context == "conversation":
            # FakeRouter resolves before waiter: mutation must precede gateway continuation.
            async def complete():
                result = claude_bridge.TurnResult("", None, False, None, self.conversation_status, structured=self.decision)
                if not job.result.done():
                    job.result.set_result(result)
            self.tasks[-1].cancel()
            self.tasks.append(asyncio.create_task(complete()))
        return position


async def test_every_message_uses_conversation_even_long_multiline(tmp_path):
    router = ConversationRouter({"action": "reply", "reply": "Я здесь, можешь спрашивать.", "role": "", "brief": ""})
    gateway = make_gateway(tmp_path, router=router, conversation_enabled=True)
    ctx = FakeContext()
    await gateway.on_message(FakeUpdate(OWNER, message=FakeIncoming(text="Объясни\n" * 100)), ctx)
    assert [j.context for _, j in router.jobs] == ["conversation"]
    assert router.jobs[0][1].queue == "conversation"
    assert any("можешь спрашивать" in m["text"] for m in ctx.bot.sent)


@pytest.mark.parametrize("decision,status", [(None, "error"), ({"action": "dispatch", "role": "oops", "reply": "да", "brief": "x"}, "ok")])
async def test_bad_conversation_never_falls_into_worker_queue(tmp_path, decision, status):
    router = ConversationRouter(decision, status=status)
    gateway = make_gateway(tmp_path, router=router, conversation_enabled=True)
    ctx = FakeContext()
    await gateway.on_message(FakeUpdate(OWNER, message=FakeIncoming(text="Что происходит?")), ctx)
    assert len(router.jobs) == 1
    assert any("собеседник" in m["text"].lower() for m in ctx.bot.sent)


async def test_dispatch_creates_one_fresh_task_and_keeps_original(tmp_path):
    router = ConversationRouter({"action": "dispatch", "reply": "Передаю специалисту по текстам.", "role": "text", "brief": "Напиши пост без обещаний."})
    gateway = make_gateway(tmp_path, router=router, conversation_enabled=True)
    original = "Напиши пост.\nНе обещай ничего!\n" * 20
    await gateway.on_message(FakeUpdate(OWNER, message=FakeIncoming(text=original)), FakeContext())
    dialogue, task = [j for _, j in router.jobs]
    assert dialogue.queue == "conversation" and task.queue is None
    assert task.context == "task" and task.role == "text" and task.original == original
    assert original in task.prompt
    assert task.options.disallowed_tools == ("Agent", "Task")


async def test_task_context_does_not_resume_chat_and_keeps_its_own_session(tmp_path, monkeypatch):
    from runtime import task_router
    from tests.test_telegram import FakeSessions
    monkeypatch.setattr(task_router, "EPISODES_DIR", tmp_path / "episodes")
    monkeypatch.setattr(task_router, "ROOT", tmp_path)
    monkeypatch.setattr(task_router.spec, "SPECS_DIR", tmp_path / "specs")
    monkeypatch.setattr(task_router.worker, "ROOT", tmp_path)
    calls = []
    class Bridge:
        @staticmethod
        async def run_turn(prompt, sid, on_event, **kwargs):
            calls.append(sid)
            return claude_bridge.TurnResult("Ответ", "task-session-" + kwargs["task_id"], False, None, "ok")
        @staticmethod
        def stop(run_id):
            return True
    sessions = FakeSessions()
    sessions.set(1, "old-chat")
    router = task_router.TaskRouter(sessions=sessions, budget_path=tmp_path / "budget.json", git_status=lambda: {}, env={"JARVIS_REVIEW": "off"})
    router.runtimes["claude"] = Bridge
    jobs = [task_router.Job("одна задача", context="task", data_root=tmp_path, role=role, original="целый запрос") for role in ("text", "research")]
    for job in jobs:
        router.submit(1, job)
        await job.result
    assert calls == [None, None]
    assert sessions.get(1) == "old-chat"
    assert sessions.get(f"1:task:{jobs[0].task_id}") != sessions.get(f"1:task:{jobs[1].task_id}")
    for job in jobs:
        data = json.loads((tmp_path / "state" / "tasks" / f"{job.task_id}.json").read_text(encoding="utf-8"))
        assert data["original"] == "целый запрос" and data["role"] == job.role and data["status"] == "ok"
    snapshot = json.loads(conversation.task_snapshot(tmp_path, 1))
    assert len(snapshot) == 2 and all(row["result"] == "Ответ" for row in snapshot)
    assert all("acceptance" in row and "files" in row for row in snapshot)
    assert json.loads(conversation.task_snapshot(tmp_path, 2)) == []


async def test_pipeline_fix_keeps_original_worker_restrictions(tmp_path, monkeypatch):
    from runtime import task_router
    from tests.test_telegram import FakeSessions
    checks = iter([["пропущен проход"], []])
    monkeypatch.setattr(task_router.public_texts, "check", lambda *args: next(checks))
    router = task_router.TaskRouter(sessions=FakeSessions(), budget_path=tmp_path / "budget.json")
    options = claude_bridge.TurnOptions(disallowed_tools=("Agent", "Task"))
    job = task_router.Job("одна задача", context="task", options=options)
    async def timed(*args, **kwargs):
        assert kwargs["options"] is options
        return claude_bridge.TurnResult("Исправлено", "session", False, None, "ok")
    monkeypatch.setattr(router, "_timed", timed)
    await router._enforce_public_texts("1", job, claude_bridge.TurnResult("Черновик", "session", False, None, "ok"), 1)


async def test_review_fix_keeps_original_worker_restrictions(tmp_path, monkeypatch):
    from runtime import task_router
    from tests.test_telegram import FakeSessions
    monkeypatch.setattr(task_router, "ROOT", tmp_path)
    router = task_router.TaskRouter(sessions=FakeSessions(), budget_path=tmp_path / "budget.json", git_status=lambda: set())
    options = claude_bridge.TurnOptions(disallowed_tools=("Agent", "Task"))
    job = task_router.Job("одна задача", context="task", options=options)
    rounds = 0
    async def timed(*args, **kwargs):
        nonlocal rounds
        if kwargs["options"] is task_router.review.OPTIONS:
            rounds += 1
            return claude_bridge.TurnResult("", None, False, None, "ok", structured={"verdict": "fix" if rounds == 1 else "pass", "problems": ["поправь"] if rounds == 1 else [], "checked": []})
        assert kwargs["options"] is options
        return claude_bridge.TurnResult("Исправлено", "session", False, None, "ok")
    monkeypatch.setattr(router, "_timed", timed)
    result = await router._review("1", job, claude_bridge.TurnResult("Черновик", "session", False, None, "ok"), 1)
    assert result.acceptance == "accepted"


async def test_followup_returns_to_same_task_only(tmp_path):
    from runtime import task_router
    old = task_router.Job("первое поручение", task="пост", context="task", role="text", original="Полный исходник")
    old.chat = str(OWNER)
    old.runtime_used = "claude2"
    conversation.save_task(tmp_path / "state" / "tasks", old,
        claude_bridge.TurnResult("Черновик", "old-task-session", False, None, "ok"))
    router = ConversationRouter({"action": "dispatch", "reply": "Исправлю", "role": "text", "brief": "Убери обещание", "task_id": old.task_id})
    gateway = make_gateway(tmp_path, router=router, conversation_enabled=True)
    incoming = "Убери обещание из этого поста.\nФайл от владелицы: inbox/пример.md"
    await gateway._run(FakeUpdate(OWNER, message=FakeIncoming(text=None)), FakeContext(), incoming)
    new = router.jobs[-1][1]
    assert new.task_id == old.task_id and new.resume_task and new.role == "text"
    assert new.runtime == "claude2" and incoming in new.prompt
    assert new.original == old.original and "Убери обещание" in new.prompt
    assert conversation.previous_task(tmp_path, OWNER + 1, old.task_id, "text") is None
    assert conversation.previous_task(tmp_path, OWNER, old.task_id, "research") is None
    conversation.save_task(tmp_path / "state" / "tasks", new)
    assert len(list((tmp_path / "state" / "tasks" / "versions").glob("*.json"))) == 1
    assert conversation.previous_task(tmp_path, OWNER, old.task_id, "text") is None


async def test_explicit_task_resume_uses_only_task_session(tmp_path, monkeypatch):
    from runtime import task_router
    from tests.test_telegram import FakeSessions
    monkeypatch.setattr(task_router, "ROOT", tmp_path)
    monkeypatch.setattr(task_router, "EPISODES_DIR", tmp_path / "episodes")
    sessions = FakeSessions()
    sessions.set(1, "main-session")
    sessions.set("1:task:known", "own-session")
    class Bridge:
        @staticmethod
        async def run_turn(prompt, sid, on_event, **kwargs):
            assert sid == "own-session"
            return claude_bridge.TurnResult("Правка", sid, False, None, "ok")
    router = task_router.TaskRouter(sessions=sessions, budget_path=tmp_path / "budget.json",
        git_status=lambda: set(), env={"JARVIS_REVIEW": "off"})
    router.runtimes["claude"] = Bridge
    job = task_router.Job("уточнение", context="task", task_id="known", role="text", resume_task=True)
    router.submit(1, job)
    await job.result
    assert sessions.get(1) == "main-session"
