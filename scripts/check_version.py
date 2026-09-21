"""Reject application changes that reuse an already tagged release version."""
import argparse
import re
import subprocess
from release_bundle import ROOT, RUNTIME_FILES, git, version_tuple


def check(repo, ref='HEAD', tag=None):
    version = git(repo, 'show', f'{ref}:.app/VERSION').decode().strip()
    current = version_tuple(version)
    if tag is not None and tag != f'v{version}':
        raise ValueError('Release tag must equal v + .app/VERSION')
    candidates = []
    for candidate in git(repo, 'tag', '--merged', ref).decode().splitlines():
        try:
            candidates.append((version_tuple(candidate.removeprefix('v')), candidate))
        except ValueError:
            continue
    if not candidates:
        return version, None
    previous, previous_tag = max(candidates)
    changed = git(repo, 'diff', '--name-only', previous_tag, ref, '--', *RUNTIME_FILES).decode().splitlines()
    if current < previous or (changed and current <= previous):
        raise ValueError(f'Application files changed after {previous_tag}; increase .app/VERSION and add release notes')
    if changed or tag:
        try:
            notes = git(repo, 'show', f'{ref}:CHANGELOG.md').decode()
        except subprocess.CalledProcessError as exc:
            raise ValueError('Add CHANGELOG.md release notes for this version') from exc
        if not re.search(rf'^## \[{re.escape(version)}\][^\n]*\n\s*\S', notes, re.M):
            raise ValueError('Add CHANGELOG.md release notes for this version')
    return version, previous_tag


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ref', default='HEAD')
    parser.add_argument('--tag')
    args = parser.parse_args()
    version, previous = check(ROOT, args.ref, args.tag)
    print(f'Version policy passed: {version}; nearest highest release tag: {previous or "none"}')


if __name__ == '__main__':
    main()
