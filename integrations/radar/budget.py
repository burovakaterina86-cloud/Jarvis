"""Потолок трат: HikerAPI платный — максимум запросов за прогон, без бесконечного перебора."""
from __future__ import annotations

from dataclasses import dataclass


class BudgetExceeded(Exception):
    """Потолок запросов за прогон исчерпан — прогон останавливается честно."""

    def __init__(self, spent: int, limit: int):
        super().__init__(f"{spent}/{limit} запросов")
        self.spent = spent
        self.limit = limit


@dataclass
class RequestBudget:
    limit: int
    spent: int = 0

    def spend(self, n: int = 1) -> None:
        if self.spent + n > self.limit:
            raise BudgetExceeded(self.spent, self.limit)
        self.spent += n
