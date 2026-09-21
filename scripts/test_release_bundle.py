import json
import subprocess
import tempfile
import unittest
import zipfile
from pathlib import Path
from release_bundle import COMMON, PLATFORM_FILES, expected_bundle, verify_bundle
from check_version import check


class ReleaseTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='csl-release-test-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.git('init', '-b', 'master')
        self.git('config', 'user.name', 'Release Test')
        self.git('config', 'user.email', 'test@example.com')
        for name in set(COMMON + sum(PLATFORM_FILES.values(), ())):
            target = self.root / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text('2.1.0\n' if name == '.app/VERSION' else f'fixture: {name}\n', encoding='utf-8')
        self.commit()
        self.git('tag', 'v2.1.0')

    def git(self, *args):
        return subprocess.check_output(['git', '-C', str(self.root), *args], stderr=subprocess.PIPE)

    def commit(self):
        self.git('add', '.')
        self.git('commit', '-m', 'fixture')

    def test_bundle_uses_tagged_files_not_dirty_or_private_worktree_data(self):
        manifest, files = expected_bundle(self.root, 'v2.1.0')
        (self.root / '.app/session_linker.py').write_text('uncommitted change', encoding='utf-8')
        (self.root / '.app/account_labels.json').write_text('{"private":true}', encoding='utf-8')
        self.assertEqual((manifest, files), expected_bundle(self.root, 'v2.1.0'))
        self.assertEqual(len(files), 6)
        for platform in PLATFORM_FILES:
            versioned = f'claude-session-linker-2.1.0-{platform}.zip'
            self.assertEqual(files[versioned], files[f'claude-session-linker-{platform}.zip'])
            import io
            with zipfile.ZipFile(io.BytesIO(files[versioned])) as archive:
                self.assertEqual(set(archive.namelist()), set(COMMON + PLATFORM_FILES[platform]) | {'RELEASE.json'})
                self.assertEqual(json.loads(archive.read('RELEASE.json'))['commit'], manifest['commit'])
                for item in archive.infolist():
                    self.assertEqual(item.create_system, 3)
                    if item.filename.endswith(('.command', '.sh')):
                        self.assertEqual(item.external_attr >> 16, 0o100755)

    def test_tracked_runtime_data_is_rejected(self):
        (self.root / '.app/account_labels.json').write_text('{}', encoding='utf-8')
        self.commit()
        with self.assertRaisesRegex(ValueError, 'Runtime/private'):
            expected_bundle(self.root, 'HEAD')

    def test_symlink_blob_is_not_packaged_as_application_code(self):
        blob = subprocess.check_output(['git', '-C', str(self.root), 'hash-object', '-w', '--stdin'], input=b'outside').decode().strip()
        self.git('update-index', '--cacheinfo', f'120000,{blob},.app/session_linker.py')
        self.git('commit', '-m', 'symlink')
        with self.assertRaisesRegex(ValueError, 'unsafe'):
            expected_bundle(self.root, 'HEAD')

    def test_integrity_verification_rejects_tampered_zip(self):
        _, files = expected_bundle(self.root, 'v2.1.0')
        output = self.root / 'output'
        output.mkdir()
        for name, data in files.items():
            (output / name).write_bytes(data)
        verify_bundle(self.root, 'v2.1.0', output)
        (output / 'claude-session-linker-windows.zip').write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError, 'snapshot'):
            verify_bundle(self.root, 'v2.1.0', output)

    def test_tag_must_match_embedded_version(self):
        self.git('tag', 'v2.0.0')
        with self.assertRaisesRegex(ValueError, 'differ'):
            expected_bundle(self.root, 'v2.0.0')

    def test_runtime_change_requires_new_version_but_docs_do_not(self):
        (self.root / 'README.md').write_text('new docs', encoding='utf-8')
        self.commit()
        self.assertEqual(check(self.root)[0], '2.1.0')
        (self.root / '.app/session_linker.py').write_text('new code', encoding='utf-8')
        self.commit()
        with self.assertRaisesRegex(ValueError, 'increase'):
            check(self.root)
        (self.root / '.app/VERSION').write_text('2.1.1', encoding='utf-8')
        self.commit()
        with self.assertRaisesRegex(ValueError, 'release notes'):
            check(self.root)
        (self.root / 'CHANGELOG.md').write_text('## [2.1.1] - 2026-09-21\n\nFixed a regression.\n', encoding='utf-8')
        self.commit()
        self.assertEqual(check(self.root)[0], '2.1.1')
        with self.assertRaisesRegex(ValueError, 'must equal'):
            check(self.root, tag='v2.1.0')


if __name__ == '__main__':
    unittest.main()
