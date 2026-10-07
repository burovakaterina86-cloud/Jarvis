"""Вопрос под карточкой объясняет именно её и не запускает новую задачу."""
import asyncio
from types import SimpleNamespace

from runtime import side_lane
from runtime.approvals import ApprovalsServer
from tests.test_telegram import OWNER, FakeContext, FakeIncoming, FakeUpdate, make_gateway


def pending(server, rid, task, description):
    server._pending[rid] = asyncio.get_running_loop().create_future()
    server._records[rid] = {"request_id": rid, "task_id": task, "level": "EXTERNAL", "tool": "Bash",
                            "summary": "просмотр плана", "details": {"kind": "run_script", "tool_input":
                            {"command": "python -c 'print(1)'", "description": description}}}


async def test_reply_to_approval_explains_only_selected_request_without_model(tmp_path):
    server = ApprovalsServer()
    pending(server, "one", "t1", "Посмотреть идеи недели")
    pending(server, "two", "t2", "Другое действие")
    g = make_gateway(tmp_path, approvals=server)
    g._approval_messages[(str(OWNER), 9)] = "one"
    g.router.active_tasks = lambda chat: [SimpleNamespace(task_id="t1", chat=str(OWNER))]
    msg = FakeIncoming(text="зачем тебе это?")
    msg.reply_to_message = SimpleNamespace(message_id=9, text="карточка")
    ctx = FakeContext()
    await g.on_message(FakeUpdate(OWNER, message=msg), ctx)
    answer = ctx.bot.sent[-1]["text"]
    assert "Посмотреть идеи недели" in answer and "Другое действие" not in answer
    assert not g.router.jobs


def test_side_context_never_uses_pending_approvals_from_disk(tmp_path):
    path = tmp_path / "state" / "approvals.jsonl"
    path.parent.mkdir()
    path.write_text('{"type":"request","summary":"stale-other-chat"}', encoding="utf-8")
    text = side_lane.build_prompt(tmp_path, OWNER, "зачем?", tasks=[], approvals=[])
    assert "stale-other-chat" not in text


async def test_copied_approval_card_is_data_not_a_new_job(tmp_path):
    server = ApprovalsServer()
    pending(server, "one", "t1", "Посмотреть идеи недели")
    g = make_gateway(tmp_path, approvals=server)
    g.router.active_tasks = lambda chat: [SimpleNamespace(task_id="t1", chat=str(OWNER))]
    text = "🌐 Хочу запустить программу на твоём компьютере.\nКоманда: python …\nМожно, я это сделаю?"
    ctx = FakeContext()
    await g.on_message(FakeUpdate(OWNER, message=FakeIncoming(text=text)), ctx)
    assert not g.router.jobs and "Посмотреть идеи недели" in ctx.bot.sent[-1]["text"]


async def test_normal_answer_with_real_approvals_is_delivered(tmp_path):
    from runtime.claude_bridge import TurnResult
    g = make_gateway(tmp_path, approvals=ApprovalsServer())
    ctx = FakeContext()
    await g._deliver(ctx, OWNER, TurnResult("Понятный ответ", None, False, None, "ok"))
    assert ctx.bot.sent[-1]["text"] == "Понятный ответ"
