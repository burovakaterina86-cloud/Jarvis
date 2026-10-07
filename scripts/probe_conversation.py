"""Безопасный живой запрос собеседнику: без инструментов и без Telegram."""
from __future__ import annotations

import argparse
import asyncio
import json
import tempfile
import time
from pathlib import Path

from runtime import claude2_bridge, claude_bridge, conversation, events


async def probe(account: str) -> int:
    bridge = claude2_bridge if account == "claude2" else claude_bridge
    with tempfile.TemporaryDirectory(prefix="jarvis-conversation-probe-") as folder:
        old_events = events.EVENTS_PATH
        events.EVENTS_PATH = Path(folder) / "events.jsonl"
        start = time.monotonic()
        try:
            run_id = "conversation-probe"
            turn = asyncio.create_task(bridge.run_turn(
                "Владелица спрашивает: ты здесь? Ответь одним предложением; action=reply, role и brief пустые.",
                run_id=run_id, options=conversation.OPTIONS))
            done, _ = await asyncio.wait({turn}, timeout=conversation.TIMEOUT_SEC)
            if not done:
                bridge.stop(run_id)
            result = await turn
            decision = conversation.parse(result)
            print(json.dumps({"account": account, "model": "haiku", "status": result.status,
                "elapsed_sec": round(time.monotonic() - start, 2), "decision_ok": decision is not None,
                "action": decision["action"] if decision else None,
                "tool_uses": result.tool_uses}, ensure_ascii=False))
            return 0 if decision and decision["action"] == "reply" and result.tool_uses <= 1 else 1
        finally:
            events.EVENTS_PATH = old_events


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--account", choices=("claude", "claude2"), default="claude")
    return asyncio.run(probe(parser.parse_args().account))


if __name__ == "__main__":
    raise SystemExit(main())
