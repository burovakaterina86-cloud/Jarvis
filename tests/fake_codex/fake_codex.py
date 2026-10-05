"""Фейковый `codex` для тестов codex_bridge: печатает события `codex exec --json`, как живой 0.157.0.

Сценарий — env FAKE_CODEX_SCENARIO, журнал вызовов — FAKE_CODEX_LOG (argv, хвост stdin).
"""
import json
import os
import sys
import time


def out(obj):
    sys.stdout.buffer.write((json.dumps(obj, ensure_ascii=False) + "\n").encode("utf-8"))
    sys.stdout.flush()


def main():
    argv = sys.argv[1:]
    stdin = sys.stdin.buffer.read().decode("utf-8")
    log = os.environ.get("FAKE_CODEX_LOG")
    if log:
        with open(log, "a", encoding="utf-8") as fh:
            schema = None
            if "--output-schema" in argv:
                with open(argv[argv.index("--output-schema") + 1], encoding="utf-8") as sf:
                    schema = json.load(sf)
            fh.write(json.dumps({"argv": argv, "stdin_tail": stdin[-300:], "cwd": os.getcwd(), "schema": schema,
                                 "env_jarvis": {k: v for k, v in os.environ.items() if k.startswith("JARVIS_")}},
                                ensure_ascii=False) + "\n")
    scenario = os.environ.get("FAKE_CODEX_SCENARIO", "ok")
    thread = argv[argv.index("resume") + 1] if "resume" in argv else "thread-new-0001"
    out({"type": "thread.started", "thread_id": thread})
    out({"type": "turn.started"})
    if scenario == "sleep":
        time.sleep(60)
    if scenario == "rate_limit":
        out({"type": "turn.failed", "error": {"message": "You've hit your usage limit. Try again later."}})
        sys.exit(1)
    if scenario == "auth":
        out({"type": "turn.failed", "error": {"message": "401 Unauthorized: please run codex login"}})
        sys.exit(1)
    if scenario == "crash":
        sys.stderr.write("boom\n")
        sys.exit(3)
    out({"type": "item.completed", "item": {"id": "i0", "type": "error",
                                            "message": "предупреждение, не ошибка хода"}})
    out({"type": "item.started", "item": {"id": "i1", "type": "command_execution",
                                          "command": "powershell -Command 'Get-ChildItem'", "status": "in_progress"}})
    out({"type": "item.completed", "item": {"id": "i1", "type": "command_execution",
                                            "command": "powershell -Command 'Get-ChildItem'", "exit_code": 0,
                                            "status": "completed"}})
    path = os.path.join(os.getcwd(), "essa-ai", "content", "x", "post.md")
    out({"type": "item.started", "item": {"id": "i2", "type": "file_change",
                                          "changes": [{"path": path, "kind": "add"}], "status": "in_progress"}})
    out({"type": "item.completed", "item": {"id": "i2", "type": "file_change",
                                            "changes": [{"path": path, "kind": "add"}], "status": "completed"}})
    if scenario == "schema":
        verdicts = os.environ.get("FAKE_CODEX_VERDICT", "pass")
        out({"type": "item.completed", "item": {"id": "i3", "type": "agent_message",
                                                "text": json.dumps({"verdict": "fix", "problems": ["промежуточный"],
                                                                    "checked": []}, ensure_ascii=False)}})
        out({"type": "item.completed", "item": {"id": "i4", "type": "agent_message",
                                                "text": json.dumps({"verdict": verdicts, "problems": [],
                                                                    "checked": ["post.md"]}, ensure_ascii=False)}})
    else:
        out({"type": "item.completed", "item": {"id": "i3", "type": "agent_message", "text": "Смотрю папку."}})
        out({"type": "item.completed", "item": {"id": "i4", "type": "agent_message",
                                                "text": "Готово в Codex: пост в essa-ai/content/x/post.md"}})
    out({"type": "turn.completed", "usage": {"input_tokens": 10, "output_tokens": 5}})


if __name__ == "__main__":
    main()
