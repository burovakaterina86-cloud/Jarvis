"""Секреты не уходят в дочерние процессы: Claude, Codex, node, фоновые работы, ffmpeg."""
import os
from pathlib import Path

from runtime import claude_bridge, secretenv

DIRTY = {"PATH": "/bin", "SYSTEMROOT": "C:\\Windows", "USERPROFILE": "C:\\u", "JARVIS_TASK_ID": "t1",
         "CLAUDE_CODE_GIT_BASH_PATH": "C:\\git\\bash.exe", "CLAUDECODE": "1",
         "TELEGRAM_BOT_TOKEN": "123456789:AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA", "APIFY_TOKEN": "a", "KIE_API_KEY": "k",
         "GROQ_API_KEY": "g", "GROQ_KEY": "g2", "OPENAI_API_KEY": "o", "AWS_SECRET_ACCESS_KEY": "s",
         "GITHUB_TOKEN": "gh", "DB_PASSWORD": "p", "SSH_AUTH_SOCK": "x", "MY_PRIVATE_THING": "z"}


def test_scrub_drops_secrets_and_keeps_the_rest():
    out = secretenv.scrub(DIRTY)
    assert set(out) == {"PATH", "SYSTEMROOT", "USERPROFILE", "JARVIS_TASK_ID", "CLAUDE_CODE_GIT_BASH_PATH"}


def test_claude_child_env_has_no_service_keys():
    env = claude_bridge.build_env(DIRTY)
    for name in ("APIFY_TOKEN", "KIE_API_KEY", "GROQ_API_KEY", "TELEGRAM_BOT_TOKEN", "OPENAI_API_KEY", "CLAUDECODE"):
        assert name not in env
    assert env["CLAUDE_CODE_GIT_BASH_PATH"] and env["JARVIS_TASK_ID"] == "t1"


def test_lookup_reads_the_one_key_and_does_not_touch_environ(tmp_path, monkeypatch):
    dotenv = tmp_path / ("." + "env")
    dotenv.write_text("# c\nAPIFY_TOKEN=apify-1\nexport KIE_API_KEY='kie-1'\nTELEGRAM_BOT_TOKEN=tg\n", encoding="utf-8")
    monkeypatch.delenv("APIFY_TOKEN", raising=False)
    assert secretenv.lookup("APIFY_TOKEN", dotenv=dotenv) == "apify-1"
    assert secretenv.lookup("KIE_API_KEY", dotenv=dotenv) == "kie-1"
    assert secretenv.lookup("NOPE", dotenv=dotenv) is None
    assert "APIFY_TOKEN" not in os.environ
    assert secretenv.lookup("APIFY_TOKEN", environ={"APIFY_TOKEN": "from-env"}, dotenv=dotenv) == "from-env"


def test_load_dotenv_only_loads_the_requested_keys(tmp_path, monkeypatch):
    from integrations.radar import keys
    dotenv = tmp_path / ("." + "env")
    dotenv.write_text("APIFY_TOKEN=a1\nTELEGRAM_BOT_TOKEN=tg\nKIE_API_KEY=k\n", encoding="utf-8")
    for name in ("APIFY_TOKEN", "TELEGRAM_BOT_TOKEN", "KIE_API_KEY"):
        monkeypatch.delenv(name, raising=False)
    keys.load_dotenv(dotenv, only=("APIFY_TOKEN",))
    assert os.environ.get("APIFY_TOKEN") == "a1"
    assert "TELEGRAM_BOT_TOKEN" not in os.environ and "KIE_API_KEY" not in os.environ
    monkeypatch.delenv("APIFY_TOKEN")


def test_montage_children_get_groq_only_where_needed(monkeypatch):
    from integrations.montage import config, render
    monkeypatch.setenv("GROQ_API_KEY", "gq")
    monkeypatch.setenv("APIFY_TOKEN", "ap")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "tg")
    assert config.child_env()["GROQ_API_KEY"] == "gq"                  # roughcut/captions ждут именно его
    assert "APIFY_TOKEN" not in config.child_env() and "TELEGRAM_BOT_TOKEN" not in config.child_env()
    page_env = render.env_for(Path("work/overlay.html"), Path("frames"), 1.0)
    assert not any(secretenv.is_secret_name(k) for k in page_env)      # node и браузер — без ключей


def test_background_jobs_env_is_clean(monkeypatch):
    from integrations.jobs import runner
    monkeypatch.setenv("APIFY_TOKEN", "ap")
    monkeypatch.setenv("KIE_API_KEY", "k")
    env = runner._clean_env()
    assert "APIFY_TOKEN" not in env and "KIE_API_KEY" not in env and env["PYTHONUTF8"] == "1"
