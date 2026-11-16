"""Verify five CircleCI lanes plus the real, pinned Intel GitHub Actions job."""
import argparse
import base64
import hashlib
import json
import os
import re
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urlencode
from gate import check_release_tag, verify_receipts
from native import ROOT, identity

REPOSITORY = 'brunoflma/claude-session-linker'
REPOSITORY_ID = 1288808417
WORKFLOW_PATH = '.github/workflows/validate.yml'
WORKFLOW_SHA256 = '79e568ff1de260a04bb551d0fdae7d91de432223bf20a690425fb2988db4c4e9'
INTEL_JOB = 'macos-15-intel / Python 3.14'
REQUIRED_STEPS = (
    'Install pinned application dependencies', 'Validate version progression',
    'Test application logic', 'Test release integrity and publication gates',
    'Check Python syntax', 'Build and verify OS packages from this commit',
    'Open the extracted package with synthetic profiles', 'Check whitespace',
)


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise urllib.error.HTTPError(req.full_url, code, 'Redirect refused', headers, fp)


def get_json(path, token=None):
    """Public GET by default; never borrow ambient credentials or log a token."""
    base = path.partition('?')[0]
    if (not (base == f'/repos/{REPOSITORY}' or base.startswith(f'/repos/{REPOSITORY}/')
             or base == '/installation/repositories') or '..' in base.split('/')):
        raise ValueError('Unexpected GitHub API destination')
    headers = {'Accept': 'application/vnd.github+json', 'X-GitHub-Api-Version': '2022-11-28',
               'User-Agent': 'claude-session-linker-hybrid-ci'}
    if token is not None:
        headers['Authorization'] = 'Bearer ' + token
    request = urllib.request.Request('https://api.github.com' + path, headers=headers, method='GET')
    try:
        with urllib.request.build_opener(NoRedirect()).open(request, timeout=20) as response:
            data = response.read(4 * 1024 * 1024 + 1)
            if len(data) > 4 * 1024 * 1024:
                raise ValueError('GitHub response exceeds the evidence limit')
            return json.loads(data)
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f'GitHub GET failed: HTTP {exc.code}; no missing/success result inferred') from None
    except urllib.error.URLError:
        raise RuntimeError('GitHub GET transport failed; no missing/success result inferred') from None


def pages(api, path, key, max_pages=2):
    result = []
    for page in range(1, max_pages + 1):
        separator = '&' if '?' in path else '?'
        data = api(path + separator + urlencode({'per_page': 100, 'page': page}))
        items = data[key]
        result.extend(items)
        if len(result) >= data['total_count']:
            return result
        if not items:
            break
    raise ValueError('GitHub evidence pagination incomplete; refusing partial inventory')


def git_environment():
    env = dict(os.environ)
    env.update(GIT_PAGER='cat', PAGER='cat', GIT_TERMINAL_PROMPT='0', GCM_INTERACTIVE='Never')
    for key in ('GIT_TRACE', 'GIT_TRACE_CURL', 'GIT_CURL_VERBOSE', 'GIT_TRACE_PACKET', 'GIT_TRACE_SETUP'):
        env.pop(key, None)
    return env


def run_git(*args, binary=False):
    options = {} if binary else {'encoding': 'utf-8'}
    result = subprocess.run(['git', '--no-pager', *args], cwd=ROOT, env=git_environment(),
                            check=True, capture_output=True, text=not binary, **options)
    return result.stdout


def git(*args):
    return run_git(*args).strip()


def config_digest():
    return hashlib.sha256(run_git('show', 'HEAD:.circleci/config.yml', binary=True)).hexdigest()


def workflow_source():
    return run_git('show', f'HEAD:{WORKFLOW_PATH}', binary=True)


def check_repository(data):
    if data.get('id') != REPOSITORY_ID or data.get('full_name', '').lower() != REPOSITORY:
        raise ValueError('GitHub repository identity mismatch')


def check_workflow(api, commit, source):
    if hashlib.sha256(source).hexdigest() != WORKFLOW_SHA256:
        raise ValueError('Intel workflow content differs from the reviewed CI policy')
    workflow = api(f'/repos/{REPOSITORY}/actions/workflows/validate.yml')
    if workflow.get('path') != WORKFLOW_PATH or workflow.get('state') != 'active':
        raise ValueError('Expected active Intel workflow path')
    content = api(f'/repos/{REPOSITORY}/contents/{WORKFLOW_PATH}?ref={commit}')
    actual = base64.b64decode(content['content'], validate=False)
    blob = hashlib.sha1(b'blob ' + str(len(source)).encode() + b'\0' + source).hexdigest()
    if content.get('encoding') != 'base64' or actual != source or content.get('sha') != blob:
        raise ValueError('Intel workflow Git blob/version differs from the tested commit')
    return workflow, blob


def matching_run(run, commit, workflow_id, tag):
    return (run.get('workflow_id') == workflow_id and run.get('path') == WORKFLOW_PATH
            and run.get('head_sha') == commit
            and (run.get('repository') or {}).get('id') == REPOSITORY_ID
            and (run.get('head_repository') or {}).get('id') == REPOSITORY_ID
            and (run.get('event') == 'push' and run.get('head_branch') == tag if tag
                 else run.get('event') in ('push', 'pull_request', 'workflow_dispatch')))


def verify_job(job, run, commit):
    if (job.get('name') != INTEL_JOB or job.get('run_id') != run['id']
            or job.get('head_sha') != commit or job.get('status') != 'completed'
            or job.get('conclusion') != 'success' or 'macos-15-intel' not in job.get('labels', [])
            or job.get('run_attempt', run['run_attempt']) != run['run_attempt']):
        raise ValueError('Intel job identity, runner or successful completion mismatch')
    numbers = []
    for name in REQUIRED_STEPS:
        steps = [step for step in job.get('steps', []) if step.get('name') == name]
        if len(steps) != 1 or steps[0].get('status') != 'completed' or steps[0].get('conclusion') != 'success':
            raise ValueError(f'Intel required step did not complete successfully: {name}')
        numbers.append(steps[0]['number'])
    if numbers != sorted(set(numbers)):
        raise ValueError('Intel required steps are out of order or duplicated')


def verify_intel(commit, source, tag='', *, api=get_json, attempts=20, interval=30, sleep=time.sleep,
                 clock=time.monotonic):
    if not re.fullmatch(r'[0-9a-f]{40}', commit) or not 1 <= attempts <= 20 or not 0 <= interval <= 30:
        raise ValueError('Invalid SHA or bounded polling policy')
    if tag and not re.fullmatch(r'v(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)', tag):
        raise ValueError('Release evidence requires a stable exact tag')
    deadline = clock() + 600
    repository = api(f'/repos/{REPOSITORY}')
    check_repository(repository)
    if repository.get('private') is not False:
        raise ValueError('Intel gate requires public unauthenticated GitHub evidence')
    workflow, blob = check_workflow(api, commit, source)
    for poll in range(attempts):
        if clock() >= deadline:
            break
        runs = pages(api, f'/repos/{REPOSITORY}/actions/workflows/validate.yml/runs?head_sha={commit}', 'workflow_runs')
        candidates = [run for run in runs if matching_run(run, commit, workflow['id'], tag)]
        if candidates:
            latest = max(candidates, key=lambda run: (run['run_number'], run['id'], run['run_attempt']))
            if latest.get('status') == 'completed':
                if latest.get('conclusion') != 'success':
                    raise ValueError('Latest matching Intel workflow failed; older successes cannot replace it')
                attempt = latest['run_attempt']
                run = api(f'/repos/{REPOSITORY}/actions/runs/{latest["id"]}/attempts/{attempt}')
                if (not matching_run(run, commit, workflow['id'], tag) or run.get('id') != latest['id']
                        or run.get('run_attempt') != attempt or run.get('status') != 'completed'
                        or run.get('conclusion') != 'success'):
                    raise ValueError('Intel workflow attempt changed or is not successful')
                jobs = pages(api, f'/repos/{REPOSITORY}/actions/runs/{run["id"]}/attempts/{attempt}/jobs', 'jobs')
                intel = [job for job in jobs if job.get('name') == INTEL_JOB]
                if len(intel) != 1:
                    raise ValueError('Exactly one Intel job is required')
                verify_job(intel[0], run, commit)
                # Do not accept an older attempt after a rerun begins during inspection.
                current = api(f'/repos/{REPOSITORY}/actions/runs/{run["id"]}')
                if current.get('run_attempt') != attempt or current.get('status') != 'completed' or current.get('conclusion') != 'success':
                    raise ValueError('Intel run changed during verification; obtain fresh evidence')
                return {'schema': 1, 'provider': 'github-actions', 'lane': 'macos-intel-py314',
                        'repository': REPOSITORY, 'repository_id': REPOSITORY_ID,
                        'commit': commit, 'tag': tag, 'workflow_id': workflow['id'],
                        'workflow_path': WORKFLOW_PATH, 'workflow_sha256': WORKFLOW_SHA256,
                        'workflow_blob_sha': blob, 'run_id': run['id'], 'run_attempt': attempt,
                        'job_id': intel[0]['id'], 'event': run['event'], 'head_branch': run['head_branch'],
                        'gui_checked': True, 'status': 'passed', 'required_steps': list(REQUIRED_STEPS)}
        if poll + 1 < attempts and clock() + interval < deadline:
            print(f'Waiting for matching Intel Actions evidence ({poll + 1}/{attempts}).', flush=True)
            sleep(interval)
        elif poll + 1 < attempts:
            break
    raise TimeoutError('Bounded wait ended without successful matching Intel evidence')


def release_preflight(expected):
    tag, commit = expected['CIRCLE_TAG'], expected['CIRCLE_SHA1']
    check_release_tag(tag, commit, resolve=git)
    run_git('merge-base', '--is-ancestor', commit, 'origin/main')
    remote = run_git('ls-remote', 'origin', f'refs/tags/{tag}', f'refs/tags/{tag}^{{}}')
    refs = dict(line.split('\t')[::-1] for line in remote.splitlines())
    if (refs.get(f'refs/tags/{tag}^{{}}') != commit
            or refs.get(f'refs/tags/{tag}') != git('rev-parse', f'refs/tags/{tag}')):
        raise ValueError('Remote annotated tag/object changed from this pipeline checkout')
    subprocess.run([os.sys.executable, 'scripts/check_version.py', '--ref', tag, '--tag', tag], cwd=ROOT, check=True)


def verify_hybrid(directory, *, release=False, attempts=20):
    expected = identity(os.environ)
    if expected['CIRCLE_SHA1'] != git('rev-parse', 'HEAD'):
        raise ValueError('Hybrid gate checkout differs from pipeline revision')
    lanes = verify_receipts(directory, expected, config_digest(), 'supported-native')
    if release:
        release_preflight(expected)
    intel = verify_intel(expected['CIRCLE_SHA1'], workflow_source(),
                         expected['CIRCLE_TAG'] if release else '', attempts=attempts)
    return {'schema': 1, 'provider': 'hybrid', 'circleci_identity': expected,
            'circleci_lanes': lanes, 'intel': intel, 'complete_coverage': True,
            'release_preflight': release, 'release_authorized': False, 'published': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--receipts', type=Path, required=True)
    parser.add_argument('--output', type=Path, default=ROOT / 'release-artifacts/ci-hybrid/coverage.json')
    parser.add_argument('--release', action='store_true')
    args = parser.parse_args()
    report = verify_hybrid(args.receipts, release=args.release)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x', encoding='utf-8') as stream:
        json.dump(report, stream, indent=2)
        stream.write('\n')
    print(json.dumps(report))


if __name__ == '__main__':
    main()
