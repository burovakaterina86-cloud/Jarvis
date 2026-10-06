"""Фоновые работы бота: проверка запроса, очередь, запуск, письмо о результате, потеря при перезапуске."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from integrations import jobs
from integrations.jobs.runner import MAX_RUNNING, JobRunner

REMAKE = ["-m", "integrations.montage.run", "remake", "--work", "outbox/montage/x", "--spec", "outbox/montage/x/spec.json"]


def good(**kw):
    return {"title": "Сборка рилса", "argv": REMAKE, "files": ["outbox/x.mp4"], "done": "Ролик собран.", **kw}


# ---------- проверка запроса: произвольный код через эту дверь не пройдёт ----------

def test_a_good_request_has_no_problems(tmp_path):
    assert jobs.validate(good(), tmp_path) == []


@pytest.mark.parametrize("bad, fragment", [
    (good(argv=["-c", "import os; os.system('x')"]), "-m"),
    (good(argv=["-m", "os", "system"]), "белого списка"),
    (good(argv=["-m", "integrations.montage.run\nrm"]), "белого списка"),
    (good(argv=["notepad.exe", "x"]), "-m"),
    (good(argv=["-m"]), "argv"),
    (good(argv=["-m", "integrations.montage.run", "a\nb"]), "перевод"),
    (good(files=["../../etc/passwd"]), "вне папки"),
    (good(files=["state/secrets/approvals.token"]), "защищённого"),
    (good(files=["./" + ".en" + "v.local"]), "защищённого"),
    (good(files=["sub/../state/jobs/x.json"]), "защищённого"),
    (good(files=[".env"]), "защищённого"),
    (good(files=["a", "b", "c", "d", "e", "f", "g"]), "не больше"),
    (good(title=""), "title"),
    (good(title="x" * 200), "title"),
    ({"title": "x"}, "argv"),
])
def test_bad_requests_are_refused(bad, fragment, tmp_path):
    problems = jobs.validate(bad, tmp_path)
    assert problems and any(fragment in p for p in problems), problems


def test_submit_writes_a_request_file_only_when_valid(tmp_path):
    job_id, problems = jobs.submit("Сборка", REMAKE, ["outbox/x.mp4"], "готово", root=tmp_path)
    assert problems == [] and (tmp_path / "jobs" / "requests" / f"{job_id}.json").is_file()
    job_id2, problems2 = jobs.submit("Плохая", ["-c", "x"], root=tmp_path)
    assert job_id2 == "" and problems2
    assert len(list((tmp_path / "jobs" / "requests").glob("*.json"))) == 1


def test_cli_submit_prints_that_the_turn_should_end(tmp_path, monkeypatch, capsys):
    from integrations.jobs import __main__ as cli
    monkeypatch.setattr(jobs, "ROOT", tmp_path)
    monkeypatch.setattr(cli, "submit", lambda *a, **k: jobs.submit(*a, root=tmp_path, **k))
    assert cli.main(["submit", "--title", "Сборка", "--file", "outbox/x.mp4", "--done", "ок", "--", *REMAKE]) == 0
    assert "закончи ход" in capsys.readouterr().out
    assert cli.main(["submit", "--title", "Плохая", "--", "-c", "x"]) == 2


# ---------- запускатель ----------

class FakeProc:
    def __init__(self, rcs):
        self.rcs, self.pid, self.killed = list(rcs), 4242, False

    def poll(self):
        return self.rcs.pop(0) if len(self.rcs) > 1 else self.rcs[0]

    def kill(self):
        self.killed = True


def make_runner(tmp_path, procs, clock=None):
    mail, spawned = [], []
    now = {"t": 1000.0}

    def popen(cmd, **kw):
        spawned.append((cmd, kw))
        return procs[len(spawned) - 1]

    runner = JobRunner(tmp_path, post=lambda text, files: mail.append((text, files)), popen=popen,
                       clock=clock or (lambda: now["t"]), env={"PATH": "x"})
    return runner, mail, spawned, now


def put(tmp_path, job_id="aaa", **kw):
    folder = tmp_path / "jobs" / "requests"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / f"{job_id}.json").write_text(json.dumps(good(**kw), ensure_ascii=False), encoding="utf-8")


def test_job_runs_in_bot_process_and_result_is_mailed_with_the_file(tmp_path):
    (tmp_path / "outbox").mkdir()
    (tmp_path / "outbox" / "x.mp4").write_bytes(b"video")
    runner, mail, spawned, now = make_runner(tmp_path, [FakeProc([None, 0])])
    put(tmp_path)
    runner.tick()
    assert len(spawned) == 1 and spawned[0][0][1:4] == ["-m", "integrations.montage.run", "remake"]
    assert spawned[0][1]["cwd"] == str(tmp_path) and "TELEGRAM_BOT_TOKEN" not in spawned[0][1]["env"]
    assert mail == [] and not list((tmp_path / "jobs" / "requests").glob("*.json"))   # запрос принят и снят
    runner.tick()
    assert mail == []                                                 # ещё идёт
    now["t"] += 240
    runner.tick()
    text, files = mail[0]
    assert text.startswith("Готово: Сборка рилса") and "4 мин" in text and "Ролик собран." in text
    assert files == ["outbox/x.mp4"]
    state = json.loads((tmp_path / "state" / "jobs" / "aaa.json").read_text(encoding="utf-8"))
    assert state["status"] == "done" and state["rc"] == 0
    runner.tick()
    assert len(mail) == 1                                             # второй раз письма нет


def test_failure_is_mailed_with_log_tail_and_secrets_are_hidden(tmp_path):
    runner, mail, spawned, _ = make_runner(tmp_path, [FakeProc([1])])
    put(tmp_path, fail="Пересоберу после правки.")
    runner.tick()
    log = tmp_path / "state" / "jobs" / "aaa.log"
    log.write_text("строка 1\nошибка: ffmpeg упал\nAPIFY_TOKEN=apify_api_SECRETSECRETSECRET123\n", encoding="utf-8")
    runner.tick()
    text, files = mail[0]
    assert text.startswith("Не получилось: Сборка рилса (код 1)") and "Пересоберу после правки." in text
    assert "ffmpeg упал" in text and "SECRETSECRET" not in text and files == []


def test_missing_result_file_is_reported_instead_of_silence(tmp_path):
    runner, mail, _, _ = make_runner(tmp_path, [FakeProc([0])])
    put(tmp_path)
    runner.tick()
    runner.tick()
    assert "файла нет: outbox/x.mp4" in mail[0][0] and mail[0][1] == []


def test_rejected_request_is_not_run_and_owner_is_told_why(tmp_path):
    runner, mail, spawned, _ = make_runner(tmp_path, [])
    folder = tmp_path / "jobs" / "requests"
    folder.mkdir(parents=True)
    (folder / "evil.json").write_text(json.dumps({"title": "Хитрая", "argv": ["-c", "x"], "files": []}), encoding="utf-8")
    runner.tick()
    assert spawned == [] and "не запустил" in mail[0][0] and (folder / "evil.rejected").exists()


def test_no_more_than_max_running_and_the_rest_waits(tmp_path):
    procs = [FakeProc([None]) for _ in range(MAX_RUNNING + 1)]
    runner, mail, spawned, _ = make_runner(tmp_path, procs)
    for i in range(MAX_RUNNING + 1):
        put(tmp_path, job_id=f"j{i}")
    runner.tick()
    assert len(spawned) == MAX_RUNNING
    states = {s["id"]: s["status"] for s in jobs.read_states(tmp_path)}
    assert sorted(states.values()) == ["queued"] + ["running"] * MAX_RUNNING
    procs[0].rcs = [0]
    runner.tick()                                                     # одна закончилась — следом стартует ждущая
    assert len(spawned) == MAX_RUNNING + 1


def test_job_left_running_by_a_previous_bot_is_reported_as_interrupted(tmp_path):
    state = tmp_path / "state" / "jobs"
    state.mkdir(parents=True)
    (state / "old.json").write_text(json.dumps({"id": "old", "title": "Сборка", "argv": REMAKE, "files": [],
                                                "status": "running", "queued_at": 1, "started_at": 2}), encoding="utf-8")
    runner, mail, _, _ = make_runner(tmp_path, [])
    runner.tick()
    assert "прервалась" in mail[0][0] and json.loads((state / "old.json").read_text(encoding="utf-8"))["status"] == "interrupted"
    runner.tick()
    assert len(mail) == 1


def test_runaway_job_is_killed_after_two_hours(tmp_path):
    proc = FakeProc([None])
    runner, mail, _, now = make_runner(tmp_path, [proc])
    put(tmp_path)
    runner.tick()
    now["t"] += 2 * 60 * 60 + 5
    runner.tick()
    assert proc.killed and "больше двух часов" in mail[0][0]


# ---------- бот и защита ----------

async def test_gateway_ticks_the_runner_from_its_watch_loop(tmp_path):
    from tests.test_telegram import make_gateway
    g = make_gateway(tmp_path)
    calls = []

    class Stub:
        def tick(self):
            calls.append(1)

    g.jobs = Stub()
    await g.check_jobs()
    assert calls == [1]


def test_guard_lets_the_agent_submit_and_check_but_not_run_arbitrary_code(tmp_path):
    from tests import test_guard as g
    (tmp_path / "state" / "secrets").mkdir(parents=True)
    env = {"JARVIS_TASK_ID": "t"}
    submit = ('python -m integrations.jobs submit --title "Сборка" --file outbox/x.mp4 --done "ок" -- '
              '-m integrations.montage.run remake --work outbox/montage/x --spec outbox/montage/x/spec.json')
    assert g.decide(g.ev("Bash", command=submit), tmp_path, env=env).action == "allow"
    assert g.decide(g.ev("Bash", command="python -m integrations.jobs status"), tmp_path, env=env).action == "allow"
    assert g.decide(g.ev("Bash", command="python -c \"import os\""), tmp_path, env=env).action == "ask"
