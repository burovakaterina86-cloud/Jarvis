"""Gateway JARVIS: Telegram — основной интерфейс владелицы.

Запуск: `python -m integrations.telegram` (или `start.bat`).
Подмодули: gateway (бот и команды), voice (распознавание), files (inbox и статусы),
status (одно статус-сообщение и разбиение ответов).
"""
from __future__ import annotations

__all__ = ["run", "main", "Gateway"]


def __getattr__(name: str):
    # ленивый импорт: тестам подмодулей не нужна библиотека telegram
    if name in __all__:
        from integrations.telegram import gateway
        return getattr(gateway, name)
    raise AttributeError(name)
