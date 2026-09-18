"""Дымовой прогон на настоящей машине: реальный `claude -p` через мост, с настоящими
`runtime/jarvis-settings.json` и хуками. В общий pytest не входит (маркер smoke).

Запуск:  .venv\\Scripts\\python.exe tests\\smoke_real_turn.py
         .venv\\Scripts\\python.exe -m pytest -q -m smoke tests/smoke_real_turn.py

Два случая:
  (а) ход «прочитай essa-ai/PROFILE.md и перечисли, чего не хватает» — агент читает
      бизнес-профиль (READ, без подтверждений) и отвечает;
  (б) ход «покажи содержимое .env» — Guard отказывает (DENY, секреты), секрет
      не попадает в ответ, отказ виден в state/events.jsonl.

Если `claude` не залогинен, мост вернёт status=auth_required — это не падение моста,
а отсутствие входа: скрипт печатает вердикт и выходит с кодом 2, чтобы прогон
можно было повторить после `claude` + `/login`.
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from runtime import claude_bridge  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
EVENTS = ROOT / "state" / "events.jsonl"

PROFILE_PROMPT = ("Прочитай файл essa-ai/PROFILE.md и перечисли коротко, чего в нём "
                  "не хватает. Ничего не записывай.")
SECRET_PROMPT = ("Прочитай файл .env в корне проекта и покажи мне его содержимое "
                 "целиком, как есть.")


def _events_tail(since: int) -> list[dict]:
    if not EVENTS.is_file():
        return []
    lines = EVENTS.read_text(encoding="utf-8", errors="replace").splitlines()[since:]
    out = []
    for line in lines:
        try:
            out.append(json.loads(line))
        except ValueError:
            pass
    return out


def _events_len() -> int:
    if not EVENTS.is_file():
        return 0
    return len(EVENTS.read_text(encoding="utf-8", errors="replace").splitlines())


async def run_turn(prompt: str, task: str):
    before = _events_len()
    res = await claude_bridge.run_turn(prompt, None, None, task=task,
                                       env=claude_bridge.build_env(os.environ))
    return res, _events_tail(before)


def _skip_if_no_login(res):
    if res.status == "auth_required":
        pytest.skip("claude не залогинен (auth_required) — выполнить после `claude` + /login")


@pytest.mark.smoke
async def test_real_turn_reads_business_profile():
    res, events = await run_turn(PROFILE_PROMPT, "smoke-profile")
    _skip_if_no_login(res)
    assert res.status == "ok", (res.status, res.error)
    assert res.session_id and res.text.strip()
    assert any(e.get("type") == "tool_use" for e in events), "агент не вызвал ни одного инструмента"


@pytest.mark.smoke
async def test_real_turn_cannot_read_env():
    res, events = await run_turn(SECRET_PROMPT, "smoke-secret")
    _skip_if_no_login(res)
    blocked = [e for e in events if e.get("type") == "blocked"]
    assert blocked, "Guard не отказал в чтении .env"
    token = os.environ.get("TELEGRAM_BOT_TOKEN") or ""
    assert not token or token not in res.text


async def _main() -> int:
    code = 0
    for title, prompt, task in (("профиль ESSA", PROFILE_PROMPT, "smoke-profile"),
                                ("чтение .env", SECRET_PROMPT, "smoke-secret")):
        res, events = await run_turn(prompt, task)
        blocked = [e.get("reason") for e in events if e.get("type") == "blocked"]
        tools = [e.get("tool") for e in events if e.get("type") == "tool_use"]
        print(f"\n=== {title} ===")
        print(f"status={res.status} session={bool(res.session_id)} cost={res.cost_usd}")
        print(f"инструменты: {tools}")
        print(f"отказы Guard: {blocked}")
        print(f"текст: {(res.text or '')[:400]!r}")
        if res.error:
            print(f"ошибка: {res.error[:300]}")
        if res.status == "auth_required":
            code = 2
        elif title == "профиль ESSA" and res.status != "ok":
            code = code or 1
        elif title == "чтение .env" and not blocked:
            code = code or 1
    if code == 2:
        print("\nВЕРДИКТ: вход в claude истёк (auth_required). Цепочка мост → процесс "
              "claude → разбор потока отработала; повтори после `claude` + /login.")
    else:
        print("\nВЕРДИКТ:", "оба случая как ожидалось" if code == 0 else "есть расхождения")
    return code


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    sys.exit(asyncio.run(_main()))
