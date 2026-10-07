#!/usr/bin/env python3
"""Run the selected personal package without stopping another session's proxy."""
import os
from pathlib import Path
import sys

def main():
    package = Path(__file__).resolve().parent
    data = Path(os.environ.get('CLAUDE_DIALECTS_PERSONAL_DATA',
                               str(Path.home() / '.local/share/claude-dialects-personal')))
    env = dict(os.environ, DIALECT_HOME=str(data / 'state'), TMPDIR=str(data / 'tmp'))
    env.pop('ANTHROPIC_API_KEY', None)
    (data / 'tmp').mkdir(parents=True, exist_ok=True, mode=0o700)
    args = sys.argv[1:]
    if args and args[0] == 'manage':
        args = args[1:]
    elif args and args[0] == 'sync-settings':
        os.execv(sys.executable, [sys.executable, str(package / 'sync_settings.py'),
                                 '--target', str(data / 'state/instances/cc-codex/claude'), *args[1:]])
    elif args and args[0] == 'stop':
        args = ['proxy', 'cc-codex', 'stop', *args[1:]]
    elif args and args[0] == 'login':
        args = ['auth', 'cc-codex', 'codex', *args[1:]]
    else:
        if args and args[0] == '--project':
            if len(args) < 2:
                raise SystemExit('--project requires a directory')
            os.chdir(args[1])
            args = args[2:]
        args = ['run', 'cc-codex', '--', *args]
    os.execve(str(package / 'cc-dialect'), ['cc-dialect', *args], env)

if __name__ == '__main__':
    main()
