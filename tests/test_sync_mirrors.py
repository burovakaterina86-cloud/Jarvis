"""Проверка зеркал навыков и помощников для других CLI (P1.5, аудит 2026-10-05).

`.agents/skills/` — копия `.claude/skills/`, `.codex/agents/*.toml` — копия `.claude/agents/*.md`.
Скрипт только сообщает о расхождениях и ничего не копирует.
"""
import importlib.util
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "scripts" / "sync_mirrors.py"

spec = importlib.util.spec_from_file_location("sync_mirrors", SCRIPT)
sync = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sync)

AGENT_MD = "---\nname: {n}\ndescription: {d}\ntools: Read\n---\n\n{body}\n"
AGENT_TOML = 'name = "{n}"\ndescription = "{d}"\ndeveloper_instructions = """\n{body}"""\n'


def tree(root, files: dict):
    for rel, text in files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(text if isinstance(text, bytes) else text.encode("utf-8"))


def in_sync(root):
    tree(root, {
        ".claude/skills/a/SKILL.md": "навык а",
        ".claude/skills/a/references/r.md": "справка",
        ".agents/skills/a/SKILL.md": "навык а",
        ".agents/skills/a/references/r.md": "справка",
        ".claude/agents/x.md": AGENT_MD.format(n="x", d="Помощник.", body="# X\n\nДелай."),
        ".codex/agents/x.toml": AGENT_TOML.format(n="x", d="Помощник.", body="# X\r\n\r\nДелай."),
    })


def test_identical_mirrors_report_nothing(tmp_path):
    in_sync(tmp_path)
    assert sync.compare(tmp_path) == []
    assert sync.main(["--check", "--root", str(tmp_path)]) == 0


def test_differences_are_named(tmp_path):
    in_sync(tmp_path)
    tree(tmp_path, {
        ".agents/skills/a/SKILL.md": "старая версия",
        ".claude/skills/b/SKILL.md": "новый навык",
        ".agents/skills/old/SKILL.md": "удалённый",
        ".codex/agents/x.toml": AGENT_TOML.format(n="x", d="Помощник.", body="# X\n\nДругое."),
    })
    report = sync.compare(tmp_path)
    assert "расходится: .agents/skills/a/SKILL.md" in report
    assert "нет копии: .agents/skills/b/SKILL.md" in report
    assert "лишнее в копии: .agents/skills/old/SKILL.md" in report
    assert "расходится: .codex/agents/x.toml" in report
    assert sync.main(["--check", "--root", str(tmp_path)]) == 1


def test_missing_codex_agent_and_pycache_ignored(tmp_path):
    in_sync(tmp_path)
    tree(tmp_path, {
        ".claude/agents/y.md": AGENT_MD.format(n="y", d="Ещё.", body="Тело."),
        ".claude/skills/a/__pycache__/m.cpython-312.pyc": b"\x00",
    })
    assert sync.compare(tmp_path) == ["нет копии: .codex/agents/y.toml"]


def test_script_never_writes(tmp_path):
    in_sync(tmp_path)
    tree(tmp_path, {".claude/skills/b/SKILL.md": "новый"})
    before = sorted(p.relative_to(tmp_path).as_posix() for p in tmp_path.rglob("*"))
    sync.main(["--check", "--root", str(tmp_path)])
    after = sorted(p.relative_to(tmp_path).as_posix() for p in tmp_path.rglob("*"))
    assert before == after


def test_runs_on_the_real_repo_and_prints_a_report():
    proc = subprocess.run([sys.executable, str(SCRIPT), "--check"], capture_output=True, cwd=str(REPO),
                          env={"PYTHONIOENCODING": "utf-8", "SYSTEMROOT": "C:\\Windows"})
    assert proc.returncode in (0, 1)
    out = proc.stdout.decode("utf-8")
    assert ("зеркала совпадают" in out) or ("расхождений:" in out)


def test_line_endings_alone_are_not_a_difference(tmp_path):
    in_sync(tmp_path)
    tree(tmp_path, {".claude/skills/a/SKILL.md": b"line1\nline2\n",
                    ".agents/skills/a/SKILL.md": b"line1\r\nline2\r\n"})
    assert sync.compare(tmp_path) == []
