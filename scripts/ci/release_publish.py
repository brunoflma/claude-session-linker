"""Qualify or publish a hybrid-proved tag using only an ephemeral checkout credential."""
import argparse
import hashlib
import json
import os
import platform
import re
import subprocess
import sys
import tarfile
import time
import urllib.request
from pathlib import Path
from urllib.parse import urlsplit
from hybrid import REPOSITORY, REPOSITORY_ID, check_repository, get_json, git, pages, release_preflight, run_git, verify_hybrid
from native import ROOT, identity


class AuthorityError(RuntimeError):
    pass


def clean_environment():
    env = dict(os.environ)
    for key in ('GH_TOKEN', 'GITHUB_TOKEN', 'GH_ENTERPRISE_TOKEN', 'GITHUB_ENTERPRISE_TOKEN', 'GH_DEBUG',
                'GIT_TRACE', 'GIT_TRACE_CURL', 'GIT_CURL_VERBOSE', 'GIT_TRACE_PACKET', 'GIT_TRACE_SETUP'):
        env.pop(key, None)
    env.update(GIT_TERMINAL_PROMPT='0', GCM_INTERACTIVE='Never', GH_PROMPT_DISABLED='1', GH_HOST='github.com',
               GIT_PAGER='cat', PAGER='cat')
    return env


def checkout_credential(*, run=subprocess.run, now=time.time):
    # Password goes through captured stdout and process memory only, never argv/files/logs.
    request = f'protocol=https\nhost=github.com\npath={REPOSITORY}.git\n\n'
    result = run(['git', '--no-pager', '-c', 'credential.interactive=false', '-c', 'credential.useHttpPath=true',
                  'credential', 'fill'], input=request, capture_output=True, text=True,
                 cwd=ROOT, env=clean_environment(), timeout=20)
    if result.returncode:
        raise AuthorityError('Checkout credential helper did not provide an ephemeral credential; root must resolve authority')
    fields = dict(line.split('=', 1) for line in result.stdout.splitlines() if '=' in line)
    token = fields.get('password', '')
    if (not 20 <= len(token) <= 16384 or any(c.isspace() or ord(c) < 33 or ord(c) > 126 for c in token)
            or token.startswith(('ghp_', 'github_pat_', 'ghu_', 'gho_', 'ghr_'))):
        raise AuthorityError('Checkout credential is missing, invalid, or a permanent/user token')
    # Provider credentials are opaque and can use a proxy format. Both callers
    # must pass installation_authority() before using the candidate for writes;
    # the authenticated installation endpoint proves its kind and repository.
    expiry = fields.get('password_expiry_utc')
    if expiry is not None:
        if not re.fullmatch(r'\d+', expiry):
            raise AuthorityError('Checkout helper returned invalid installation-token expiry metadata')
        if int(expiry) <= now() + 600:
            raise AuthorityError('Checkout installation token is expired or too close to expiry')
    return token


def installation_authority(token, *, api=get_json):
    authenticated = lambda path: api(path, token=token)
    repositories = pages(authenticated, '/installation/repositories', 'repositories')
    matches = [repo for repo in repositories if repo.get('id') == REPOSITORY_ID]
    if len(matches) != 1:
        raise AuthorityError('Checkout installation token does not grant this repository')
    check_repository(matches[0])
    repository = authenticated(f'/repos/{REPOSITORY}')
    check_repository(repository)
    advertised = repository.get('permissions', {}).get('push')
    if advertised is False:
        raise AuthorityError('GitHub reports no push authority for the checkout installation token')
    # Public GET cannot prove narrowed contents:write. Root confirms the installation grant.
    return {'token_kind': 'github-installation', 'repository_access_verified': True,
            'advertised_push_permission': advertised, 'contents_write_api_verified': False}


def github_cli(directory):
    if sys.platform != 'linux' or platform.machine().lower() not in ('x86_64', 'amd64'):
        raise ValueError('Pinned publication tool requires native Linux x64')
    lock = json.loads(Path(__file__).with_name('release-tools.json').read_text())
    pin = lock['github_cli']
    version = pin['version']
    if (lock.get('schema') != 1 or not re.fullmatch(r'\d+\.\d+\.\d+', version)
            or pin['url'] != f'https://github.com/cli/cli/releases/download/v{version}/gh_{version}_linux_amd64.tar.gz'
            or not re.fullmatch(r'[0-9a-f]{64}', pin['sha256'])):
        raise ValueError('Invalid official GitHub CLI lock')
    directory.mkdir(parents=True, exist_ok=False)
    archive = directory / 'gh.tar.gz'
    digest, size = hashlib.sha256(), 0
    with urllib.request.urlopen(pin['url'], timeout=60) as response, archive.open('xb') as output:
        final = urlsplit(response.geturl())
        if final.scheme != 'https' or final.hostname not in ('github.com', 'release-assets.githubusercontent.com', 'objects.githubusercontent.com'):
            raise ValueError('Unexpected GitHub CLI artifact origin')
        while chunk := response.read(1024 * 1024):
            size += len(chunk)
            if size > 64 * 1024 * 1024:
                raise ValueError('GitHub CLI archive exceeds size limit')
            digest.update(chunk)
            output.write(chunk)
    if digest.hexdigest() != pin['sha256']:
        raise ValueError('GitHub CLI archive SHA-256 mismatch')
    executable = directory / 'gh'
    with tarfile.open(archive, 'r:gz') as bundle:
        member = bundle.getmember(f'gh_{version}_linux_amd64/bin/gh')
        if not member.isfile() or member.size > 128 * 1024 * 1024:
            raise ValueError('Expected a regular GitHub CLI executable')
        with bundle.extractfile(member) as source, executable.open('xb') as output:
            output.write(source.read())
    executable.chmod(0o755)
    result = subprocess.run([str(executable), '--version'], check=True, capture_output=True,
                            text=True, env=clean_environment())
    if not result.stdout.startswith(f'gh version {version} '):
        raise ValueError('GitHub CLI version mismatch')
    return executable


def legacy_publisher_present():
    try:
        result = run_git('ls-tree', '--name-only', 'HEAD', '--', '.github/workflows/release.yml')
    except subprocess.CalledProcessError:
        raise ValueError('Cannot determine legacy publisher state') from None
    return '.github/workflows/release.yml' in result.splitlines()


def draft_child(tag):
    """Stage/check only a draft using original publisher primitives; never PATCH publish."""
    sys.path.insert(0, str(ROOT / 'scripts'))
    import publish_release as core
    if core.REPOSITORY != REPOSITORY:
        raise ValueError('Original publisher repository contract changed')
    manifest, expected = core.verify_bundle(ROOT, tag, ROOT / 'release-artifacts')
    if manifest['tag'] != tag:
        raise ValueError('Draft tag differs from verified bundle')
    refs = dict(line.split('\t')[::-1] for line in core.git(
        ROOT, 'ls-remote', 'origin', f'refs/tags/{tag}', f'refs/tags/{tag}^{{}}').decode().splitlines())
    if refs.get(f'refs/tags/{tag}^{{}}') != manifest['commit']:
        raise ValueError('Remote annotated tag differs from verified draft bundle')
    release = core.find_release(tag)
    if release and not release['draft']:
        raise ValueError('Draft probe refuses an already published release')
    wrote = False
    if release is None:
        core.gh('release', 'create', tag, '--verify-tag', '--draft', '--title',
                f'Claude Session Linker {manifest["version"]}', '--notes-file', '-',
                input=core.notes_for(tag).encode())
        wrote = True
        release = core.wait_for_created_release(tag)
    core.verify_assets(release, expected, require_all=False)
    existing = {asset['name'] for asset in release['assets']}
    for name in expected:
        if name not in existing:
            core.gh('release', 'upload', tag, str(ROOT / 'release-artifacts' / name))
            wrote = True
    release = core.find_release(tag)
    if not release or not release['draft']:
        raise ValueError('Draft changed state during probe; no publication was requested')
    core.verify_assets(release, expected)
    print(json.dumps({'tag': tag, 'commit': manifest['commit'], 'draft_verified': True,
                      'write_performed': wrote, 'published': False}))


def publish(receipts, *, execute=False, draft_probe=False, contents_write_confirmed=False):
    if execute and draft_probe:
        raise ValueError('Choose draft probe or actual publication, never both')
    expected = identity(os.environ)
    if os.environ.get('CIRCLE_PULL_REQUEST') or os.environ.get('CIRCLE_PULL_REQUESTS'):
        raise ValueError('Publication qualification is unavailable to PR builds')
    run_git('diff', '--exit-code', 'HEAD', '--', '.app', 'scripts', '.github', '.circleci')
    tag = expected['CIRCLE_TAG']
    from gate import check_release_tag
    check_release_tag(tag, expected['CIRCLE_SHA1'], resolve=git)
    run_git('fetch', '--no-tags', 'origin', 'refs/heads/main:refs/remotes/origin/main')
    run_git('fetch', 'origin', f'refs/tags/{tag}:refs/tags/{tag}')
    coverage = verify_hybrid(receipts, release=True, attempts=1)
    for extra in ([], ['--check']):
        subprocess.run([sys.executable, 'scripts/release_bundle.py', '--ref', tag, *extra], cwd=ROOT, check=True)
    legacy = legacy_publisher_present()
    authority = {'available': False, 'contents_write_confirmed_by_root': contents_write_confirmed}
    token = None
    try:
        token = checkout_credential()
        authority.update(installation_authority(token), available=True)
    except AuthorityError as exc:
        authority['reason'] = str(exc)
    report = {'schema': 1, 'provider': 'hybrid', 'tag': tag, 'commit': expected['CIRCLE_SHA1'],
              'qualification_verified': True, 'intel_run_id': coverage['intel']['run_id'],
              'intel_run_attempt': coverage['intel']['run_attempt'], 'authority': authority,
              'legacy_publisher_present': legacy, 'published': False}
    if not execute and not draft_probe:
        report['publication_ready'] = authority['available'] and contents_write_confirmed and not legacy
        return report
    if not token or not authority['available']:
        raise AuthorityError('Write mode requires a verified ephemeral checkout installation token')
    if execute and not contents_write_confirmed:
        raise AuthorityError('Actual publication requires root-confirmed contents:write')
    if legacy:
        raise AuthorityError('Legacy tag publisher is still present; root must retire it before enabling CircleCI writes')
    cli = github_cli(ROOT / 'release-artifacts/ci-release-tools')
    release_preflight(expected)
    env = clean_environment()
    env['GH_TOKEN'] = token
    env['PATH'] = str(cli.parent) + os.pathsep + env.get('PATH', '')
    command = ([sys.executable, '-c',
                "import sys;sys.path.insert(0,'scripts/ci');from release_publish import draft_child;draft_child(sys.argv[1])", tag]
               if draft_probe else [sys.executable, 'scripts/publish_release.py', '--tag', tag])
    result = subprocess.run(command,
                            cwd=ROOT, env=env, capture_output=True, text=True)
    env.pop('GH_TOKEN', None)
    token = None
    if result.returncode:
        raise RuntimeError('Publisher/probe failed; determine remote draft/assets/download state before any rerun')
    final = json.loads(result.stdout.strip().splitlines()[-1])
    if draft_probe:
        if (final.get('tag') != tag or final.get('commit') != expected['CIRCLE_SHA1']
                or final.get('draft_verified') is not True or final.get('published') is not False
                or not isinstance(final.get('write_performed'), bool)):
            raise ValueError('Draft probe did not return matching unpublished evidence')
        report.update(draft_probe_verified=True, contents_write_proved_by_draft=final['write_performed'],
                      published=False)
        return report
    release_url = f'https://github.com/{REPOSITORY}/releases/tag/{tag}'
    if (final.get('verified') is not True or final.get('tag') != tag
            or final.get('commit') != expected['CIRCLE_SHA1'] or final.get('url') != release_url):
        raise ValueError('Publisher did not return matching verified release evidence')
    report.update(published=True, downloads_verified=True, url=release_url)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--receipts', type=Path, required=True)
    parser.add_argument('--output', type=Path, default=ROOT / 'release-artifacts/ci-hybrid/publication.json')
    args = parser.parse_args()
    execute = os.environ.get('CSL_RELEASE_PUBLICATION_AUTHORIZED', 'false') == 'true'
    draft_probe = os.environ.get('CSL_RELEASE_DRAFT_PROBE_AUTHORIZED', 'false') == 'true'
    confirmed = os.environ.get('CSL_CHECKOUT_CONTENTS_WRITE_CONFIRMED', 'false') == 'true'
    report = publish(args.receipts, execute=execute, draft_probe=draft_probe, contents_write_confirmed=confirmed)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x', encoding='utf-8') as output:
        json.dump(report, output, indent=2)
        output.write('\n')
    print(json.dumps(report))


if __name__ == '__main__':
    main()
