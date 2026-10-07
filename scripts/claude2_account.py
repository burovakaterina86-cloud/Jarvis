"""Отдельный вход второго Claude через официальный CLI; проверка не выводит данные аккаунтов."""
from __future__ import annotations

import argparse
import json
import os
import subprocess
from pathlib import Path

from runtime import claude2_bridge, claude_bridge


def summary(primary: dict, second: dict) -> dict:
    first_email, second_email = primary.get("email"), second.get("email")
    distinct = (str(first_email).casefold() != str(second_email).casefold()
                if primary.get("loggedIn") and first_email and second_email else None)
    return {"logged_in": second.get("loggedIn") is True,
            "subscription_login": second.get("authMethod") == "claude.ai",
            "different_account": distinct}


def status(env) -> dict:
    result = subprocess.run(["claude", "auth", "status", "--json"], env=env,
                            capture_output=True, text=True, encoding="utf-8", timeout=30)
    try:
        data = json.loads(result.stdout)
        return data if isinstance(data, dict) else {}
    except ValueError:
        return {}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--login", action="store_true")
    parser.add_argument("--probe", action="store_true")
    args = parser.parse_args(argv)
    base = claude_bridge.build_env(dict(os.environ))
    folder = Path(os.environ.get("JARVIS_CLAUDE2_DIR") or claude2_bridge.DEFAULT_CONFIG_DIR)
    second_env = {**base, "CLAUDE_CONFIG_DIR": str(folder)}
    if args.login:
        folder.mkdir(parents=True, exist_ok=True)
        print("Войдите ВТОРЫМ аккаунтом Claude с подпиской. Если браузер выбрал первый — смените аккаунт.", flush=True)
        result = subprocess.run(["claude", "auth", "login", "--claudeai"], env=second_env)
        if result.returncode:
            return result.returncode
    info = summary(status(base), status(second_env))
    print(json.dumps(info, ensure_ascii=False))
    if args.probe and info["logged_in"] and info["subscription_login"] and info["different_account"] is not False:
        result = subprocess.run(["claude", "-p", "Ответь только словом ГОТОВО. Не используй инструменты.",
                                 "--output-format", "json", "--tools", "", "--max-turns", "1",
                                 "--permission-mode", "dontAsk", "--no-session-persistence", "--setting-sources", ""],
                                env=second_env, cwd=folder, capture_output=True, text=True, encoding="utf-8", timeout=90)
        try:
            data = json.loads(result.stdout)
        except ValueError:
            data = {}
        ok = result.returncode == 0 and data.get("is_error") is False and "ГОТОВО" in str(data.get("result", "")).upper()
        print(json.dumps({"probe_ok": ok}))
        return 0 if ok else 2
    return 0 if info["logged_in"] and info["subscription_login"] and info["different_account"] is not False else 1


if __name__ == "__main__":
    raise SystemExit(main())
