"""Дымовой тест с реальным `claude -p` (по подписке). В общий прогон не входит.

Запуск: .venv\\Scripts\\python.exe tests\\smoke_real_claude.py
или:    .venv\\Scripts\\python.exe -m pytest -q -m smoke tests/smoke_real_claude.py
"""
import asyncio
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from runtime import claude_bridge  # noqa: E402

PROMPT = "Ответь одним словом: привет. Не используй инструменты."


async def _turn():
    # ровно то окружение, что мост даёт claude в бою
    return await claude_bridge.run_turn(PROMPT, None, None, task="smoke",
                                        env=claude_bridge.build_env(os.environ))


@pytest.mark.smoke
async def test_real_claude_says_hello():
    res = await _turn()
    assert res.status == "ok", (res.status, res.error)
    assert res.session_id
    assert "привет" in res.text.lower()


if __name__ == "__main__":
    r = asyncio.run(_turn())
    print(f"status={r.status} session={bool(r.session_id)} cost={r.cost_usd} "
          f"text={r.text[:200]!r} error={(r.error or '')[:300]!r}")
