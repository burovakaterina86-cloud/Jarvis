"""Роли: собственный контекст, память и проверяемые права."""
import json
from pathlib import Path

import pytest

from runtime import role_profiles


def test_profiles_exist_and_only_name_existing_skills():
    for role in role_profiles.ROLES:
        profile = role_profiles.load(role)
        assert profile.name == role and len(profile.skills) <= 20
        for skill in profile.skills:
            assert (role_profiles.ROOT / ".claude" / "skills" / skill / "SKILL.md").is_file()
    assert "reel-montage" not in role_profiles.load("text").skills
    assert "textwriter" in role_profiles.load("text").skills


def test_role_context_and_paths_are_separate(tmp_path):
    text = role_profiles.prepare(tmp_path, "1", "text", "task-a")
    research = role_profiles.prepare(tmp_path, "1", "research", "task-b")
    assert text.output != research.output and text.memory != research.memory
    prompt = text.prompt.read_text(encoding="utf-8")
    assert "textwriter" in prompt and "reel-montage" not in prompt
    assert "SOUL.md" not in prompt and "MEMORY.md" not in prompt


def test_unknown_role_and_traversal_fail(tmp_path):
    for role in ("unknown", "../text"):
        with pytest.raises(ValueError):
            role_profiles.prepare(tmp_path, "1", role, "task")
    with pytest.raises(ValueError):
        role_profiles.prepare(tmp_path, "../1", "text", "task")


def test_memory_does_not_promote_unaccepted_result(tmp_path):
    from runtime.claude_bridge import TurnResult
    role_profiles.remember(tmp_path, "1", "text", "x", TurnResult("выдумка", None, False, None, "ok", acceptance="needs_changes"))
    assert "выдумка" not in role_profiles.memory_context(tmp_path, "1", "text")
    role_profiles.remember(tmp_path, "1", "text", "y", TurnResult("проверенный итог", None, False, None, "ok", acceptance="accepted"))
    assert "проверенный итог" in role_profiles.memory_context(tmp_path, "1", "text")
    assert "проверенный итог" not in role_profiles.memory_context(tmp_path, "1", "research")


def role_env(role='text', task='t'):
    return {'JARVIS_EXECUTION_ROLE': role, 'JARVIS_CHAT_ID': '1', 'JARVIS_TASK_ID': task}


def decision(tmp_path, tool, **inputs):
    from tests.test_guard import guard, POLICY_PATH
    return guard.decide({'tool_name': tool, 'tool_input': inputs},
                        guard.load_policy(POLICY_PATH), tmp_path, role_env())


def test_guard_enforces_main_worker_scope(tmp_path):
    ctx = role_profiles.prepare(tmp_path, '1', 'text', 't')
    assert decision(tmp_path, 'Write', file_path=str(ctx.output / 'post.md')).action == 'allow'
    for tool, path in [('Write', 'outbox/agents/1/research/t/result.md'),
                       ('Write', 'state/agent-memory/1/text/episodes.jsonl'),
                       ('Read', '.claude/skills/reel-montage/SKILL.md'),
                       ('Read', 'state/agent-memory/1/research/episodes.jsonl'),
                       ('Read', 'state/agent-memory/1/text/episodes.jsonl'),
                       ('Read', 'MEMORY.md'), ('Grep', '.'), ('Glob', '.')]:
        field = 'path' if tool in ('Grep', 'Glob') else 'file_path'
        assert decision(tmp_path, tool, **{field: path}).action == 'deny'
    assert decision(tmp_path, 'Read', file_path='.claude/skills/textwriter/SKILL.md').action == 'allow'
    assert decision(tmp_path, 'Agent', prompt='другая задача').action == 'deny'
    assert decision(tmp_path, 'Bash', command='python -c "print(1)"').action == 'deny'
    for pattern in (r'\Users\burov\Projects\Jarvis\state\*', r'C:state\*'):
        assert decision(tmp_path, 'Glob', path='essa-ai', pattern=pattern).action == 'deny'


def test_unknown_role_is_fail_closed(tmp_path):
    from tests.test_guard import guard, POLICY_PATH
    assert guard.decide({'tool_name': 'Read', 'tool_input': {'file_path': 'essa-ai/VOICE.md'}},
                        guard.load_policy(POLICY_PATH), tmp_path, role_env('unknown')).action == 'deny'


def test_typed_helper_rejects_foreign_paths_commands_and_secret_search(tmp_path):
    from integrations import role_tools
    ctx = role_profiles.prepare(tmp_path, '1', 'text', 't')
    request = ctx.output / 'read.json'
    request.write_text(json.dumps({'action': 'read', 'path': '.claude/skills/reel-montage/SKILL.md'}), encoding='utf-8')
    with pytest.raises(ValueError):
        role_tools.validate(request, tmp_path, role_env())
    request.write_text(json.dumps({'action': 'read', 'path': 'essa-ai/.env.test'}), encoding='utf-8')
    with pytest.raises(ValueError):
        role_tools.validate(request, tmp_path, role_env())
    for command in ['python -m integrations.role_tools read.json; echo x',
                    'python -m integrations.role_tools $(echo x)',
                    'python -m integrations.role_tools "$(whoami).json"',
                    'python -m integrations.role_tools "`whoami`.json"',
                    'C:/other/.venv/Scripts/python.exe -m integrations.role_tools read.json']:
        with pytest.raises(ValueError):
            role_tools.command_request(command, tmp_path)


def test_helper_read_and_guard_use_same_boundaries(tmp_path):
    from integrations import role_tools
    ctx = role_profiles.prepare(tmp_path, '1', 'text', 't')
    (tmp_path / 'essa-ai').mkdir()
    source = tmp_path / 'essa-ai' / 'VOICE.md'
    source.write_text('Русский текст', encoding='utf-8')
    request = ctx.output / 'read.json'
    request.write_text(json.dumps({'action': 'read', 'path': str(source)}), encoding='utf-8')
    command = f'"{tmp_path / ".venv/Scripts/python.exe"}" -m integrations.role_tools "{request}"'
    assert decision(tmp_path, 'Bash', command=command).action == 'allow'
    assert decision(tmp_path, 'Bash', command=command, workdir=str(ctx.output)).action == 'deny'
    assert decision(tmp_path, 'Bash', command=f'python -m integrations.role_tools "{request}"').action == 'deny'
    # Не вызываем execute здесь: запись доказательств в боевой журнал запрещена тестовым сторожем.
    assert role_tools.validate(request, tmp_path, role_env())[1] == source


def test_role_launch_keeps_guard_but_excludes_common_context(tmp_path):
    from runtime import claude_bridge, codex_bridge
    options = role_profiles.options(tmp_path, '1', 'text', 't')
    args = claude_bridge.build_args(None, options)
    assert '--system-prompt-file' in args and '--safe-mode' not in args
    assert args[args.index('--setting-sources') + 1] == ''
    config = json.loads(options.settings.read_text(encoding='utf-8'))
    assert set(config['hooks']) == {'PreToolUse'}
    assert config['hooks']['PreToolUse'][0]['matcher'] == '*'
    codex = codex_bridge.build_args(None, options)
    brain = next(arg for arg in codex if arg.startswith('developer_instructions='))
    assert 'textwriter' in brain and 'reel-montage' not in brain and 'SOUL.md' not in brain


def test_symlink_cannot_join_other_role_directory(tmp_path):
    target = tmp_path / 'outbox' / 'agents' / '1' / 'research' / 't'
    target.mkdir(parents=True)
    link = tmp_path / 'outbox' / 'agents' / '1' / 'text'
    try:
        link.symlink_to(target.parent, target_is_directory=True)
    except OSError:
        pytest.skip('создание symlink недоступно этому Windows-процессу')
    with pytest.raises(ValueError):
        role_profiles.prepare(tmp_path, '1', 'text', 't')


@pytest.mark.parametrize('field', ['photo', 'screenshot', 'screens'])
def test_carousel_helper_rejects_foreign_or_secret_assets(tmp_path, field):
    from integrations import role_tools
    ctx = role_profiles.prepare(tmp_path, '1', 'carousel', 't')
    for asset in ('outbox/agents/1/text/t/private.png', 'essa-ai/.env.test'):
        value = str(tmp_path / asset)
        if field == 'screens':
            value = [value]
        (ctx.output / 'slides.json').write_text(json.dumps({'slides': [{field: value}]}), encoding='utf-8')
        request = ctx.output / 'build.json'
        request.write_text(json.dumps({'action': 'carousel', 'path': str(ctx.output)}), encoding='utf-8')
        with pytest.raises(ValueError):
            role_tools.execute(request, tmp_path, role_env('carousel'))


def test_codex_patch_cannot_write_other_role(tmp_path):
    from tests.test_guard import guard, POLICY_PATH
    role_profiles.prepare(tmp_path, '1', 'text', 't')
    policy = guard.load_policy(POLICY_PATH)
    for path, expected in [('outbox/agents/1/text/t/post.md', 'allow'),
                           ('outbox/agents/1/research/t/post.md', 'deny')]:
        event = {'tool_name': 'apply_patch', 'tool_input': {'patch': f'*** Begin Patch\n*** Add File: {path}\n+post\n*** End Patch'}}
        decisions = [guard.decide(item, policy, tmp_path, role_env()) for item in guard.codex_events(event)]
        assert decisions and all(d.action == expected for d in decisions)


async def test_delivery_cannot_send_other_role_or_memory(tmp_path):
    from tests.test_telegram import make_gateway, FakeContext, OWNER
    own = tmp_path / 'outbox/agents/1/text/t/post.md'
    own.parent.mkdir(parents=True)
    own.write_text('пост', encoding='utf-8')
    foreign = tmp_path / 'outbox/agents/1/research/t/private.md'
    foreign.parent.mkdir(parents=True)
    foreign.write_text('чужой файл', encoding='utf-8')
    context = FakeContext()
    gateway = make_gateway(tmp_path)
    await gateway._send_attachments(context, OWNER, [str(own), str(foreign)], scope=role_env())
    documents = [row for row in context.bot.documents]
    assert len(documents) == 1


def test_codex_review_cannot_accept_missing_binary_or_truncated_evidence(tmp_path):
    from runtime import review, task_router, claude_bridge
    ctx = role_profiles.prepare(tmp_path, '1', 'text', 't')
    job = task_router.Job('проверить', context='task', role='text', task_id='t', data_root=tmp_path)
    job.chat, job.runtime_used = '1', 'codex'
    for name, content, expected in [('post.md', 'текст', True), ('post.md', 'a' * 12001, False), ('photo.png', 'image', False)]:
        path = ctx.output / name
        path.write_text(content, encoding='utf-8')
        res = claude_bridge.TurnResult('готово', None, False, None, 'ok', files=[str(path.relative_to(tmp_path))])
        assert review.scoped_evidence_complete(job, res) == expected


async def test_review_rechecks_helper_files_created_during_fix(tmp_path, monkeypatch):
    from runtime import task_router, claude_bridge
    from tests.test_telegram import FakeSessions
    options = role_profiles.options(tmp_path, '1', 'text', 't')
    job = task_router.Job('проверить', context='task', role='text', task_id='t', data_root=tmp_path, options=options)
    job.chat, job.runtime_used = '1', 'codex'
    monkeypatch.setattr(task_router, 'ROOT', tmp_path)
    router = task_router.TaskRouter(sessions=FakeSessions(), budget_path=tmp_path / 'budget.json', git_status=lambda: set())
    rounds = 0
    async def timed(*args, **kwargs):
        nonlocal rounds
        if kwargs['options'].role == 'reviewer':
            rounds += 1
            return claude_bridge.TurnResult('', None, False, None, 'ok', structured={'verdict': 'fix' if rounds == 1 else 'pass', 'problems': [], 'checked': []})
        (Path(options.role_output) / 'new.png').write_bytes(b'image')
        return claude_bridge.TurnResult('исправлено', 'session', False, None, 'ok')
    monkeypatch.setattr(router, '_timed', timed)
    res = await router._review('1', job, claude_bridge.TurnResult('черновик', 'session', False, None, 'ok'), 1)
    assert res.acceptance == 'check_unavailable'
    assert any(path.endswith('new.png') for path in res.files)


async def test_conversation_cannot_deliver_a_file(tmp_path):
    from tests.test_telegram import make_gateway, FakeContext, OWNER
    from runtime.claude_bridge import TurnResult
    path = tmp_path / 'public.md'
    path.write_text('данные', encoding='utf-8')
    gateway, context = make_gateway(tmp_path), FakeContext()
    await gateway._deliver(context, OWNER, TurnResult('📎 ' + str(path), None, False, None, 'ok'), allow_attachments=False)
    assert context.bot.documents == []
