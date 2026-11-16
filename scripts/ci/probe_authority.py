"""Prove checkout-token release/asset authority using a temporary, unpublished draft."""
import hashlib
import json
import os
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from hybrid import NoRedirect, REPOSITORY, git
from native import ROOT, identity
from release_publish import checkout_credential, installation_authority

API = 'https://api.github.com'
def main():
    expected = identity(os.environ)
    commit = expected['CIRCLE_SHA1']
    if (os.environ.get('CIRCLE_BRANCH') != 'main' or expected['CIRCLE_TAG']
            or os.environ.get('CIRCLE_PULL_REQUEST') or os.environ.get('CIRCLE_PULL_REQUESTS')
            or git('rev-parse', 'HEAD') != commit
            or git('ls-remote', 'origin', 'refs/heads/main').split()[0] != commit):
        raise ValueError('Authority probe requires current main, without PR or release tag')
    token = checkout_credential()
    authority = installation_authority(token)
    opener = urllib.request.build_opener(NoRedirect())
    prefix = f'/repos/{REPOSITORY}'
    def request(path, method='GET', data=None, accept='application/vnd.github+json', host=API):
        if host not in (API, 'https://uploads.github.com') or not path.startswith(prefix + '/'):
            raise ValueError('Unexpected GitHub probe destination')
        headers = {'Authorization': 'Bearer ' + token, 'Accept': accept,
                   'X-GitHub-Api-Version': '2022-11-28', 'User-Agent': 'circleci-release-authority-probe'}
        if data is not None:headers['Content-Type'] = 'application/json' if host == API else 'application/octet-stream'
        req = urllib.request.Request(host + path, data=data, method=method, headers=headers)
        try:
            with opener.open(req, timeout=30) as response:
                body = response.read(2 * 1024 * 1024 + 1)
                if len(body) > 2 * 1024 * 1024:raise ValueError('Probe response exceeds limit')
                return response.status, body, None
        except urllib.error.HTTPError as exc:
            if exc.code in (302, 404):return exc.code, b'', exc.headers.get('Location')
            raise RuntimeError(f'GitHub authority probe rejected: HTTP {exc.code}') from None
    name = f'ci-circleci-probe-{commit[:12]}-{expected["CIRCLE_BUILD_NUM"]}'
    for path in (prefix + '/releases/tags/' + name, prefix + '/git/ref/tags/' + name):
        if request(path)[0] != 404:raise ValueError('Probe identifier already exists; preserve it')
    payload = {'tag_name': name, 'target_commitish': commit, 'name': 'Temporary CircleCI authority probe',
               'body': 'Synthetic CI permission and asset-transfer check. Never published.', 'draft': True,
               'prerelease': False, 'make_latest': 'false', 'generate_release_notes': False}
    status, body, _ = request(prefix + '/releases', 'POST', json.dumps(payload).encode())
    if status != 201:raise ValueError('Draft was not created')
    draft = json.loads(body)
    if draft.get('draft') is not True or draft.get('tag_name') != name:
        raise ValueError('Unexpected release state; stop and reconcile, without deleting it')
    rid = draft['id']
    report = {'schema': 1, 'commit': commit, 'job_id': os.environ['CIRCLE_WORKFLOW_JOB_ID'],
              'pipeline_id': expected['CSL_PIPELINE_ID'], 'release_id': rid, 'tag': name,
              'published': False, 'draft_deleted': False}
    output = ROOT / 'release-artifacts/ci-authority/probe.json'
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + '\n')
    try:
        content = ('Synthetic CircleCI asset-transfer proof for ' + commit + '\n').encode()
        path = prefix + f'/releases/{rid}/assets?name=circleci-probe.txt'
        status, body, _ = request(path, 'POST', content, host='https://uploads.github.com')
        if status != 201:raise ValueError('Synthetic asset was not uploaded')
        asset = json.loads(body)
        status, downloaded, location = request(prefix + f'/releases/assets/{asset["id"]}', accept='application/octet-stream')
        if status == 302:
            target = urllib.parse.urlsplit(location or '')
            if target.scheme != 'https' or target.hostname not in ('release-assets.githubusercontent.com', 'objects.githubusercontent.com'):
                raise ValueError('Unexpected asset download origin')
            # Never forward the installation token to a signed CDN URL.
            with opener.open(urllib.request.Request(location), timeout=30) as response:
                downloaded = response.read(len(content) + 1)
        elif status != 200:raise ValueError('Synthetic asset was not downloadable')
        if downloaded != content:raise ValueError('Synthetic upload/download checksum mismatch')
        status, body, _ = request(prefix + f'/releases/{rid}')
        current = json.loads(body)
        if current.get('draft') is not True or current.get('tag_name') != name:
            raise ValueError('Draft identity changed; refuse cleanup')
        report.update(contents_write_verified=True, asset_sha256=hashlib.sha256(content).hexdigest(),
                      asset_transfer_verified=True, authority=authority)
    finally:
        status, body, _ = request(prefix + f'/releases/{rid}')
        current = json.loads(body)
        if current.get('draft') is True and current.get('tag_name') == name:
            if request(prefix + f'/releases/{rid}', 'DELETE')[0] != 204:raise ValueError('Draft cleanup failed')
            if request(prefix + f'/releases/{rid}')[0] != 404:raise ValueError('Draft still exists after cleanup')
            # No production/version tag may be touched. This name was proved absent.
            status, body, _ = request(prefix + '/git/ref/tags/' + name)
            if status == 200:
                ref = json.loads(body)
                if ref.get('object', {}).get('sha') != commit:raise ValueError('Probe ref identity changed')
                if request(prefix + '/git/refs/tags/' + name, 'DELETE')[0] != 204:raise ValueError('Probe ref cleanup failed')
            report['draft_deleted'] = True
        output.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report))

if __name__ == '__main__':main()
