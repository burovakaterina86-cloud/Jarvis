"""REST-клиент Apify и потолок трат в долларах.

Коннектор Apify (MCP) в мост JARVIS не подключается — ходим напрямую по REST, как радар.
Токен — только в заголовке `Authorization`, не в адресе. Ключ — `APIFY_TOKEN` в `.env`
(значение не читаем в лог и не печатаем).

Цены — из инструкции агента (снято 2026-09, могут меняться): расчёт заранее, до запуска актора.
"""
from __future__ import annotations

import json
import os
import urllib.request
from dataclasses import dataclass
from typing import Any, Protocol

from integrations.radar.keys import load_dotenv

# актор → доллары за один результат (рилс, пост, расшифровка)
UNIT_COST_USD: dict[str, float] = {
    "memo23~instagram-reels-search-scraper": 0.0013,
    "scraping_solutions~instagram-boolean-search-scraper-posts-reels": 0.00145,
    "apify~instagram-reel-scraper": 0.0023,
    "apify~instagram-post-scraper": 0.0015,
    "apify~instagram-scraper": 0.0023,
    "steadyfetch~instagram-reel-transcript-scraper": 0.01,
}
#: Булев поиск берёт ещё $0,01 за страницу выдачи (≈ по 25 рилсов).
BOOLEAN_PAGE_USD = 0.01
BOOLEAN_PAGE_SIZE = 25


class BudgetExceeded(Exception):
    def __init__(self, spent: float, limit: float, asked: float):
        super().__init__(f"потолок ${limit:.2f}: потрачено ${spent:.2f}, запрос ещё на ${asked:.2f}")
        self.spent, self.limit, self.asked = spent, limit, asked


class KeyMissing(Exception):
    """Нет `APIFY_TOKEN` в окружении."""


@dataclass
class UsdBudget:
    limit: float
    spent: float = 0.0

    def charge(self, amount: float) -> None:
        """Списать заранее посчитанную сумму или остановить прогон — до запуска актора."""
        if self.spent + amount > self.limit + 1e-9:
            raise BudgetExceeded(self.spent, self.limit, amount)
        self.spent = round(self.spent + amount, 6)


def estimate(actor: str, results: int) -> float:
    unit = UNIT_COST_USD.get(actor)
    if unit is None:
        raise KeyError(f"нет цены для актора {actor}")
    cost = unit * results
    if actor.startswith("scraping_solutions~"):
        cost += BOOLEAN_PAGE_USD * -(-results // BOOLEAN_PAGE_SIZE)
    return round(cost, 6)


class ActorClient(Protocol):
    def run(self, actor: str, payload: dict[str, Any]) -> list[dict[str, Any]]: ...


def require_token(env: dict[str, str] | None = None) -> str:
    if env is None:
        load_dotenv(only=("APIFY_TOKEN",))
        env = os.environ  # type: ignore[assignment]
    token = env.get("APIFY_TOKEN")
    if not token:
        raise KeyMissing("нет ключа в окружении: APIFY_TOKEN")
    return token


API = "https://api.apify.com/v2"
FINAL_STATES = {"SUCCEEDED", "FAILED", "ABORTED", "TIMED-OUT"}


class ApifyRunError(Exception):
    pass


class ApifyRestClient:
    """Запуск актора, опрос до конца и скачивание датасета постранично.

    Синхронный `run-sync-…` не годится: Apify обрывает его примерно на 5 минутах, а поиск по тегам
    идёт дольше. Поэтому: старт → опрос статуса → `datasets/<id>/items`.
    """

    def __init__(self, token: str, max_wait_sec: int = 25 * 60, poll_sec: float = 5.0,
                 sleep=None, opener=None):
        import time
        self._token = token
        self._max_wait = max_wait_sec
        self._poll = poll_sec
        self._sleep = sleep or time.sleep
        self._open = opener or urllib.request.urlopen

    def _call(self, method: str, path: str, body: dict[str, Any] | None = None) -> Any:
        req = urllib.request.Request(
            API + path, method=method,
            data=json.dumps(body).encode("utf-8") if body is not None else None,
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {self._token}",
                     "User-Agent": "JARVIS-content-plan/1.0"})
        with self._open(req, timeout=120) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def run(self, actor: str, payload: dict[str, Any]) -> list[dict[str, Any]]:
        started = self._call("POST", f"/acts/{actor}/runs", payload)["data"]
        run_id, waited = started["id"], 0.0
        state = started.get("status")
        while state not in FINAL_STATES:
            if waited >= self._max_wait:
                self._call("POST", f"/actor-runs/{run_id}/abort")
                raise ApifyRunError(f"{actor}: не завершился за {self._max_wait // 60} мин, остановлен")
            self._sleep(self._poll)
            waited += self._poll
            state = self._call("GET", f"/actor-runs/{run_id}")["data"]["status"]
        # Даже у оборванного запуска в датасете могло накопиться — забираем, что есть.
        dataset = self._call("GET", f"/actor-runs/{run_id}")["data"]["defaultDatasetId"]
        items: list[dict[str, Any]] = []
        while True:
            page = self._call("GET", f"/datasets/{dataset}/items?clean=1&limit=1000&offset={len(items)}")
            items += page
            if len(page) < 1000:
                break
        if state != "SUCCEEDED" and not items:
            raise ApifyRunError(f"{actor}: запуск завершился со статусом {state}")
        return items
