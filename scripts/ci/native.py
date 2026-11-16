"""Run a native packaging lane; emit evidence only after every check succeeds."""
import argparse
import hashlib
import json
import os
import platform
import subprocess
import sys
from pathlib import Path
from provision import runtime_pin

ROOT = Path(__file__).resolve().parents[2]
LANES = {
    'windows-py311': ('win32', 'AMD64', '3.11'),
    'windows-py314': ('win32', 'AMD64', '3.14'),
    'windows-py315': ('win32', 'AMD64', '3.15'),
    'macos-intel-py314': ('darwin', 'x86_64', '3.14'),
    'macos-arm-py314': ('darwin', 'arm64', '3.14'),
    'macos-arm-py315': ('darwin', 'arm64', '3.15'),
}


def git(*args):
    return subprocess.check_output(['git', '-C', str(ROOT), *args], text=True).strip()


def identity(env):
    """Use actual CircleCI identities, never fabricated GitHub Actions context."""
    required = ('CIRCLE_SHA1', 'CIRCLE_WORKFLOW_ID', 'CIRCLE_BUILD_NUM',
                'CIRCLE_JOB', 'CIRCLE_BUILD_URL', 'CSL_PIPELINE_ID')
    if env.get('CIRCLECI') != 'true' or any(not env.get(key) for key in required):
        raise ValueError('Native evidence requires real CircleCI job/pipeline identity')
    return {key: env[key] for key in required} | {'CIRCLE_TAG': env.get('CIRCLE_TAG', '')}


def config_digest():
    # Hash Git bytes, not Windows checkout CRLF versus macOS/Linux LF.
    content = subprocess.check_output(['git', '-C', str(ROOT), 'show', 'HEAD:.circleci/config.yml'])
    return hashlib.sha256(content).hexdigest()


def observed_host():
    result = {'platform': sys.platform, 'machine': platform.machine(),
              'python': platform.python_version(), 'release': platform.release()}
    if sys.platform == 'win32':
        result['windows_build'] = sys.getwindowsversion().build
        result['windows_product_type'] = sys.getwindowsversion().product_type
    if sys.platform == 'darwin':
        result['macos_version'] = platform.mac_ver()[0]
        # Rosetta's x86_64 process is not evidence of Intel hardware.
        result['arm_hardware'] = subprocess.check_output(
            ['sysctl', '-n', 'hw.optional.arm64'], text=True).strip() == '1'
    return result


def check_host(lane, host, mode):
    os_name, arch, series = LANES[lane]
    if host['platform'] != os_name or host['machine'].lower() != arch.lower():
        raise ValueError(f'BLOCKED {lane}: requires native {os_name}/{arch}; observed {host}')
    if '.'.join(host['python'].split('.')[:2]) != series:
        raise ValueError(f'BLOCKED {lane}: exact Python {series} required')
    if host['python'] != runtime_pin(os_name, series)['version']:
        raise ValueError(f'BLOCKED {lane}: exact reviewed Python patch required')
    if os_name == 'darwin' and host['arm_hardware'] != (arch == 'arm64'):
        raise ValueError('BLOCKED: physical Intel/ARM parity required; Rosetta is insufficient')
    if mode == 'validation':
        if os_name == 'win32' and (host['windows_build'] != 26100
                                   or host['windows_product_type'] not in (2, 3)):
            raise ValueError('BLOCKED: windows-2025 requires build 26100; Windows Server 2022 is probe-only')
        if os_name == 'darwin' and host['macos_version'].split('.')[0] != '15':
            raise ValueError('BLOCKED: required macos-15 lane needs macOS 15')


def run_lane(lane, mode):
    provenance = identity(os.environ)
    commit = git('rev-parse', 'HEAD')
    if provenance['CIRCLE_SHA1'] != commit:
        raise ValueError('CircleCI revision differs from checked-out commit')
    subprocess.run(['git', 'diff', '--exit-code', 'HEAD', '--', '.app', 'scripts', '.circleci'],
                   cwd=ROOT, check=True)
    host = observed_host()
    check_host(lane, host, mode)
    output = ROOT / 'release-artifacts'
    profile = output / 'ci-synthetic-profile'
    profile.mkdir(parents=True, exist_ok=False)
    env = dict(os.environ, CLAUDE_SESSION_LINKER_CLAUDE_DIR=str(profile))
    commands = [
        [sys.executable, '-m', 'pip', 'install', '-r', '.app/requirements.txt'],
        [sys.executable, 'scripts/check_version.py'],
        [sys.executable, '-m', 'unittest', 'discover', '-s', '.app', '-p', 'test_*.py'],
        [sys.executable, '-m', 'unittest', 'discover', '-s', 'scripts', '-p', 'test_*.py'],
        [sys.executable, '-m', 'unittest', 'discover', '-s', 'scripts/ci', '-p', 'test_*.py'],
        [sys.executable, '-m', 'compileall', '-q', '.app/session_linker.py', '.app/setup_gui.py', 'scripts'],
        [sys.executable, 'scripts/release_bundle.py', '--ref', commit],
        [sys.executable, 'scripts/release_bundle.py', '--ref', commit, '--check'],
        [sys.executable, 'scripts/smoke_package.py', '--ref', commit, '--gui'],
        ['git', '--no-pager', 'diff', '--check'],
    ]
    for command in commands:
        subprocess.run(command, cwd=ROOT, env=env, check=True)
    receipt = {'schema': 1, 'provider': 'circleci', 'lane': lane, 'mode': mode,
               'status': 'passed' if mode == 'validation' else 'probe-passed',
               'commit': commit, 'host': host, 'identity': provenance,
               'runtime_pin': runtime_pin(host['platform'], LANES[lane][2]),
               'config_sha256': config_digest(), 'gui_checked': True,
               'checks': commands}
    path = output / 'ci-receipts' / f'{lane}.json'
    path.parent.mkdir(parents=True, exist_ok=True)
    # Reusing stale success evidence is an error, including on partial reruns.
    with path.open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(receipt, stream, indent=2)
        stream.write('\n')
    print(f'{lane}: {receipt["status"]}; receipt={path}')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--lane', choices=LANES, required=True)
    parser.add_argument('--mode', choices=('probe', 'validation'), required=True)
    args = parser.parse_args()
    run_lane(args.lane, args.mode)


if __name__ == '__main__':
    main()
