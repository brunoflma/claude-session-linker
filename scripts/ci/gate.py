"""Reject partial, probe, stale or foreign native evidence before release preparation."""
import argparse
import json
import os
import re
import subprocess
from pathlib import Path
from native import LANES, ROOT, check_host, config_digest, git, identity

EXPECTATIONS = {
    'complete-native': frozenset(LANES),
    'supported-native': frozenset(lane for lane in LANES if lane != 'macos-intel-py314'),
}


def check_scope(expectation, release=False):
    if expectation not in EXPECTATIONS:
        raise ValueError('Unknown native coverage expectation')
    if release and expectation != 'complete-native':
        raise ValueError('BLOCKED: supported-native proves five CircleCI lanes, never Intel or release readiness')
    return EXPECTATIONS[expectation]


def verify_receipts(directory, expected, digest, expectation='complete-native'):
    lanes = check_scope(expectation)
    paths = list(directory.glob('*.json'))
    if {path.name for path in paths} != {f'{lane}.json' for lane in lanes}:
        count = 'all six' if expectation == 'complete-native' else 'all five'
        raise ValueError(f'BLOCKED: {count} {expectation} lane receipts are required, exactly once')
    builds = set()
    for lane in sorted(lanes):
        path = directory / f'{lane}.json'
        if path.is_symlink():
            raise ValueError('Refusing symlinked evidence')
        receipt = json.loads(path.read_text(encoding='utf-8'))
        if (receipt.get('schema') != 1 or receipt.get('provider') != 'circleci'
                or receipt.get('lane') != lane or receipt.get('mode') != 'validation'
                or receipt.get('status') != 'passed' or receipt.get('gui_checked') is not True
                or receipt.get('config_sha256') != digest
                or receipt.get('commit') != expected['CIRCLE_SHA1']):
            raise ValueError(f'BLOCKED: {lane} lacks matching native validation evidence')
        origin = receipt['identity']
        for key in ('CIRCLE_SHA1', 'CIRCLE_WORKFLOW_ID', 'CSL_PIPELINE_ID', 'CIRCLE_TAG'):
            if origin.get(key) != expected[key]:
                raise ValueError(f'BLOCKED: stale/foreign evidence for {lane}: {key}')
        build = origin.get('CIRCLE_BUILD_NUM')
        if not build or build in builds or not origin.get('CIRCLE_JOB') or not origin.get('CIRCLE_BUILD_URL'):
            raise ValueError('BLOCKED: every native lane needs a separate CircleCI job/build')
        builds.add(build)
        check_host(lane, receipt['host'], 'validation')
    return sorted(lanes)


def check_release_tag(tag, expected_commit, resolve=git):
    if not re.fullmatch(r'v(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)', tag):
        raise ValueError('BLOCKED: publication requires an exact stable version tag')
    if resolve('cat-file', '-t', f'refs/tags/{tag}') != 'tag':
        raise ValueError('BLOCKED: release tags must be annotated')
    if resolve('rev-parse', f'refs/tags/{tag}^{{commit}}') != expected_commit:
        raise ValueError('BLOCKED: tag does not resolve to this pipeline commit')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--receipts', type=Path, required=True)
    parser.add_argument('--expectation', choices=EXPECTATIONS, default='complete-native')
    parser.add_argument('--release', action='store_true')
    args = parser.parse_args()
    check_scope(args.expectation, args.release)
    expected = identity(os.environ)
    if expected['CIRCLE_SHA1'] != git('rev-parse', 'HEAD'):
        raise ValueError('Checked-out revision differs from pipeline revision')
    passed = verify_receipts(args.receipts, expected, config_digest(), args.expectation)
    if args.release:
        tag = expected['CIRCLE_TAG']
        check_release_tag(tag, expected['CIRCLE_SHA1'])
        subprocess.run(['git', 'merge-base', '--is-ancestor', expected['CIRCLE_SHA1'], 'origin/main'],
                       cwd=ROOT, check=True)
        subprocess.run(['python3', 'scripts/check_version.py', '--ref', tag, '--tag', tag],
                       cwd=ROOT, check=True)
    print(json.dumps({'provider': 'circleci', 'commit': expected['CIRCLE_SHA1'],
                      'workflow_id': expected['CIRCLE_WORKFLOW_ID'], 'native_lanes': passed,
                      'expectation': args.expectation,
                      'intel_verified': 'macos-intel-py314' in passed,
                      'complete_native_coverage': args.expectation == 'complete-native',
                      'release_authorized': False,
                      'release_preflight': args.release, 'published': False}))


if __name__ == '__main__':
    main()
