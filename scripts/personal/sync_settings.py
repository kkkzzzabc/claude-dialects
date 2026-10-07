#!/usr/bin/env python3
"""Merge common settings and managed skill links without replacing GPT settings."""
import argparse
import json
import os
from pathlib import Path
import tempfile

KEYS = ('attribution', 'permissions', 'viewMode', 'language', 'feedbackDrafts',
        'maxProseWidth', 'skipDangerousModePermissionPrompt', 'theme', 'editorMode',
        'autoCompactEnabled', 'remoteControlAtStartup', 'tui', 'skipWorkflowUsageWarning')

def write_json(path, value):
    fd, temporary = tempfile.mkstemp(dir=path.parent, prefix='.settings-')
    try:
        with os.fdopen(fd, 'w') as out:
            json.dump(value, out, ensure_ascii=False, indent=2)
            out.write('\n')
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)

def sync(source, target, user_skills):
    original = json.loads(source.read_text())
    settings = json.loads((target / 'settings.json').read_text())
    directory = target / 'skills'
    record = target / '.personal-skill-links.json'
    managed = json.loads(record.read_text()) if record.exists() else {}
    links = {p.name: str(p) for p in user_skills.iterdir()
             if p.name != 'synced' and (p / 'SKILL.md').is_file()}
    for skill in sorted((user_skills / 'synced').rglob('SKILL.md')):
        if any(part.startswith('.') for part in skill.relative_to(user_skills / 'synced').parts):
            continue
        if skill.parent.name in links:
            raise ValueError('Duplicate skill name: ' + skill.parent.name)
        links[skill.parent.name] = str(skill.parent)
    for name, origin in links.items():
        dest = directory / name
        if dest.exists() or dest.is_symlink():
            if not dest.is_symlink() or (str(dest.readlink()) != origin and
                                         str(dest.readlink()) != managed.get(name)):
                raise ValueError('Unmanaged skill conflict: ' + str(dest))
    for key in KEYS:
        if key in original:
            settings[key] = ({**settings.get(key, {}), **original[key]}
                             if key == 'permissions' else original[key])
    directory.mkdir(exist_ok=True)
    for name, origin in managed.items():
        dest = directory / name
        if name not in links and dest.is_symlink() and str(dest.readlink()) == origin:
            dest.unlink()
    for name, origin in links.items():
        dest = directory / name
        if dest.is_symlink() and str(dest.readlink()) != origin:
            dest.unlink()
        if not dest.is_symlink():
            dest.symlink_to(origin, target_is_directory=True)
    write_json(target / 'settings.json', settings)
    write_json(record, links)
    print('Common settings applied; linked ' + str(len(links)) + ' user skills.')

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, default=Path.home() /
                        'workspace/tools/environment/agents/claude/settings.json')
    parser.add_argument('--target', type=Path, required=True)
    parser.add_argument('--skills', type=Path, default=Path.home() / '.claude/skills')
    args = parser.parse_args()
    sync(args.source, args.target, args.skills)

if __name__ == '__main__':
    main()
