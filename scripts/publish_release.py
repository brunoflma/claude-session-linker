"""Publish verified artifacts through a draft release; never overwrite published assets."""
import argparse
import json
import re
import subprocess
import urllib.request
from pathlib import Path
from release_bundle import ROOT, git, sha256, verify_bundle, version_tuple

REPOSITORY = 'brunoflma/claude-session-linker'


def gh(*args, input=None):
    return subprocess.check_output(['gh', *args, '--repo', REPOSITORY], input=input, stderr=subprocess.PIPE)


def api(endpoint, payload=None):
    args = ['gh', 'api', endpoint]
    data = None
    if payload is not None:
        args += ['--method', 'PATCH', '--input', '-']
        data = json.dumps(payload).encode()
    return json.loads(subprocess.check_output(args, input=data, stderr=subprocess.PIPE))


def release_records():
    # Auth/network failures must not be mistaken for a missing release.
    releases = json.loads(subprocess.check_output(
        ['gh', 'api', '--paginate', '--slurp', f'repos/{REPOSITORY}/releases?per_page=100'], stderr=subprocess.PIPE))
    return [release for page in releases for release in page]


def find_release(tag):
    return next((release for release in release_records() if release['tag_name'] == tag), None)


def verify_assets(release, expected, require_all=True):
    assets = {asset['name']: asset for asset in release['assets']}
    if set(assets) - set(expected):
        raise ValueError('Release contains unexpected assets; refusing to change it')
    if require_all and set(assets) != set(expected):
        raise ValueError('Release assets are incomplete')
    for name, asset in assets.items():
        if asset.get('state') != 'uploaded' or asset.get('size') != len(expected[name]) or asset.get('digest') != 'sha256:' + sha256(expected[name]):
            raise ValueError(f'Remote asset does not match the tagged build: {name}')


def notes_for(tag):
    text = git(ROOT, 'show', f'{tag}:CHANGELOG.md').decode()
    version = tag.removeprefix('v')
    match = re.search(rf'^## \[{re.escape(version)}\][^\n]*\n([\s\S]*?)(?=^## \[|\Z)', text, re.M)
    if not match or not match[1].strip():
        raise ValueError('Release notes are missing for this version')
    return match[1].strip() + '\n'


def publish(tag, directory, verify_only=False):
    version_tuple(tag.removeprefix('v'))
    manifest, expected = verify_bundle(ROOT, tag, directory)
    if tag != manifest['tag']:
        raise ValueError('Tag must match the artifact version')
    subprocess.run(['git', '-C', str(ROOT), 'merge-base', '--is-ancestor', manifest['commit'], 'origin/master'], check=True, capture_output=True)
    remote = subprocess.check_output(['git', '-C', str(ROOT), 'ls-remote', 'origin', f'refs/tags/{tag}', f'refs/tags/{tag}^{{}}']).decode().splitlines()
    references = dict(line.split('\t')[::-1] for line in remote)
    remote_commit = references.get(f'refs/tags/{tag}^{{}}', references.get(f'refs/tags/{tag}'))
    if remote_commit != manifest['commit']:
        raise ValueError('Remote tag differs from the validated commit')
    release = find_release(tag)
    if verify_only:
        if not release or release['draft']:
            raise ValueError('Expected a published release')
    elif release and not release['draft']:
        verify_assets(release, expected)
        print('Release already published; verifying without changing it.')
    else:
        if not release:
            gh('release', 'create', tag, '--verify-tag', '--draft', '--title', f'Claude Session Linker {manifest["version"]}', '--notes-file', '-', input=notes_for(tag).encode())
            release = find_release(tag)
        verify_assets(release, expected, require_all=False)
        existing = {a['name'] for a in release['assets']}
        for name in expected:
            if name not in existing:
                gh('release', 'upload', tag, str(directory / name))
        release = find_release(tag)
        verify_assets(release, expected)
        # Never demote a newer stable release when resuming an older draft.
        stable = []
        for item in release_records():
            if item['draft'] or item['prerelease']:
                continue
            try:
                stable.append(version_tuple(item['tag_name'].removeprefix('v')))
            except ValueError:
                continue
        latest = not stable or version_tuple(manifest['version']) > max(stable)
        api(f'repos/{REPOSITORY}/releases/{release["id"]}', {'draft': False, 'make_latest': 'true' if latest else 'false'})
        release = find_release(tag)
    verify_assets(release, expected)
    for asset in release['assets']:
        url = asset['browser_download_url']
        prefix = f'https://github.com/{REPOSITORY}/releases/download/{tag}/'
        if not url.startswith(prefix):
            raise ValueError('Unexpected download destination')
        request = urllib.request.Request(url, headers={'User-Agent': 'claude-session-linker-release-check'})
        with urllib.request.urlopen(request, timeout=60) as response:
            data = response.read(len(expected[asset['name']]) + 1)
        if data != expected[asset['name']]:
            raise ValueError(f'Public download differs: {asset["name"]}')
    print(json.dumps({'tag': tag, 'commit': manifest['commit'], 'url': release['html_url'],
                      'assets': [{'name': a['name'], 'digest': a['digest'], 'url': a['browser_download_url']} for a in release['assets']], 'verified': True}))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--tag', required=True)
    parser.add_argument('--directory', type=Path, default=ROOT / 'release-artifacts')
    parser.add_argument('--verify-only', action='store_true')
    args = parser.parse_args()
    publish(args.tag, args.directory, args.verify_only)


if __name__ == '__main__':
    main()
