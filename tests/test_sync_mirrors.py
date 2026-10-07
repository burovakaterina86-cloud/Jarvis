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


# ---------- правило зеркала и пересборка (P4.2: зеркала поддерживаются — она пользуется Codex) ----------

def test_project_rule_paths_are_rewritten(tmp_path):
    in_sync(tmp_path)
    tree(tmp_path, {".claude/skills/a/SKILL.md": "читай .claude/rules/x.md, .claude/skills/a и CLAUDE.md",
                    ".agents/skills/a/SKILL.md": "читай .agents/rules/x.md, .agents/skills/a и AGENTS.md"})
    assert sync.compare(tmp_path) == []


def test_rewrite_points_only_at_folders_that_exist():
    """Раньше `.claude` → `.Codex` (такой папки нет): ссылки вели в никуда, на Linux регистр ломал путь вовсе."""
    text = (b"`.claude/rules/safety.md`, `.claude/skills/site-builder/scripts/p.py`, "
            b"`.claude/agents/researcher.md`, `.claude/hooks/guard.py`, CLAUDE.md")
    out = sync.rewrite(text)
    assert b".Codex" not in out
    assert out == (b"`.agents/rules/safety.md`, `.agents/skills/site-builder/scripts/p.py`, "
                   b"`.codex/agents/researcher.toml`, `.claude/hooks/guard.py`, AGENTS.md")


def test_rules_are_mirrored_and_drift_is_reported(tmp_path):
    in_sync(tmp_path)
    tree(tmp_path, {".claude/rules/safety.md": "см. .claude/rules/approvals.md"})
    assert sync.compare(tmp_path) == ["нет копии: .agents/rules/safety.md"]
    sync.write(tmp_path)
    assert (tmp_path / ".agents/rules/safety.md").read_text(encoding="utf-8") == "см. .agents/rules/approvals.md"
    assert sync.compare(tmp_path) == []
    (tmp_path / ".agents/rules/safety.md").write_text("правка руками", encoding="utf-8")
    assert sync.compare(tmp_path) == ["расходится: .agents/rules/safety.md"]


def test_raw_copy_without_rewrite_is_drift(tmp_path):
    in_sync(tmp_path)
    tree(tmp_path, {".claude/skills/a/SKILL.md": "читай .claude/rules",
                    ".agents/skills/a/SKILL.md": "читай .claude/rules"})
    assert sync.compare(tmp_path) == ["расходится: .agents/skills/a/SKILL.md"]


def test_autopilot_is_verbatim(tmp_path):
    in_sync(tmp_path)
    tree(tmp_path, {".claude/skills/autopilot/SKILL.md": "~/.claude/skills",
                    ".agents/skills/autopilot/SKILL.md": "~/.claude/skills"})
    assert sync.compare(tmp_path) == []


def test_binary_line_ending_noise_is_not_drift(tmp_path):
    in_sync(tmp_path)
    tree(tmp_path, {".claude/skills/a/p.jpg": b"\xff\xd8\r\n\x00", ".agents/skills/a/p.jpg": b"\xff\xd8\n\x00"})
    assert sync.compare(tmp_path) == []


def test_write_rebuilds_everything_from_claude(tmp_path):
    in_sync(tmp_path)
    body = 'Читай .claude/rules и CLAUDE.md.\nПуть C:\\Users\\x и тройные кавычки """ внутри.'
    tree(tmp_path, {
        ".agents/skills/a/SKILL.md": "старая версия",
        ".claude/skills/b/SKILL.md": "новый навык про .claude",
        ".agents/skills/old/SKILL.md": "удалённый",
        ".claude/agents/x.md": AGENT_MD.format(n="x", d="Помощник — «кавычки» и \\\\.", body=body),
        ".codex/agents/gone.toml": AGENT_TOML.format(n="gone", d="нет", body="x"),
    })
    changed = sync.write(tmp_path)
    assert sync.compare(tmp_path) == []
    assert ".agents/skills/b/SKILL.md" in changed and ".codex/agents/x.toml" in changed
    assert (tmp_path / ".agents/skills/b/SKILL.md").read_text(encoding="utf-8") == "новый навык про .claude"
    assert not (tmp_path / ".agents/skills/old/SKILL.md").exists()
    assert not (tmp_path / ".codex/agents/gone.toml").exists()
    import tomllib
    t = tomllib.loads((tmp_path / ".codex/agents/x.toml").read_text(encoding="utf-8"))
    assert t["developer_instructions"].strip() == body.replace(".claude/rules", ".agents/rules").replace("CLAUDE.md", "AGENTS.md")
    assert sync.write(tmp_path) == []          # второй раз — нечего менять


def test_write_flag_returns_zero_when_done(tmp_path):
    in_sync(tmp_path)
    tree(tmp_path, {".claude/skills/b/SKILL.md": "новый"})
    assert sync.main(["--write", "--root", str(tmp_path)]) == 0
    assert sync.main(["--check", "--root", str(tmp_path)]) == 0


def test_real_repo_mirrors_are_in_sync():
    """После P4.2 зеркала совпадают; поменял .claude/ — запусти `scripts/sync_mirrors.py --write`."""
    assert sync.compare(REPO) == []
