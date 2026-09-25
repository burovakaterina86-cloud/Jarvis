"""Почтовый ящик бота: задача по расписанию кладёт письмо в state/outbox/, бот присылает его владелице."""
from integrations.telegram import outbox
from tests.test_telegram import OWNER, FakeBot, make_gateway


def test_post_writes_a_message_file(tmp_path):
    path = outbox.post(tmp_path, "Радар готов", ["essa-ai/content/radar-2026-09-28/radar.md"])
    assert path.parent == tmp_path / "state" / "outbox"
    text = path.read_text(encoding="utf-8")
    assert text.startswith("Радар готов")
    assert "📎 essa-ai/content/radar-2026-09-28/radar.md" in text


async def test_gateway_delivers_outbox_to_owner_once(tmp_path):
    f = tmp_path / "essa-ai" / "content" / "radar-2026-09-28" / "radar.md"
    f.parent.mkdir(parents=True)
    f.write_text("топ", encoding="utf-8")
    outbox.post(tmp_path, "Радар готов", ["essa-ai/content/radar-2026-09-28/radar.md"])
    g = make_gateway(tmp_path)
    bot = FakeBot()
    g.attach(bot)

    assert await g.check_outbox() == 1
    assert any("Радар готов" in m["text"] and m["chat_id"] == OWNER for m in bot.sent)
    assert [d["filename"] for d in bot.documents] == ["radar.md"]
    assert await g.check_outbox() == 0                       # второй опрос молчит
    assert list((tmp_path / "state" / "outbox" / "sent").glob("*.md"))


async def test_failed_delivery_stays_for_next_poll(tmp_path):
    outbox.post(tmp_path, "Радар готов")
    g = make_gateway(tmp_path)
    g.attach(FakeBot(fail_message=True))
    assert await g.check_outbox() == 0
    assert len(list((tmp_path / "state" / "outbox").glob("*.md"))) == 1


async def test_no_owner_no_delivery(tmp_path):
    outbox.post(tmp_path, "Радар готов")
    g = make_gateway(tmp_path, owner_id=None)
    g.attach(FakeBot())
    assert await g.check_outbox() == 0
