"""Понятные запросы на подтверждение и быстрый ответ, который знает, что ждёт её кнопки (её жалоба 2026-10-07)."""
import json

from integrations.telegram import explain
from runtime import side_lane

CODE = ("python -I -c \"import json\nfor w in ['test-jarvis']:\n d=json.load(open(w+'/reels.json',encoding='utf-8'))\n"
        "print(d['week'],d['stats'])\"")


def test_script_button_says_what_it_does_in_plain_words():
    text = explain.build("EXTERNAL", "Bash", "запуск кода", {"kind": "run_script", "tool_input": {
        "command": CODE, "description": "Смотрю, какие рилсы лежат в контент-плане"}})
    assert "Зачем (как я сам это описал): Смотрю, какие рилсы лежат в контент-плане" in text
    assert "reels.json" in text and "последствия автоматически не проверены" in text
    assert CODE not in text and "Начало кода" not in text and "Отклонить" in text


def test_script_with_network_or_writes_is_flagged():
    net = explain.describe_command("python -c \"import requests; requests.post('https://x.example', data=open('a.md').read())\"")
    assert any("интернет" in line for line in net) and not any("только читает" in line for line in net)
    wr = explain.describe_command("python -c \"open('a.md','w').write('x')\"")
    assert any("Меняет" in line for line in wr)


def test_side_lane_does_not_guess_pending_requests_from_journal(tmp_path):
    journal = tmp_path / "state" / "approvals.jsonl"
    journal.parent.mkdir(parents=True)
    rows = [{"type": "request", "request_id": "r1", "level": "EXTERNAL", "tool": "Bash", "summary": "x",
             "details": {"kind": "run_script", "tool_input": {"command": CODE, "description": "Смотрю контент-план"}}},
            {"type": "request", "request_id": "r2", "level": "EXTERNAL", "tool": "Bash", "summary": "y",
             "details": {"kind": "run_script", "tool_input": {"command": "python -c 1"}}},
            {"type": "decision", "request_id": "r2", "decision": "allow"}]
    journal.write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")
    ctx = side_lane.context(tmp_path, 1)
    assert "Смотрю контент-план" not in ctx and "python -c 1" not in ctx


def test_side_lane_without_pending_requests_stays_quiet(tmp_path):
    assert "ждёт её кнопки" not in side_lane.context(tmp_path, 1)


def test_side_lane_prompt_tells_to_explain_pending_requests():
    assert "действующий запрос" in side_lane.PROMPT.read_text(encoding="utf-8")


def test_dynamic_code_never_gets_read_only_or_no_network_guarantee():
    text = "\n".join(explain.describe_command("python -c \"import subprocess; subprocess.run(['evil'])\""))
    assert "только читает" not in text and "не проверены" in text


def test_full_details_preserve_multiline_command():
    assert CODE in explain.full_details("Bash", {"tool_input": {"command": CODE}})
