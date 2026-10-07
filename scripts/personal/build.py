#!/usr/bin/env python3
"""Build a pinned patched proxy outside the source tree; never install tools."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[2]

def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--go', type=Path, required=True)
    parser.add_argument('--work-dir', type=Path, required=True)
    parser.add_argument('--version', default='personal.1+eac8612')
    parser.add_argument('--check', action='store_true')
    parser.add_argument('--prepare-only', action='store_true')
    args = parser.parse_args()
    work = args.work_dir.resolve()
    if work == ROOT or ROOT in work.parents:
        parser.error('work-dir must be outside the repository')
    go = args.go.resolve()
    if not go.is_file():
        parser.error('Go executable is not installed')
    work.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ, GOTOOLCHAIN='local', GOTELEMETRY='off', GOENV='off',
               GOMAXPROCS='2', CGO_ENABLED='0', GOPATH=str(work / 'gopath'),
               GOMODCACHE=str(work / 'modules'), GOCACHE=str(work / 'build'),
               GOTMPDIR=str(work / 'tmp'), TMPDIR=str(work / 'tmp'), GOFLAGS='')
    (work / 'tmp').mkdir(exist_ok=True)
    def run(arguments, cwd=ROOT, capture=False):
        return subprocess.run(arguments, cwd=cwd, env=env, check=True,
                              text=True, capture_output=capture).stdout
    metadata = json.loads((ROOT / 'patches/cliproxyapi-gpt61.json').read_text())
    patch = ROOT / 'patches/cliproxyapi-gpt61.patch'
    if digest(patch) != metadata['patch_sha256']:
        raise SystemExit('Patch checksum mismatch')
    downloaded = json.loads(run([str(go), 'mod', 'download', '-json',
                                 metadata['module'] + '@' + metadata['version']], capture=True))
    run([str(go), 'mod', 'verify'])
    proxy = work / 'proxy-source'
    if proxy.exists():
        target = proxy / metadata['file']
        if not target.exists() or digest(target) != metadata['after_sha256']:
            raise SystemExit('Existing proxy overlay differs; select a new work-dir')
    else:
        if digest(Path(downloaded['Dir']) / metadata['file']) != metadata['before_sha256']:
            raise SystemExit('Original catalog checksum mismatch')
        shutil.copytree(downloaded['Dir'], proxy)
        for path in proxy.rglob('*'):
            path.chmod(0o700 if path.is_dir() else 0o600)
        run(['patch', '--batch', '-p1', '-i', str(patch)], cwd=proxy)
        if digest(proxy / metadata['file']) != metadata['after_sha256']:
            raise SystemExit('Patched catalog checksum mismatch')
    original = Path(downloaded['Dir'])
    expected = {str(p.relative_to(original)): digest(p)
                for p in original.rglob('*') if p.is_file()}
    expected[metadata['file']] = metadata['after_sha256']
    actual = {str(p.relative_to(proxy)): digest(p)
              for p in proxy.rglob('*') if p.is_file()}
    if actual != expected:
        raise SystemExit('Proxy overlay contains changes beyond the reviewed catalog patch')
    modfile = work / 'personal.mod'
    modfile.write_text((ROOT / 'go.mod').read_text() + '\nreplace ' +
                       metadata['module'] + ' => ' + json.dumps(str(proxy)) + '\n')
    shutil.copy2(ROOT / 'go.sum', work / 'personal.sum')
    flags = ['-modfile=' + str(modfile), '-mod=readonly', '-p=2']
    if args.prepare_only:
        return
    if args.check:
        formatting = run([str(go.parent / 'gofmt'), '-l', '.'], capture=True)
        if formatting.strip():
            raise SystemExit('Go formatting differs:\n' + formatting)
        run([str(go), 'test', *flags, './...'])
        run([str(go), 'vet', *flags, './...'])
    package = work / 'package'
    package.mkdir(exist_ok=True)
    run([str(go), 'build', *flags, '-trimpath',
         '-ldflags=-s -w -X main.version=' + args.version,
         '-o', str(package / 'cc-dialect'), '.'])
    for name in ('runtime.py', 'sync_settings.py', 'install.py'):
        shutil.copy2(ROOT / 'scripts/personal' / name, package / name)
    for name in ('LICENSE', 'THIRD_PARTY_NOTICES.md'):
        shutil.copy2(ROOT / name, package / name)
    sha = run(['git', 'rev-parse', 'HEAD'], capture=True).strip()
    manifest = {'version': args.version, 'source_sha': sha,
                'upstream_sha': 'eac861273a7787eec394299f25cc7a6653f2036b',
                'dirty': bool(run(['git', 'status', '--porcelain'], capture=True).strip()),
                'go_version': run([str(go), 'version'], capture=True).strip(),
                'platform': run([str(go), 'env', 'GOOS', 'GOARCH'], capture=True).splitlines(),
                'proxy_patch': metadata, 'proxy_module_sum': downloaded['Sum'],
                'checks': 'go test/vet passed' if args.check else 'not run'}
    (package / 'build-manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    (package / 'SHA256SUMS').write_text(''.join(
        digest(path) + '  ' + path.name + '\n' for path in sorted(package.iterdir())
        if path.is_file() and path.name != 'SHA256SUMS'))
    print(package)

if __name__ == '__main__':
    main()
