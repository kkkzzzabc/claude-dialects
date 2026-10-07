#!/usr/bin/env python3
"""Exercise preservation, managed bucket updates and conflict refusal."""
import json
from pathlib import Path
import tempfile
import unittest
from sync_settings import sync

class SyncTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.source = self.root / 'source.json'
        self.source.write_text(json.dumps({'viewMode': 'default', 'model': 'opus',
                                           'permissions': {'defaultMode': 'bypassPermissions'}}))
        self.target = self.root / 'claude'
        self.target.mkdir()
        self.settings = {'modelPicker': {'options': ['gpt-6.1-sol']},
                         'statusLine': {'command': 'owned'},
                         'permissions': {'allow': ['Read']}}
        (self.target / 'settings.json').write_text(json.dumps(self.settings))
        self.skills = self.root / 'user-skills'
        self.skills.mkdir()

    def skill(self, bucket):
        path = self.skills / 'synced' / bucket / 'pdf'
        path.mkdir(parents=True)
        (path / 'SKILL.md').write_text('---\nname: pdf\n---\n')
        (path / 'resource.txt').write_text('resource')
        return path

    def test_preserves_routing_and_updates_only_owned_links(self):
        first = self.skill('bucket1')
        sync(self.source, self.target, self.skills)
        current = json.loads((self.target / 'settings.json').read_text())
        self.assertEqual(current['modelPicker'], self.settings['modelPicker'])
        self.assertEqual(current['statusLine'], self.settings['statusLine'])
        self.assertNotIn('model', current)
        self.assertEqual(current['permissions']['allow'], ['Read'])
        self.assertEqual((self.target / 'skills/pdf/resource.txt').read_text(), 'resource')
        original = (self.target / 'settings.json').read_bytes()
        sync(self.source, self.target, self.skills)
        self.assertEqual((self.target / 'settings.json').read_bytes(), original)
        first.rename(first.parent / 'old')
        (first.parent / 'old/SKILL.md').unlink()
        second = self.skill('bucket2')
        sync(self.source, self.target, self.skills)
        self.assertEqual((self.target / 'skills/pdf').readlink(), second)

    def test_refuses_conflict_before_changing_settings(self):
        self.skill('bucket1')
        (self.target / 'skills/pdf').mkdir(parents=True)
        original = (self.target / 'settings.json').read_bytes()
        with self.assertRaisesRegex(ValueError, 'Unmanaged skill conflict'):
            sync(self.source, self.target, self.skills)
        self.assertEqual((self.target / 'settings.json').read_bytes(), original)

if __name__ == '__main__':
    unittest.main()
