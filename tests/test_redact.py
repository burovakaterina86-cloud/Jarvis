"""Маскировка секретов в журнале и безопасная сводка вызова инструмента (P1.1, аудит 2026-10-05)."""
import pytest

from runtime import redact

SECRETS = [
    ("bearer", "curl -H 'Authorization: Bearer abc.DEF-123_xyz' https://api.x.io", "abc.DEF-123_xyz"),
    ("token=", "https://api.x.io/run?token=s3cr3tValue&limit=5", "s3cr3tValue"),
    ("api_key json", '{"api_key": "k-12345678"}', "k-12345678"),
    ("password:", "password: hunter2hunter2", "hunter2hunter2"),
    ("openai/anthropic", "key sk-ant-api03-AbCdEfGhIjKlMnOpQrStUv", "sk-ant-api03-AbCdEfGhIjKlMnOpQrStUv"),
    ("github", "ghp_1234567890abcdefghijABCDEFGHIJ123456", "ghp_1234567890abcdefghijABCDEFGHIJ123456"),
    ("telegram bot", "bot 123456789:AAHdqTcvCH1vGWJxfSeofSAs0K5PALDsaw0", "AAHdqTcvCH1vGWJxfSeofSAs0K5PALDsaw0"),
    ("apify", "apify_api_AbCdEfGhIjKlMnOpQrStUvWxYz012345", "apify_api_AbCdEfGhIjKlMnOpQrStUvWxYz012345"),
    ("groq", "gsk_AbCdEfGhIjKlMnOpQrStUvWxYz0123456789", "gsk_AbCdEfGhIjKlMnOpQrStUvWxYz0123456789"),
    ("aws", "AKIAIOSFODNN7EXAMPLE", "AKIAIOSFODNN7EXAMPLE"),
    ("google", "AIzaSyA1234567890abcdefghijklmnopqrstu", "AIzaSyA1234567890abcdefghijklmnopqrstu"),
    ("long opaque", "x-jarvis-token Zm9vYmFyYmF6cXV4MTIzNDU2Nzg5MGFiY2RlZmdoaWpr", "Zm9vYmFyYmF6cXV4MTIzNDU2Nzg5MGFiY2RlZmdoaWpr"),
]


@pytest.mark.parametrize("name,text,secret", SECRETS, ids=[s[0] for s in SECRETS])
def test_secrets_are_masked(name, text, secret):
    out = redact.redact(text)
    assert secret not in out
    assert "***" in out


ORDINARY = [
    "C:/Users/burov/Projects/Jarvis/essa-ai/content/2026-09-21-не-изучай/post.md",
    "python -m integrations.visuals.build essa-ai/content/x slides.json",
    "Привет, Катерина! Комплект готов: пост, карусель, рилс.",
    "git log --oneline -5",
    "токен доверия аудитории растёт",
]


@pytest.mark.parametrize("text", ORDINARY)
def test_ordinary_text_is_untouched(text):
    assert redact.redact(text) == text


def test_redact_obj_walks_nested_structures():
    data = {"a": ["Bearer qwertyuiop123", {"b": "token=abc123def"}], "n": 5, "none": None}
    out = redact.redact_obj(data)
    assert "qwertyuiop123" not in str(out) and "abc123def" not in str(out)
    assert out["n"] == 5 and out["none"] is None


SUMMARIES = [
    ("Read", {"file_path": "essa-ai/VOICE.md"}, "essa-ai/VOICE.md"),
    ("Write", {"file_path": "memory/a.md", "content": "секретное содержимое"}, "memory/a.md"),
    ("Grep", {"pattern": "Guard", "path": "runtime"}, "Guard"),
    ("WebFetch", {"url": "https://example.com/path?q=личное", "prompt": "x"}, "example.com"),
    ("mcp__playwright__browser_navigate", {"url": "https://shop.ru/cart?id=1"}, "shop.ru"),
    ("Agent", {"subagent_type": "researcher", "description": "найти цифры", "prompt": "длинно"}, "researcher"),
    ("Skill", {"skill": "carousel-instagram"}, "carousel-instagram"),
]


@pytest.mark.parametrize("tool,inp,expected", SUMMARIES, ids=[s[0] for s in SUMMARIES])
def test_tool_summary_names_the_object(tool, inp, expected):
    assert expected in redact.tool_summary(tool, inp)


def test_tool_summary_never_logs_contents_query_or_typed_text():
    assert "секретное" not in redact.tool_summary("Write", {"file_path": "a.md", "content": "секретное"})
    assert "личное" not in redact.tool_summary("WebFetch", {"url": "https://e.com/p?q=личное"})
    s = redact.tool_summary("mcp__playwright__browser_type",
                            {"element": "Поле email", "ref": "e1", "text": "me@mail.ru"})
    assert "me@mail.ru" not in s and "Поле email" in s
    assert "длинно" not in redact.tool_summary("Agent", {"subagent_type": "x", "prompt": "длинно"})


def test_tool_summary_masks_and_shortens_commands():
    s = redact.tool_summary("Bash", {"command": "curl -H 'Authorization: Bearer abcdef123456' " + "x" * 500})
    assert "abcdef123456" not in s
    assert len(s) <= 210


def test_tool_summary_of_unknown_tool_lists_only_keys():
    s = redact.tool_summary("mcp__other__do", {"text": "личное", "id": "7"})
    assert "личное" not in s and "text" in s
