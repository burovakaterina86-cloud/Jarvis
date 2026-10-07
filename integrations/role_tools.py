"""Ограниченные операции роли: данные вместо произвольных команд."""
import json
import os
import re
from pathlib import Path

from runtime import role_profiles


def command_request(command, root):
    if any(char in command for char in '$`!%;&|<>\r\n(){}[]*?'):
        raise ValueError('подстановки и операторы оболочки запрещены')
    match = re.fullmatch(r'\s*(?:python|"?[^"\r\n]*[\\/]\.venv[\\/]Scripts[\\/]python\.exe"?)\s+-m\s+integrations\.role_tools\s+(?:"([^"\r\n]+)"|([^\s";&|<>]+))\s*', command)
    if not match:
        raise ValueError('разрешён только типизированный помощник роли')
    executable = command.strip().split(' -m ', 1)[0].strip('"')
    if Path(executable).resolve() != (Path(root) / '.venv' / 'Scripts' / 'python.exe').resolve():
        raise ValueError('чужой интерпретатор запрещён')
    path = Path(match[1] or match[2])
    return path if path.is_absolute() else Path(root) / path


def validate(request, root, env):
    if not role_profiles.allowed_path(root, env, request, write=True):
        raise ValueError('запрос должен находиться в каталоге своей задачи')
    if Path(request).stat().st_size > 16384:
        raise ValueError('слишком большой запрос')
    data = json.loads(Path(request).read_text(encoding='utf-8'))
    if not isinstance(data, dict) or set(data) - {'action', 'path', 'text'}:
        raise ValueError('неизвестные поля запроса')
    action = data.get('action')
    if action not in ('read', 'list', 'search', 'carousel'):
        raise ValueError('неизвестная операция')
    path = Path(data['path'])
    path = path if path.is_absolute() else Path(root) / path
    if not role_profiles.allowed_path(root, env, path, write=action == 'carousel'):
        raise ValueError('путь вне прав роли')
    from integrations.telegram.files import _load_guard
    guard, policy = _load_guard()
    if guard.decide({'tool_name': 'Read', 'tool_input': {'file_path': str(path)}}, policy, root, env).action == 'deny':
        raise ValueError('путь запрещён защитой')
    # Эти операции не получают права на секреты через широкий каталог входных данных.
    if any(p.lower().startswith('.env') or p.lower() in ('secrets', '.git', 'browser-profile') for p in path.parts):
        raise ValueError('служебный путь запрещён')
    if action == 'carousel' and env.get('JARVIS_EXECUTION_ROLE') != 'carousel':
        raise ValueError('операция доступна только роли каруселей')
    return action, path.resolve(), data.get('text', '')


def execute(request, root, env):
    action, path, term = validate(request, root, env)
    if action == 'read':
        with path.open('r', encoding='utf-8') as stream:
            result = stream.read(16000)
        from runtime import events
        events.emit('pipeline_evidence', task_id=env.get('JARVIS_TASK_ID'), operation='Read',
                    path=str(path), success=True)
        return result
    if action in ('list', 'search'):
        result = []
        for entry in path.rglob('*'):
            if not role_profiles.allowed_path(root, env, entry):
                continue
            from integrations.telegram.files import _load_guard
            guard, policy = _load_guard()
            if guard.decide({'tool_name': 'Read', 'tool_input': {'file_path': str(entry)}}, policy, root, env).action == 'deny':
                continue
            if any(p.lower().startswith('.env') or p.lower() in ('secrets', '.git', 'browser-profile') for p in entry.parts):
                continue
            if action == 'list':
                result.append(str(entry.relative_to(path)))
            elif entry.is_file() and entry.stat().st_size <= 100000:
                try:
                    for n, line in enumerate(entry.read_text(encoding='utf-8').splitlines(), 1):
                        if str(term) in line:
                            result.append(f'{entry.relative_to(path)}:{n}:{line[:300]}')
                except (OSError, UnicodeError):
                    continue
            if len(result) >= 200:
                break
        return '\n'.join(result[:200])
    # Входной JSON не может увести сборщик к чужим фото/снимкам или файлам слайдов.
    from integrations.telegram.files import _load_guard
    guard, policy = _load_guard()
    def check_read(source):
        if not role_profiles.allowed_path(root, env, source):
            raise ValueError('ресурс слайда вне прав роли')
        if guard.decide({'tool_name': 'Read', 'tool_input': {'file_path': str(source)}}, policy, root, env).action == 'deny':
            raise ValueError('ресурс слайда запрещён защитой')
    check_read(path / 'slides.json')
    for existing in path.rglob('*'):
        if existing.resolve() != existing.absolute():
            raise ValueError('сборка через ссылки в каталоге результатов запрещена')
    slides = json.loads((path / 'slides.json').read_text(encoding='utf-8'))
    def check(value, key=''):
        if isinstance(value, dict):
            for k, v in value.items():
                check(v, k)
        elif isinstance(value, list):
            for v in value:
                check(v, key)
        elif isinstance(value, str) and key in ('photo', 'screenshot', 'screen', 'screens', 'shot', 'src'):
            check_read(path / value)
    check(slides)
    from integrations.visuals.build import main
    return main([str(path)])


def main():
    import sys
    try:
        if len(sys.argv) != 2:
            raise ValueError('нужен один файл запроса')
        result = execute(Path(sys.argv[1]), role_profiles.ROOT, os.environ)
        print(result)
        if isinstance(result, int):
            return result
    except (ValueError, OSError, KeyError, TypeError) as exc:
        print(f'Операция отклонена: {exc}', file=sys.stderr)
        return 2
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
