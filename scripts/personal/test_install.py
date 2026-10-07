#!/usr/bin/env python3
"""Check staged activation and refusal to overwrite an existing modified release."""
import contextlib
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import install

class InstallTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.home = Path(self.temporary.name)
        self.package = self.home / 'package'
        self.package.mkdir()
        (self.package / 'cc-dialect').write_text('test binary')
        (self.package / 'runtime.py').write_text('test runtime')
        (self.package / 'build-manifest.json').write_text(json.dumps({
            'dirty': False, 'version': 'personal.test', 'source_sha': 'a' * 40}))
        (self.package / 'SHA256SUMS').write_text(''.join(
            hashlib.sha256(p.read_bytes()).hexdigest() + '  ' + p.name + '\n'
            for p in sorted(self.package.iterdir())))
        data = self.home / '.local/share/claude-dialects-personal/state'
        data.mkdir(parents=True)
        (data / 'preserve.txt').write_text('state remains')
        self.validation = self.home / 'validation.json'
        self.validation.write_text(json.dumps({'checks': 'passed',
            'package_sha256': install.digest(self.package / 'cc-dialect')}))

    def invoke(self, *extra):
        with patch.object(Path, 'home', return_value=self.home), \
                patch('sys.argv', ['install.py', '--package', str(self.package), *extra]), \
                contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            install.main()

    def test_selection_requires_matching_evidence_and_preserves_state(self):
        self.invoke()
        current = self.home / '.local/opt/claude-dialects-personal/current'
        self.assertFalse(current.exists())
        self.validation.write_text(json.dumps({'checks': 'passed', 'package_sha256': 'wrong'}))
        with self.assertRaises(SystemExit):
            self.invoke('--activate', '--validation', str(self.validation))
        self.assertFalse(current.exists())
        self.validation.write_text(json.dumps({'checks': 'passed',
            'package_sha256': install.digest(self.package / 'cc-dialect')}))
        self.invoke('--activate', '--validation', str(self.validation))
        self.assertTrue(current.is_symlink())
        command = self.home / '.local/bin/claude-gpt'
        self.assertEqual(command.resolve(), (current / 'runtime.py').resolve())
        self.assertEqual((self.home / '.local/share/claude-dialects-personal/state/preserve.txt').read_text(),
                         'state remains')

    def test_refuses_modified_existing_release(self):
        self.invoke()
        release = next((self.home / '.local/opt/claude-dialects-personal/releases').iterdir())
        (release / 'runtime.py').write_text('unrelated edit')
        with self.assertRaises(SystemExit):
            self.invoke('--activate', '--validation', str(self.validation))
        self.assertEqual((release / 'runtime.py').read_text(), 'unrelated edit')
        self.assertFalse((release.parent.parent / 'current').exists())

if __name__ == '__main__':
    unittest.main()
