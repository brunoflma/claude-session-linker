"""Provision hash-pinned PSF Python/Tk on ephemeral native CircleCI runners."""
import argparse
import hashlib
import json
import os
import platform
import re
import stat
import subprocess
import sys
import urllib.request
import zipfile
from pathlib import Path, PurePosixPath
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[2]
LOCK = Path(__file__).with_name('python-runtimes.json')
MAX_DOWNLOAD = 128 * 1024 * 1024


def runtime_pin(os_name, series):
    data = json.loads(LOCK.read_text(encoding='utf-8'))
    if data.get('schema') != 1:
        raise ValueError('Unsupported Python lock schema')
    pin = data[os_name][series]
    version = pin['version']
    if not re.fullmatch(re.escape(series) + r'\.\d+', version):
        raise ValueError('Python patch must be pinned within the requested series')
    suffix = 'amd64.zip' if os_name == 'win32' else 'macos11.pkg'
    expected_url = f'https://www.python.org/ftp/python/{version}/python-{version}-{suffix}'
    if pin['url'] != expected_url or not re.fullmatch(r'[0-9a-f]{64}', pin['sha256']):
        raise ValueError('Unsafe Python URL or SHA-256 pin')
    return pin


def download(pin, target, opener=urllib.request.urlopen):
    """No cached/unverified artifact is executed or reused."""
    digest = hashlib.sha256()
    total = 0
    request = urllib.request.Request(pin['url'], headers={'User-Agent': 'csl-native-ci-bootstrap'})
    with opener(request, timeout=60) as response, target.open('xb') as output:
        final = urlsplit(response.geturl())
        if final.scheme != 'https' or final.netloc != 'www.python.org':
            raise ValueError('Python download redirected outside the official HTTPS origin')
        while chunk := response.read(1024 * 1024):
            total += len(chunk)
            if total > MAX_DOWNLOAD:
                raise ValueError('Python distribution exceeds the download limit')
            digest.update(chunk)
            output.write(chunk)
    if digest.hexdigest() != pin['sha256']:
        raise ValueError('Python distribution SHA-256 differs from the reviewed official metadata')
    return total


def extract_windows(archive, destination):
    """Reject path escapes/links/collisions before extracting a verified full ZIP."""
    with zipfile.ZipFile(archive) as bundle:
        entries = bundle.infolist()
        names = set()
        if sum(entry.file_size for entry in entries) > 1024 * 1024 * 1024:
            raise ValueError('Python ZIP exceeds the extraction limit')
        for entry in entries:
            name = entry.orig_filename
            path = PurePosixPath(name)
            if (not name or path.is_absolute() or '..' in path.parts or ':' in name
                    or '\\' in name or stat.S_ISLNK(entry.external_attr >> 16)
                    or any(part.endswith((' ', '.')) for part in path.parts)):
                raise ValueError('Unsafe Python ZIP entry')
            folded = name.rstrip('/').casefold()
            if folded in names:
                raise ValueError('Duplicate Python ZIP entry')
            names.add(folded)
        required = {'python.exe', 'dlls/_tkinter.pyd', 'lib/tkinter/__init__.py',
                    'lib/venv/__init__.py', 'lib/ensurepip/__init__.py'}
        if not required <= names:
            raise ValueError('Expected full Python/Tk/venv distribution, not an embeddable build')
        destination.mkdir(exist_ok=False)
        bundle.extractall(destination)
    return destination / 'python.exe'


def runtime_environment(bin_directory=None):
    env = dict(os.environ)
    for key in ('PYTHONHOME', 'PYTHONPATH', 'TCL_LIBRARY', 'TK_LIBRARY', 'VIRTUAL_ENV'):
        env.pop(key, None)
    env['PYTHONNOUSERSITE'] = '1'
    if bin_directory is not None:
        env['PATH'] = str(bin_directory) + os.pathsep + env.get('PATH', '')
    return env


def run(command, *, include_stderr=False):
    result = subprocess.run(command, cwd=ROOT, env=runtime_environment(), capture_output=True, text=True)
    if result.returncode:
        sys.stderr.write(result.stdout + result.stderr)
        result.check_returncode()
    return result.stdout + result.stderr if include_stderr else result.stdout


def install_runtime(os_name, series, pin, archive, directory):
    if os_name == 'win32':
        interpreter = extract_windows(archive, directory / 'python')
        result = json.loads(run(['powershell.exe', '-NoProfile', '-NonInteractive',
                                 '-ExecutionPolicy', 'Bypass', '-File',
                                 str(Path(__file__).with_name('verify-runtime-signature.ps1')),
                                 '-Path', str(interpreter)]))
        if result.get('status') != 'Valid' or result.get('signer') != 'Python Software Foundation':
            raise ValueError('Python executable signature did not pass PSF verification')
        return interpreter, result
    signature = run(['/usr/sbin/pkgutil', '--check-signature', str(archive)])
    if pin['installer_identity'] not in signature or 'trusted' not in signature.lower():
        raise ValueError('Python installer lacks the trusted PSF Developer ID Installer signature')
    assessment = run(['/usr/sbin/spctl', '--assess', '--type', 'install', '--verbose=2', str(archive)],
                     include_stderr=True)
    run(['/usr/bin/sudo', '-n', '/usr/sbin/installer', '-pkg', str(archive), '-target', '/'])
    interpreter = Path(f'/Library/Frameworks/Python.framework/Versions/{series}/bin/python{series}')
    return interpreter, {'signer': pin['installer_identity'], 'pkgutil': signature,
                         'gatekeeper': assessment, 'status': 'Valid'}


def check_interpreter(interpreter, version, os_name):
    # Imports prove native Tk bindings exist; the mandatory package smoke proves GUI.
    code = ('import json,platform,sys,tkinter,venv,ensurepip; '
            'print(json.dumps({"version":platform.python_version(),'
            '"machine":platform.machine(),"platform":sys.platform,'
            '"tk":tkinter.TkVersion,"free_threaded":bool(sysconfig.get_config_var("Py_GIL_DISABLED"))}))')
    result = json.loads(run([str(interpreter), '-I', '-c', 'import sysconfig; ' + code]))
    arch = 'amd64' if os_name == 'win32' else 'arm64'
    if (result['version'] != version or result['platform'] != os_name
            or result['machine'].lower() != arch or result['free_threaded']):
        raise ValueError('Provisioned Python has the wrong patch/platform/architecture/GIL mode')
    return result


def provision(series, mode):
    # Prevent accidental local installation: identity and revision are checked first.
    from native import git, identity
    context = identity(os.environ)
    if context['CIRCLE_SHA1'] != git('rev-parse', 'HEAD'):
        raise ValueError('Bootstrap revision differs from CircleCI revision')
    os_name = sys.platform
    if os_name not in ('win32', 'darwin'):
        raise ValueError('Bootstrap requires native Windows or macOS')
    if os_name == 'darwin' and platform.machine() != 'arm64':
        raise ValueError('Hosted macOS bootstrap requires native ARM, never Rosetta/Intel')
    pin = runtime_pin(os_name, series)
    venv = ROOT / 'release-artifacts' / 'ci-venv'
    if venv.exists():
        raise ValueError('Refusing to reuse an existing CI venv')
    directory = ROOT / 'release-artifacts' / 'ci-runtime'
    directory.mkdir(parents=True, exist_ok=False)
    archive = directory / Path(urlsplit(pin['url']).path).name
    size = download(pin, archive)
    interpreter, signature = install_runtime(os_name, series, pin, archive, directory)
    observed = check_interpreter(interpreter, pin['version'], os_name)
    run([str(interpreter), '-I', '-m', 'venv', str(venv)])
    venv_python = venv / ('Scripts/python.exe' if os_name == 'win32' else 'bin/python')
    check_interpreter(venv_python, pin['version'], os_name)
    receipt = {'schema': 1, 'version': pin['version'], 'url': pin['url'],
               'sha256': pin['sha256'], 'bytes': size, 'signature': signature,
               'interpreter': observed, 'identity': context}
    (directory / 'provision.json').write_text(json.dumps(receipt, indent=2) + '\n', encoding='utf-8')
    print(f'Provisioned PSF Python {pin["version"]} with Tk; SHA-256 and signature verified.', flush=True)
    lane = ('windows' if os_name == 'win32' else 'macos-arm') + '-py' + series.replace('.', '')
    subprocess.run([str(venv_python), 'scripts/ci/native.py', '--lane', lane, '--mode', mode],
                   cwd=ROOT, env=runtime_environment(venv_python.parent), check=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--series', choices=('3.11', '3.14', '3.15'), required=True)
    parser.add_argument('--mode', choices=('probe', 'validation'), required=True)
    args = parser.parse_args()
    provision(args.series, args.mode)


if __name__ == '__main__':
    main()
