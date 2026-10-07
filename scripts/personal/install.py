#!/usr/bin/env python3
"""Stage a personal package and trial state; activate only with validation evidence."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import secrets
import shutil
import socket

def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--package', type=Path, required=True)
    parser.add_argument('--trial', type=Path)
    parser.add_argument('--activate', action='store_true')
    parser.add_argument('--validation', type=Path)
    parser.add_argument('--port', type=int, default=43171)
    args = parser.parse_args()
    package = args.package.resolve()
    manifest = json.loads((package / 'build-manifest.json').read_text())
    if manifest['dirty']:
        parser.error('Package source must be committed before installation')
    if Path(manifest['version']).name != manifest['version']:
        parser.error('Invalid package version')
    for line in (package / 'SHA256SUMS').read_text().splitlines():
        checksum, name = line.split('  ', 1)
        if Path(name).name != name or digest(package / name) != checksum:
            parser.error('Package checksum mismatch')
    opt = Path.home() / '.local/opt/claude-dialects-personal'
    data = Path.home() / '.local/share/claude-dialects-personal'
    if opt.is_symlink() or data.is_symlink():
        parser.error('Personal installation roots must not be symlinks')
    release = opt / 'releases' / (manifest['version'] + '-' + manifest['source_sha'][:10])
    release.parent.mkdir(parents=True, exist_ok=True)
    if release.exists():
        if (release / 'SHA256SUMS').read_bytes() != (package / 'SHA256SUMS').read_bytes():
            parser.error('Existing release differs; do not overwrite it')
    else:
        shutil.copytree(package, release)
    (opt / '.personal-marker').touch(mode=0o600)
    if not (data / 'state').exists():
        if args.trial is None:
            parser.error('First installation requires --trial')
        with socket.socket() as probe:
            probe.bind(('127.0.0.1', args.port))
        trial = args.trial.resolve()
        state = trial / 'state'
        cfg = json.loads((state / 'config.json').read_text())
        dialect = cfg['dialects']['cc-codex-trial']
        if dialect['contextWindow'] != 272000 or dialect['effortLevel'] != 'medium':
            parser.error('Trial capacity/effort differs from the approved baseline')
        data.mkdir(parents=True, exist_ok=True, mode=0o700)
        staged = data / '.state-staging'
        if staged.exists():
            parser.error('Partial migration exists; inspect it before continuing')
        instance = staged / 'instances/cc-codex'
        instance.mkdir(parents=True, mode=0o700)
        origin = state / 'instances/cc-codex-trial'
        shutil.copytree(origin / 'claude', instance / 'claude', symlinks=True,
                        ignore=shutil.ignore_patterns('cache', '*.sock', '*.pid'))
        (instance / 'auth').mkdir(mode=0o700)
        auth_count = 0
        for auth in (origin / 'auth').glob('*.json'):
            shutil.copy2(auth, instance / 'auth' / auth.name)
            auth_count += 1
        if not auth_count:
            parser.error('No trial authentication files found')
        settings_path = instance / 'claude/settings.json'
        settings = json.loads(settings_path.read_text())
        settings.pop('statusLine', None)  # Generate the new instance's own script on first run.
        settings_path.write_text(json.dumps(settings, ensure_ascii=False, indent=2) + '\n')
        dialect = dict(dialect, port=args.port, apiKey=secrets.token_hex(32))
        cfg = dict(cfg, basePort=args.port, dialects={'cc-codex': dialect}, nativeLaunchers={})
        (staged / 'config.json').write_text(json.dumps(cfg, indent=2) + '\n')
        for path in staged.rglob('*'):
            if not path.is_symlink():
                path.chmod(0o700 if path.is_dir() else 0o600)
        staged.rename(data / 'state')
        (data / 'migration.json').write_text(json.dumps({
            'trial_preserved': True, 'auth_files_copied': auth_count,
            'port': args.port, 'dialect': 'cc-codex', 'claude_history_copied': True
        }, indent=2) + '\n')
        (data / 'migration.json').chmod(0o600)
    (data / 'tmp').mkdir(exist_ok=True, mode=0o700)
    if args.activate:
        if args.validation is None:
            parser.error('Activation requires --validation')
        validation = json.loads(args.validation.read_text())
        if validation.get('checks') != 'passed' or validation.get('package_sha256') != digest(release / 'cc-dialect'):
            parser.error('Validation does not match this package')
        command = Path.home() / '.local/bin/claude-gpt'
        if command.exists() or command.is_symlink():
            if not command.is_symlink() or command.readlink() != opt / 'current/runtime.py':
                parser.error('Existing claude-gpt command is not managed by this installer')
        current = opt / 'current'
        if current.exists() and not current.is_symlink():
            parser.error('current must be a managed release symlink')
        previous = str(current.readlink()) if current.is_symlink() else None
        pending = opt / '.current-pending'
        pending.symlink_to(release.relative_to(opt), target_is_directory=True)
        os.replace(pending, current)
        command.parent.mkdir(parents=True, exist_ok=True)
        if not command.is_symlink():
            command.symlink_to(opt / 'current/runtime.py')
        record = {**manifest, 'release': str(release), 'previous': previous,
                  'validation': validation, 'checksums': str(release / 'SHA256SUMS')}
        (data / 'personal-install.json').write_text(json.dumps(record, indent=2) + '\n')
        (data / 'personal-install.json').chmod(0o600)
    print(release)

if __name__ == '__main__':
    main()
