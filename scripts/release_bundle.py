"""Build deterministic release ZIPs from an immutable Git commit, never from the working tree."""
import argparse
import hashlib
import io
import json
import re
import subprocess
import time
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VERSION_RE = re.compile(r'(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)')
COMMON = (
    '.app/VERSION', '.app/session_linker.py', '.app/requirements.txt',
    '.app/icon.ico', '.app/icon.png', 'README.md', 'GUIA.md',
    'GUIA-WINDOWS.md', 'GUIA-MACOS.md', 'docs/cover.svg',
)
PLATFORM_FILES = {
    'windows': ('00 - Setup Claude Session Linker.vbs', 'Claude Session Linker.vbs',
                '.app/setup_gui.py', '.app/setup.ps1'),
    'macos': ('00 - Setup Claude Session Linker.command', 'Claude Session Linker.command', '.app/setup.sh'),
}
RUNTIME_FILES = tuple(sorted({p for p in COMMON + sum(PLATFORM_FILES.values(), ()) if p.startswith('.app/') or p.endswith(('.vbs', '.command'))} - {'.app/VERSION'}))
FORBIDDEN = re.compile(r'(^|/)(?:venv|__pycache__|backups|logs|staging|node_modules)(/|$)|(^|/)(?:account_labels|session_links)\.json$|(^|/)\.env(?:\.|$)|\.(?:pyc|log)$')


def git(repo, *args):
    return subprocess.check_output(['git', '-C', str(repo), *args], stderr=subprocess.PIPE)


def version_tuple(value):
    if not VERSION_RE.fullmatch(value):
        raise ValueError('Expected a stable semantic version: major.minor.patch')
    return tuple(map(int, value.split('.')))


def snapshot(repo, ref):
    commit = git(repo, 'rev-parse', '--verify', f'{ref}^{{commit}}').decode().strip()
    tree = {}
    for item in git(repo, 'ls-tree', '-rz', '--full-tree', commit).split(b'\0'):
        if not item:
            continue
        meta, name = item.split(b'\t', 1)
        mode, kind, oid = meta.decode().split()
        name = name.decode('utf-8')
        if FORBIDDEN.search(name):
            raise ValueError(f'Runtime/private artifact is tracked in the selected commit: {name}')
        tree[name] = (mode, kind, oid)
    version = git(repo, 'show', f'{commit}:.app/VERSION').decode().strip()
    version_tuple(version)
    if ref.startswith('v') and ref != f'v{version}':
        raise ValueError('Tag and .app/VERSION differ')
    stamp = int(git(repo, 'show', '-s', '--format=%ct', commit).decode())
    date = tuple(time.gmtime(max(stamp, 315532800))[:6])
    return commit, version, tree, date


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def json_bytes(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + '\n').encode('utf-8')


def expected_bundle(repo, ref):
    commit, version, tree, date = snapshot(repo, ref)
    outputs, packages, aliases = {}, [], {}
    for platform, specific in PLATFORM_FILES.items():
        provenance = {'schema': 1, 'version': version, 'tag': f'v{version}', 'commit': commit, 'platform': platform}
        contents = {'RELEASE.json': json_bytes(provenance)}
        modes = {'RELEASE.json': 0o100644}
        for name in sorted(COMMON + specific):
            if name not in tree or tree[name][0] not in ('100644', '100755') or tree[name][1] != 'blob':
                raise ValueError(f'Required regular release file is missing or unsafe: {name}')
            contents[name] = git(repo, 'cat-file', 'blob', tree[name][2])
            modes[name] = 0o100755 if name.endswith(('.command', '.sh')) else 0o100644
        stream = io.BytesIO()
        with zipfile.ZipFile(stream, 'w', compression=zipfile.ZIP_STORED) as archive:
            for name, data in sorted(contents.items()):
                info = zipfile.ZipInfo(name, date_time=date)
                info.create_system = 3
                info.create_version = info.extract_version = 20
                info.external_attr = modes[name] << 16
                archive.writestr(info, data)
        data = stream.getvalue()
        filename = f'claude-session-linker-{version}-{platform}.zip'
        alias = f'claude-session-linker-{platform}.zip'
        outputs[filename] = outputs[alias] = data
        aliases[alias] = filename
        packages.append({**provenance, 'filename': filename, 'sha256': sha256(data), 'size': len(data),
                         'files': [{'path': n, 'sha256': sha256(b), 'mode': oct(modes[n])} for n, b in sorted(contents.items())]})
    manifest = {'schema': 1, 'version': version, 'tag': f'v{version}', 'commit': commit, 'packages': packages, 'aliases': aliases}
    outputs['release-manifest.json'] = json_bytes(manifest)
    outputs['SHA256SUMS.txt'] = ''.join(f'{sha256(data)}  {name}\n' for name, data in sorted(outputs.items())).encode()
    return manifest, outputs


def verify_bundle(repo, ref, directory):
    manifest, expected = expected_bundle(repo, ref)
    for name, content in expected.items():
        path = directory / name
        if path.is_symlink() or not path.is_file() or path.read_bytes() != content:
            raise ValueError(f'Release artifact does not match the tagged Git snapshot: {name}')
    return manifest, expected


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ref', required=True)
    parser.add_argument('--output', type=Path, default=ROOT / 'release-artifacts')
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    if args.output.is_symlink():
        raise ValueError('Release output must not be a symlink')
    if args.check:
        manifest, outputs = verify_bundle(ROOT, args.ref, args.output)
    else:
        manifest, outputs = expected_bundle(ROOT, args.ref)
        args.output.mkdir(parents=True, exist_ok=True)
        for name, data in outputs.items():
            target = args.output / name
            if target.is_symlink():
                raise ValueError(f'Refusing symlinked artifact: {name}')
            target.write_bytes(data)
        verify_bundle(ROOT, args.ref, args.output)
    print(json.dumps({'version': manifest['version'], 'commit': manifest['commit'], 'artifacts': sorted(outputs), 'verified': True}))


if __name__ == '__main__':
    main()
