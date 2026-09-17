"""Фейковый `claude` для тестов моста: печатает записанный stream-json.

Сценарий берётся из env FAKE_CLAUDE_SCENARIO, журнал вызовов — FAKE_CLAUDE_LOG
(jsonl: argv, env-ключи, длина stdin). Реальный Claude не вызывается.
"""
import json
import os
import subprocess
import sys
import time

SID_NEW = "sess-new-0001"


def out(obj):
    sys.stdout.buffer.write((json.dumps(obj, ensure_ascii=False) + "\n").encode("utf-8"))
    sys.stdout.flush()


def raw(line):
    sys.stdout.buffer.write((line + "\n").encode("utf-8"))
    sys.stdout.flush()


def tool_pair(sid):
    out({"type": "assistant", "session_id": sid, "parent_tool_use_id": None,
         "message": {"content": [{"type": "tool_use", "id": "tu1", "name": "Read",
                                  "input": {"file_path": "CLAUDE.md"}}]}})
    out({"type": "user", "session_id": sid, "parent_tool_use_id": None,
         "message": {"content": [{"type": "tool_result", "tool_use_id": "tu1", "content": "ok"}]}})


def main():
    argv = sys.argv[1:]
    stdin_data = sys.stdin.buffer.read().decode("utf-8")
    scenario = os.environ.get("FAKE_CLAUDE_SCENARIO", "ok")
    log = os.environ.get("FAKE_CLAUDE_LOG")
    if log:
        with open(log, "a", encoding="utf-8") as fh:
            fh.write(json.dumps({"argv": argv, "env_keys": sorted(os.environ),
                                 "env_jarvis": {k: v for k, v in os.environ.items() if k.startswith("JARVIS_")},
                                 "stdin_len": len(stdin_data), "t_start": time.time(),
                                 "stdin_tail": stdin_data[-200:]},
                                ensure_ascii=False) + "\n")
    resume = argv[argv.index("--resume") + 1] if "--resume" in argv else None
    sid = resume or SID_NEW

    if scenario in ("resume_fail", "overflow") and resume:
        if scenario == "resume_fail":
            sys.stderr.write(f"No conversation found with session ID: {resume}\n")
            sys.exit(1)
        out({"type": "system", "subtype": "init", "session_id": sid})
        out({"type": "result", "subtype": "success", "is_error": True, "session_id": sid,
             "result": "Prompt is too long", "total_cost_usd": 0.0, "duration_ms": 5})
        sys.exit(1)

    out({"type": "system", "subtype": "init", "session_id": sid, "tools": ["Read"]})
    if scenario == "sleep":
        time.sleep(60)
    if scenario == "sleep_child":
        # дочерний процесс живёт дольше родителя — проверка taskkill /T
        pid_file = os.environ["FAKE_CLAUDE_CHILD_PID"]
        child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(120)"])
        with open(pid_file, "w", encoding="utf-8") as fh:
            fh.write(str(child.pid))
        time.sleep(120)
    if scenario == "auth_result":
        out({"type": "result", "subtype": "success", "is_error": True, "session_id": sid,
             "result": "Failed to authenticate: OAuth session expired and could not be refreshed",
             "total_cost_usd": 0, "duration_ms": 3})
        sys.exit(1)
    if scenario in ("rate_limit", "auth"):
        err = "rate_limit" if scenario == "rate_limit" else "authentication_failed"
        out({"type": "system", "subtype": "api_retry", "attempt": 1, "max_retries": 10,
             "retry_delay_ms": 1000, "error_status": 429 if err == "rate_limit" else 401,
             "error": err, "session_id": sid})
        out({"type": "result", "subtype": "success", "is_error": True, "session_id": sid,
             "result": "API Error", "total_cost_usd": 0.0, "duration_ms": 10})
        sys.exit(1)
    if scenario in ("overflow_after_tools", "resume_fail_after_tools") and resume:
        tool_pair(sid)
        if scenario == "resume_fail_after_tools":
            sys.stderr.write(f"No conversation found with session ID: {resume}\n")
            sys.exit(1)
        out({"type": "result", "subtype": "success", "is_error": True, "session_id": sid,
             "result": "Prompt is too long", "total_cost_usd": 0.0, "duration_ms": 7})
        sys.exit(1)
    if scenario == "garbage":
        raw("не json вовсе")
        raw(json.dumps([1, 2, 3]))
        raw(json.dumps("строка"))
        raw(json.dumps({"type": "assistant", "session_id": sid,
                        "message": {"content": [{"type": "text", "text": "ю" * 200000}]}}))
    if scenario == "context_in_text":
        out({"type": "assistant", "session_id": sid, "parent_tool_use_id": None,
             "message": {"content": [{"type": "text",
                                      "text": "У Claude большой context window, prompt is too long тут просто слова."}]}})
        out({"type": "result", "subtype": "success", "is_error": False, "session_id": sid,
             "result": "У Claude большой context window, prompt is too long тут просто слова.",
             "total_cost_usd": 0.001, "duration_ms": 12})
        return
    time.sleep(float(os.environ.get("FAKE_CLAUDE_DELAY", "0")))
    tool_pair(sid)
    out({"type": "assistant", "session_id": sid, "parent_tool_use_id": None,
         "message": {"content": [{"type": "text", "text": "Привет, Катерина!"}]}})
    out({"type": "result", "subtype": "success", "is_error": False, "session_id": sid,
         "result": "Привет, Катерина!", "total_cost_usd": 0.0123, "duration_ms": 1500})
    if log:
        with open(log, "a", encoding="utf-8") as fh:
            fh.write(json.dumps({"t_end": time.time(), "stdin_tail": stdin_data[-200:]},
                                ensure_ascii=False) + "\n")


if __name__ == "__main__":
    main()
