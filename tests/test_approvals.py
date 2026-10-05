"""Шов approvals: HTTP POST /approve с фейковым gateway (подписка on_request + resolve)."""
import asyncio
import json
import shutil
import subprocess
import sys
from pathlib import Path

import aiohttp
import pytest

from runtime.approvals import ApprovalsServer

REPO = Path(__file__).resolve().parents[1]

BODY = {"level": "EXTERNAL", "tool": "mcp__instagram__reply_comment",
        "summary": "Ответить @user: «спасибо»", "details": {"kind": "reply", "tool_input": {"text": "спасибо"}}}


class FakeGateway:
    """Записывает запросы и по желанию сразу отвечает решением."""

    def __init__(self, server, decision=None, reason=""):
        self.server, self.decision, self.reason = server, decision, reason
        self.calls = []
        self.seen = asyncio.Event()
        server.on_request(self)

    def __call__(self, request_id, level, tool, summary, details):
        self.calls.append((request_id, level, tool, summary, details))
        self.seen.set()
        if self.decision:
            asyncio.get_running_loop().call_soon(self.server.resolve, request_id, self.decision, self.reason)


@pytest.fixture
async def server(tmp_path):
    srv = ApprovalsServer(timeout=5)
    await srv.start(tmp_path)
    yield srv
    await srv.stop()


def _token(root):
    return (Path(root) / "state" / "secrets" / "approvals.token").read_text(encoding="utf-8").strip()


def _port(root):
    return int((Path(root) / "state" / "approvals.port").read_text(encoding="utf-8").strip())


async def _post(root, body=BODY, token="__file__"):
    headers = {}
    if token == "__file__":
        headers["X-Jarvis-Token"] = _token(root)
    elif token is not None:
        headers["X-Jarvis-Token"] = token
    async with aiohttp.ClientSession() as s:
        async with s.post(f"http://127.0.0.1:{_port(root)}/approve", json=body, headers=headers) as r:
            text = await r.text()
            return r.status, (json.loads(text) if r.status == 200 else text)


def _journal(root):
    path = Path(root) / "state" / "approvals.jsonl"
    return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]


@pytest.mark.parametrize("decision", ["allow", "deny"])
async def test_resolve_decides_response(server, tmp_path, decision):
    gw = FakeGateway(server, decision=decision, reason="владелица нажала")
    status, data = await _post(tmp_path)
    assert status == 200
    assert data == {"decision": decision, "reason": "владелица нажала"}
    (_, level, tool, summary, details), = gw.calls
    assert (level, tool, summary, details) == ("EXTERNAL", BODY["tool"], BODY["summary"], BODY["details"])


async def test_no_answer_until_timeout_is_deny_timeout(tmp_path):
    srv = ApprovalsServer(timeout=1)
    await srv.start(tmp_path)
    try:
        gw = FakeGateway(srv)
        status, data = await asyncio.wait_for(_post(tmp_path), 10)
        assert status == 200 and data["decision"] == "deny" and data["reason"] == "timeout"
        assert len(gw.calls) == 1
        # поздний resolve после таймаута ничего не ломает и сообщает, что запроса уже нет
        assert srv.resolve(gw.calls[0][0], "allow") is False
    finally:
        await srv.stop()


@pytest.mark.parametrize("token", [None, "чужой-токен", ""])
async def test_wrong_or_missing_token_401_and_no_callback(server, tmp_path, token):
    gw = FakeGateway(server, decision="allow")
    status, _ = await _post(tmp_path, token=token)
    assert status == 401
    assert gw.calls == []


async def test_listens_only_on_loopback(server):
    assert server.addresses
    assert all(host == "127.0.0.1" for host, _ in server.addresses)
    assert {p for _, p in server.addresses} == {server.port}


async def test_journal_and_events_have_request_and_decision(server, tmp_path):
    gw = FakeGateway(server, decision="deny", reason="нет")
    await _post(tmp_path)
    rid = gw.calls[0][0]
    kinds = [(r["type"], r["request_id"]) for r in _journal(tmp_path)]
    assert kinds == [("request", rid), ("decision", rid)]
    req, dec = _journal(tmp_path)
    assert req["tool"] == BODY["tool"] and req["level"] == "EXTERNAL" and req["summary"] == BODY["summary"]
    assert dec["decision"] == "deny" and dec["reason"] == "нет"
    events = [json.loads(x) for x in (tmp_path / "state" / "events.jsonl").read_text(encoding="utf-8").splitlines()]
    assert [e["type"] for e in events] == ["approval_request", "approval_decision"]
    assert events[0]["status"] == "waiting_approval" and events[1]["decision"] == "deny"
    assert all("ts" in e and "session" in e and "agent" in e and "progress" in e for e in events)


async def test_parallel_requests_are_independent(server, tmp_path):
    gw = FakeGateway(server)
    body2 = dict(BODY, tool="mcp__mail__send", summary="Письмо")
    t1 = asyncio.create_task(_post(tmp_path))
    t2 = asyncio.create_task(_post(tmp_path, body=body2))
    while len(gw.calls) < 2:
        await asyncio.wait_for(gw.seen.wait(), 5)
        gw.seen.clear()
    by_tool = {c[2]: c[0] for c in gw.calls}
    assert server.resolve(by_tool["mcp__mail__send"], "deny", "нет") is True
    status2, data2 = await asyncio.wait_for(t2, 5)
    assert data2["decision"] == "deny"
    assert not t1.done()
    server.resolve(by_tool[BODY["tool"]], "allow")
    status1, data1 = await asyncio.wait_for(t1, 5)
    assert data1["decision"] == "allow"


async def test_restart_rewrites_port_and_token(tmp_path):
    srv = ApprovalsServer()
    await srv.start(tmp_path)
    old_token = _token(tmp_path)
    await srv.stop()
    assert not (tmp_path / "state" / "approvals.port").exists()
    srv2 = ApprovalsServer()
    port = await srv2.start(tmp_path)
    try:
        assert _port(tmp_path) == port
        assert _token(tmp_path) != old_token
    finally:
        await srv2.stop()


async def test_client_gone_drops_request_immediately(server, tmp_path):
    gw = FakeGateway(server)
    task = asyncio.create_task(_post(tmp_path))
    await asyncio.wait_for(gw.seen.wait(), 5)
    rid = gw.calls[0][0]
    task.cancel()  # Guard ушёл: соединение закрыто
    with pytest.raises(asyncio.CancelledError):
        await task
    for _ in range(50):
        if rid not in server.pending:
            break
        await asyncio.sleep(0.05)
    assert server.resolve(rid, "allow") is False
    await asyncio.sleep(0.1)
    decisions = [r for r in _journal(tmp_path) if r["type"] == "decision"]
    assert [(d["decision"], d["reason"]) for d in decisions] == [("deny", "client_gone")]


def test_default_timeout_shorter_than_guard_deadline():
    import yaml
    guard_deadline = yaml.safe_load((REPO / "runtime" / "policy.yaml").read_text(encoding="utf-8"))["approval_timeout_sec"]
    assert ApprovalsServer().timeout < guard_deadline


@pytest.mark.parametrize("body", [
    "не json",
    {"tool": "x", "summary": "s", "details": {}},
    dict(BODY, level="READ"),
    dict(BODY, details="строка"),
])
async def test_bad_request_400_and_no_callback(server, tmp_path, body):
    gw = FakeGateway(server, decision="allow")
    async with aiohttp.ClientSession() as s:
        kwargs = {"data": body.encode("utf-8")} if isinstance(body, str) else {"json": body}
        async with s.post(f"http://127.0.0.1:{_port(tmp_path)}/approve",
                          headers={"X-Jarvis-Token": _token(tmp_path)}, **kwargs) as r:
            assert r.status == 400
    assert gw.calls == []


async def test_stop_with_pending_request_denies_shutdown(tmp_path):
    srv = ApprovalsServer(timeout=30)
    await srv.start(tmp_path)
    gw = FakeGateway(srv)
    task = asyncio.create_task(_post(tmp_path))
    await asyncio.wait_for(gw.seen.wait(), 5)
    await srv.stop()
    status, data = await asyncio.wait_for(task, 5)
    assert (status, data) == (200, {"decision": "deny", "reason": "shutdown"})
    assert [(r["decision"], r["reason"]) for r in _journal(tmp_path) if r["type"] == "decision"] == [("deny", "shutdown")]


async def test_token_restricted_before_content_written(tmp_path, monkeypatch):
    import runtime.approvals as mod
    seen = []
    monkeypatch.setattr(mod, "_restrict_to_owner", lambda p: seen.append(p.read_text(encoding="utf-8")) or True)
    srv = ApprovalsServer()
    await srv.start(tmp_path)
    try:
        assert seen == [""]
        assert len(_token(tmp_path)) >= 32
    finally:
        await srv.stop()


async def test_restrict_failure_warns_and_emits_error(tmp_path, monkeypatch, caplog):
    import runtime.approvals as mod

    def boom(*a, **k):
        raise OSError("нет icacls")
    monkeypatch.setattr(mod.subprocess, "run", boom)
    monkeypatch.setattr(mod.os, "chmod", boom)
    srv = ApprovalsServer(timeout=5)
    with caplog.at_level("WARNING", logger="jarvis.approvals"):
        await srv.start(tmp_path)
    try:
        assert any(r.levelname == "WARNING" for r in caplog.records)
        events = [json.loads(x) for x in (tmp_path / "state" / "events.jsonl").read_text(encoding="utf-8").splitlines()]
        assert [e["type"] for e in events] == ["error"]
        FakeGateway(srv, decision="allow")
        assert (await _post(tmp_path))[1]["decision"] == "allow"
    finally:
        await srv.stop()


async def test_journal_truncates_long_strings(server, tmp_path):
    long = "я" * 2000
    FakeGateway(server, decision="deny")
    body = dict(BODY, details={"kind": "reply", "tool_input": {"text": long, "nested": [{"x": long}], "n": 5}})
    await _post(tmp_path, body=body)
    req = _journal(tmp_path)[0]
    ti = req["details"]["tool_input"]
    assert ti["text"] == "я" * 500 and ti["nested"][0]["x"] == "я" * 500 and ti["n"] == 5


# ---------- интеграция с реальным guard.py ----------

@pytest.fixture
def guard_root(tmp_path):
    """Временный корень: guard.py берёт корень из своего расположения (parents[2])."""
    (tmp_path / ".claude" / "hooks").mkdir(parents=True)
    (tmp_path / "runtime").mkdir()
    shutil.copy(REPO / ".claude" / "hooks" / "guard.py", tmp_path / ".claude" / "hooks" / "guard.py")
    shutil.copy(REPO / "runtime" / "policy.yaml", tmp_path / "runtime" / "policy.yaml")
    return tmp_path


@pytest.mark.parametrize("decision,code", [("allow", 0), ("deny", 2)])
async def test_real_guard_hook_with_api(guard_root, decision, code):
    srv = ApprovalsServer(timeout=30)
    await srv.start(guard_root)
    try:
        gw = FakeGateway(srv, decision=decision, reason="тест")
        event = {"hook_event_name": "PreToolUse", "tool_name": "mcp__instagram__reply_comment",
                 "tool_input": {"comment_id": "1", "text": "спасибо"}}
        proc = await asyncio.create_subprocess_exec(
            sys.executable, str(guard_root / ".claude" / "hooks" / "guard.py"),
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        _, err = await asyncio.wait_for(proc.communicate(json.dumps(event).encode("utf-8")), 60)
        assert proc.returncode == code, err.decode("utf-8", "replace")
        assert len(gw.calls) == 1 and gw.calls[0][1] == "EXTERNAL"
        assert gw.calls[0][4]["tool_input"] == event["tool_input"]
        if code == 2:
            assert "тест" in err.decode("utf-8")
    finally:
        await srv.stop()


async def test_task_id_and_masking_reach_journal_and_events(server, tmp_path):
    """P1.1: запрос подписан задачей; токены в аргументах не попадают в журналы."""
    FakeGateway(server, decision="allow", reason="да")
    body = dict(BODY, task_id="t-9",
                details={"kind": "x", "tool_input": {"command": "curl -H 'Authorization: Bearer abcdef123456'"}})
    await _post(tmp_path, body=body)
    journal = _journal(tmp_path)
    assert [r.get("task_id") for r in journal] == ["t-9", "t-9"]
    events = [json.loads(x) for x in (tmp_path / "state" / "events.jsonl").read_text(encoding="utf-8").splitlines()]
    assert [e.get("task_id") for e in events] == ["t-9", "t-9"]
    blob = (tmp_path / "state" / "approvals.jsonl").read_text(encoding="utf-8")
    assert "abcdef123456" not in blob
