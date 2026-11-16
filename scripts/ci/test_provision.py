"""Bootstrap contract tests with synthetic archives and mocked installation effects."""
import hashlib
import io
import json
import subprocess
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch
import provision


class Response(io.BytesIO):
    def geturl(self):
        return 'https://www.python.org/ftp/python/example.zip'


class DownloadTests(unittest.TestCase):
    def test_locked_patches_are_complete_official_distributions(self):
        expected = {'win32': {'3.11': '3.11.9', '3.14': '3.14.10', '3.15': '3.15.2'},
                    'darwin': {'3.14': '3.14.10', '3.15': '3.15.2'}}
        for os_name, versions in expected.items():
            for series, version in versions.items():
                with self.subTest(os_name=os_name, series=series):
                    pin = provision.runtime_pin(os_name, series)
                    self.assertEqual(pin['version'], version)
                    self.assertTrue(pin['url'].startswith('https://www.python.org/ftp/python/'))
                    self.assertEqual(len(pin['sha256']), 64)

    def test_bad_origin_or_hash_in_lock_is_rejected(self):
        data = json.loads(provision.LOCK.read_text())
        for field, value in [('url', 'https://evil.example/python.zip'), ('sha256', 'not-a-hash'),
                             ('version', '3.15.2')]:
            altered = json.loads(json.dumps(data))
            altered['win32']['3.14'][field] = value
            with self.subTest(field=field), patch('provision.json.loads', return_value=altered):
                with self.assertRaises(ValueError):
                    provision.runtime_pin('win32', '3.14')

    def test_download_requires_pinned_hash_and_https_origin(self):
        data = b'synthetic-official-package'
        pin = {'url': 'https://www.python.org/ftp/python/example.zip',
               'sha256': hashlib.sha256(data).hexdigest()}
        with tempfile.TemporaryDirectory(prefix='csl-bootstrap-test-') as folder:
            base = Path(folder)
            self.assertEqual(provision.download(pin, base / 'ok.zip', lambda *a, **kw: Response(data)), len(data))
            with self.assertRaisesRegex(ValueError, 'SHA-256'):
                provision.download(pin | {'sha256': '0' * 64}, base / 'bad.zip', lambda *a, **kw: Response(data))
            response = Response(data)
            response.geturl = lambda: 'http://www.python.org/insecure.zip'
            with self.assertRaisesRegex(ValueError, 'HTTPS origin'):
                provision.download(pin, base / 'redirect.zip', lambda *a, **kw: response)
            with patch.object(provision, 'MAX_DOWNLOAD', 1), self.assertRaisesRegex(ValueError, 'limit'):
                provision.download(pin, base / 'large.zip', lambda *a, **kw: Response(data))


class ArchiveTests(unittest.TestCase):
    def archive(self, directory, extra=None, full=True):
        path = directory / 'runtime.zip'
        with zipfile.ZipFile(path, 'w') as bundle:
            if full:
                for name in ['python.exe', 'DLLs/_tkinter.pyd', 'Lib/tkinter/__init__.py',
                             'Lib/venv/__init__.py', 'Lib/ensurepip/__init__.py']:
                    bundle.writestr(name, b'synthetic-data-never-executed')
            if extra is not None:
                if isinstance(extra, str) and '\\' in extra:
                    raw = zipfile.ZipInfo('raw-name')
                    raw.filename = extra
                    extra = raw
                bundle.writestr(extra, b'unsafe')
        return path

    def test_full_archive_extracts_into_isolated_directory(self):
        with tempfile.TemporaryDirectory(prefix='csl-bootstrap-test-') as folder:
            base = Path(folder)
            interpreter = provision.extract_windows(self.archive(base), base / 'extracted')
            self.assertTrue(interpreter.is_file())

    def test_path_escapes_links_and_case_collisions_fail_before_extraction(self):
        symlink = zipfile.ZipInfo('linked')
        symlink.create_system = 3
        symlink.external_attr = 0o120777 << 16
        for entry in ['../escape', '/absolute', 'C:/escape', 'file:stream', 'bad\\path',
                      'directory./file', 'PYTHON.EXE', symlink]:
            with self.subTest(entry=str(entry)), tempfile.TemporaryDirectory(prefix='csl-bootstrap-test-') as folder:
                base = Path(folder)
                with self.assertRaises(ValueError):
                    provision.extract_windows(self.archive(base, entry), base / 'extracted')
                self.assertFalse((base / 'extracted').exists())

    def test_embeddable_archive_is_insufficient_for_tk_and_venv(self):
        with tempfile.TemporaryDirectory(prefix='csl-bootstrap-test-') as folder:
            base = Path(folder)
            with self.assertRaisesRegex(ValueError, 'full Python/Tk/venv'):
                provision.extract_windows(self.archive(base, full=False), base / 'extracted')


class SignatureTests(unittest.TestCase):
    def test_windows_requires_valid_psf_authenticode(self):
        valid = {'status': 'Valid', 'signer': 'Python Software Foundation'}
        for result, passes in [(valid, True), (valid | {'status': 'NotTrusted'}, False),
                               (valid | {'signer': 'Other publisher'}, False)]:
            with self.subTest(result=result), \
                    patch.object(provision, 'extract_windows', return_value=Path('runtime/python.exe')), \
                    patch.object(provision, 'run', return_value=json.dumps(result)) as run:
                args = ('win32', '3.14', {}, Path('runtime.zip'), Path('runtime'))
                if passes:
                    provision.install_runtime(*args)
                    self.assertIn('verify-runtime-signature.ps1', str(run.call_args.args[0]))
                else:
                    with self.assertRaisesRegex(ValueError, 'PSF verification'):
                        provision.install_runtime(*args)

    def test_macos_signature_and_gatekeeper_precede_installation(self):
        pin = provision.runtime_pin('darwin', '3.15')
        outputs = ['Status: signed by a certificate trusted by macOS\n' + pin['installer_identity'], '', 'installed']
        with patch.object(provision, 'run', side_effect=outputs) as run:
            interpreter, _ = provision.install_runtime('darwin', '3.15', pin, Path('runtime.pkg'), Path('runtime'))
        commands = [call.args[0] for call in run.call_args_list]
        self.assertEqual([Path(command[0]).name for command in commands], ['pkgutil', 'spctl', 'sudo'])
        self.assertIn('Python.framework', str(interpreter))
        self.assertIn('-n', commands[-1])

    def test_bad_macos_signer_or_gatekeeper_failure_never_installs(self):
        pin = provision.runtime_pin('darwin', '3.14')
        for outputs in [['signed by Other Publisher'],
                        ['signed by a certificate trusted by macOS ' + pin['installer_identity'],
                         subprocess.CalledProcessError(1, ['spctl'])]]:
            with self.subTest(outputs=str(outputs)), patch.object(provision, 'run', side_effect=outputs) as run:
                with self.assertRaises((ValueError, subprocess.CalledProcessError)):
                    provision.install_runtime('darwin', '3.14', pin, Path('runtime.pkg'), Path('runtime'))
                self.assertFalse(any(call.args[0][0] == '/usr/bin/sudo' for call in run.call_args_list))


class InterpreterTests(unittest.TestCase):
    def test_runtime_environment_removes_seed_python_tk_overrides_and_prefers_venv(self):
        poisoned = {key: 'seed-runtime' for key in ('PYTHONHOME', 'PYTHONPATH', 'TCL_LIBRARY', 'TK_LIBRARY', 'VIRTUAL_ENV')}
        with patch.dict(provision.os.environ, poisoned | {'PATH': 'system-tools'}):
            env = provision.runtime_environment(Path('verified-venv/Scripts'))
        for key in poisoned:
            self.assertNotIn(key, env)
        self.assertEqual(env['PYTHONNOUSERSITE'], '1')
        self.assertTrue(env['PATH'].startswith(str(Path('verified-venv/Scripts')) + provision.os.pathsep))
        self.assertTrue(env['PATH'].endswith('system-tools'))

    def test_exact_patch_architecture_platform_and_regular_gil_are_required(self):
        valid = {'version': '3.15.2', 'platform': 'darwin', 'machine': 'arm64', 'free_threaded': False, 'tk': 9.0}
        for changes in [{}, {'version': '3.15.1'}, {'machine': 'x86_64'},
                        {'platform': 'linux'}, {'free_threaded': True}]:
            with self.subTest(changes=changes), patch.object(provision, 'run', return_value=json.dumps(valid | changes)):
                if not changes:
                    provision.check_interpreter(Path('python'), '3.15.2', 'darwin')
                else:
                    with self.assertRaisesRegex(ValueError, 'wrong patch/platform/architecture/GIL'):
                        provision.check_interpreter(Path('python'), '3.15.2', 'darwin')


class ProvisioningOrderTests(unittest.TestCase):
    def test_non_circleci_invocation_stops_before_download_or_install(self):
        with patch('native.identity', side_effect=ValueError('not CircleCI')), \
                patch.object(provision, 'download') as download, patch.object(provision, 'install_runtime') as install:
            with self.assertRaises(ValueError):
                provision.provision('3.14', 'validation')
            download.assert_not_called()
            install.assert_not_called()

    def test_hash_mismatch_stops_before_signature_install_or_native_execution(self):
        with tempfile.TemporaryDirectory(prefix='csl-bootstrap-test-') as folder, \
                patch.object(provision, 'ROOT', Path(folder)), \
                patch.object(provision.sys, 'platform', 'win32'), \
                patch('native.identity', return_value={'CIRCLE_SHA1': 'commit'}), \
                patch('native.git', return_value='commit'), \
                patch.object(provision, 'download', side_effect=ValueError('SHA-256 mismatch')), \
                patch.object(provision, 'install_runtime') as install, \
                patch.object(provision.subprocess, 'run') as native_run:
            with self.assertRaisesRegex(ValueError, 'SHA-256'):
                provision.provision('3.15', 'validation')
            install.assert_not_called()
            native_run.assert_not_called()

    def test_verified_runtime_creates_and_checks_venv_then_runs_real_validation(self):
        with tempfile.TemporaryDirectory(prefix='csl-bootstrap-test-') as folder, \
                patch.object(provision, 'ROOT', Path(folder)), \
                patch.object(provision.sys, 'platform', 'win32'), \
                patch('native.identity', return_value={'CIRCLE_SHA1': 'commit'}), \
                patch('native.git', return_value='commit'), \
                patch.object(provision, 'download', return_value=99), \
                patch.object(provision, 'install_runtime', return_value=(Path('verified/python.exe'), {'status': 'Valid'})), \
                patch.object(provision, 'check_interpreter', return_value={'version': '3.15.2'}) as interpreter_check, \
                patch.object(provision, 'run') as venv_run, \
                patch('builtins.print'), \
                patch.object(provision.subprocess, 'run') as native_run:
            provision.provision('3.15', 'validation')
            self.assertEqual(interpreter_check.call_count, 2)
            self.assertIn('venv', venv_run.call_args.args[0])
            command = native_run.call_args.args[0]
            self.assertEqual(command[-4:], ['--lane', 'windows-py315', '--mode', 'validation'])
            receipt = json.loads((Path(folder) / 'release-artifacts/ci-runtime/provision.json').read_text())
            self.assertEqual(receipt['version'], '3.15.2')
            self.assertEqual(receipt['signature']['status'], 'Valid')


if __name__ == '__main__':
    unittest.main()
