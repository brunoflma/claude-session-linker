"""Publication tests use synthetic credentials and mock every network/write effect."""
import contextlib
import hashlib
import io
import json
import os
import subprocess
import tarfile
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
import release_publish as release

COMMIT = 'a' * 40
CANARY = 'ghs_SYNTHETIC_TEST_CANARY_NEVER_REAL'


class CredentialTests(unittest.TestCase):
    def test_helper_credential_is_in_memory_never_argv_or_request(self):
        runner = Mock(return_value=subprocess.CompletedProcess([], 0, 'username=x-access-token\npassword=' + CANARY + '\n', ''))
        with patch.dict(os.environ, {'GH_TOKEN': 'ambient-secret', 'GH_DEBUG': 'api', 'GIT_TRACE': '1'}):
            self.assertEqual(release.checkout_credential(run=runner), CANARY)
        command = runner.call_args.args[0]
        options = runner.call_args.kwargs
        self.assertNotIn(CANARY, str(command))
        self.assertNotIn(CANARY, options['input'])
        self.assertIn('path=' + release.REPOSITORY + '.git', options['input'])
        self.assertEqual(options['env']['GIT_TERMINAL_PROMPT'], '0')
        self.assertNotIn('GH_TOKEN', options['env'])
        self.assertNotIn('GH_DEBUG', options['env'])
        self.assertNotIn('GIT_TRACE', options['env'])

    def test_no_helper_or_permanent_user_tokens_are_not_substituted(self):
        for output, code in [('', 1), ('password=ghp_permanent', 0), ('password=github_pat_permanent', 0),
                             ('password=ghu_user_token', 0), ('password=gho_oauth', 0)]:
            runner = Mock(return_value=subprocess.CompletedProcess([], code, output, 'stderr-secret-canary'))
            with self.subTest(code=code, kind=output[:12]), self.assertRaises(release.AuthorityError) as error:
                release.checkout_credential(run=runner)
            self.assertNotIn('stderr-secret-canary', str(error.exception))

    def test_expiry_metadata_is_validated(self):
        for expiry in ('500', 'nan', 'not-time'):
            runner = Mock(return_value=subprocess.CompletedProcess([], 0, f'password={CANARY}\npassword_expiry_utc={expiry}\n', ''))
            with self.subTest(expiry=expiry), self.assertRaises(release.AuthorityError):
                release.checkout_credential(run=runner, now=lambda: 1000)
        runner = Mock(return_value=subprocess.CompletedProcess([], 0, f'password={CANARY}\npassword_expiry_utc=3000\n', ''))
        self.assertEqual(release.checkout_credential(run=runner, now=lambda: 1000), CANARY)

    def test_opaque_provider_credential_requires_authenticated_installation_proof(self):
        candidate = 'v1.SYNTHETIC_OPAQUE_PROVIDER_CANARY'
        runner = Mock(return_value=subprocess.CompletedProcess([], 0, 'password=' + candidate + '\n', ''))
        self.assertEqual(release.checkout_credential(run=runner), candidate)
        denied = Mock(side_effect=RuntimeError('installation endpoint denied'))
        with self.assertRaisesRegex(RuntimeError, 'installation endpoint denied'):
            release.installation_authority(candidate, api=denied)
        self.assertEqual(denied.call_args.args[0], '/installation/repositories?per_page=100&page=1')

    def test_installation_token_repo_access_is_verified_without_claiming_contents_write(self):
        repository = {'id': release.REPOSITORY_ID, 'full_name': release.REPOSITORY, 'permissions': {'push': True}}
        api = Mock(side_effect=[{'total_count': 1, 'repositories': [repository]}, repository])
        report = release.installation_authority(CANARY, api=api)
        self.assertTrue(report['repository_access_verified'])
        self.assertFalse(report['contents_write_api_verified'])
        self.assertNotIn(CANARY, json.dumps(report))
        self.assertTrue(all(call.kwargs == {'token': CANARY} for call in api.call_args_list))

    def test_wrong_installation_repository_and_denied_push_refuse_authority(self):
        repository = {'id': release.REPOSITORY_ID, 'full_name': release.REPOSITORY}
        for first, second in [({'total_count': 0, 'repositories': []}, repository),
                              ({'total_count': 1, 'repositories': [repository]}, repository | {'permissions': {'push': False}})]:
            with self.subTest(first=first), self.assertRaises(release.AuthorityError):
                release.installation_authority(CANARY, api=Mock(side_effect=[first, second]))


class CLITests(unittest.TestCase):
    def archive(self, *, symlink=False):
        data = io.BytesIO()
        with tarfile.open(fileobj=data, mode='w:gz') as bundle:
            info = tarfile.TarInfo('gh_1.2.3_linux_amd64/bin/gh')
            if symlink:
                info.type, info.linkname = tarfile.SYMTYPE, '/outside'
                bundle.addfile(info)
            else:
                content = b'synthetic-binary-never-executed'
                info.size = len(content)
                bundle.addfile(info, io.BytesIO(content))
        return data.getvalue()

    def provision(self, directory, data, *, digest=None, url='https://release-assets.githubusercontent.com/package'):
        lock = {'schema': 1, 'github_cli': {'version': '1.2.3',
                'url': 'https://github.com/cli/cli/releases/download/v1.2.3/gh_1.2.3_linux_amd64.tar.gz',
                'sha256': digest or hashlib.sha256(data).hexdigest()}}
        response = io.BytesIO(data)
        response.geturl = lambda: url
        with patch.object(release.sys, 'platform', 'linux'), patch.object(release.platform, 'machine', return_value='x86_64'), \
                patch.object(release.json, 'loads', return_value=lock), \
                patch.object(release.urllib.request, 'urlopen', return_value=response), \
                patch.object(release.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0, 'gh version 1.2.3 (test)\n', '')) as execute:
            return release.github_cli(directory), execute

    def test_cli_is_hash_checked_before_single_file_extraction_and_mocked_execution(self):
        with tempfile.TemporaryDirectory(prefix='csl-cli-test-') as folder:
            executable, run = self.provision(Path(folder) / 'tools', self.archive())
            self.assertEqual(executable.read_bytes(), b'synthetic-binary-never-executed')
            self.assertEqual(run.call_count, 1)
            self.assertEqual(run.call_args.args[0][-1], '--version')

    def test_cli_bad_hash_redirect_or_link_never_becomes_executable(self):
        for kind in ('hash', 'origin', 'link'):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory(prefix='csl-cli-test-') as folder:
                target = Path(folder) / 'tools'
                with self.assertRaises(ValueError):
                    self.provision(target, self.archive(symlink=kind == 'link'),
                                   digest='0' * 64 if kind == 'hash' else None,
                                   url='http://evil.example/package' if kind == 'origin' else 'https://release-assets.githubusercontent.com/package')
                self.assertFalse((target / 'gh').exists())


class PublicationTests(unittest.TestCase):
    def setUp(self):
        self.stack = contextlib.ExitStack()
        self.addCleanup(self.stack.close)
        self.context = {'CIRCLE_SHA1': COMMIT, 'CIRCLE_TAG': 'v2.0.0'}
        self.stack.enter_context(patch.object(release, 'identity', return_value=self.context))
        self.stack.enter_context(patch.dict(os.environ, {'CIRCLE_PULL_REQUEST': '', 'CIRCLE_PULL_REQUESTS': ''}))
        self.stack.enter_context(patch('gate.check_release_tag'))
        self.coverage = self.stack.enter_context(patch.object(release, 'verify_hybrid', return_value={'intel': {'run_id': 101, 'run_attempt': 1}}))
        self.credential = self.stack.enter_context(patch.object(release, 'checkout_credential', return_value=CANARY))
        self.authority = self.stack.enter_context(patch.object(release, 'installation_authority', return_value={'token_kind': 'github-installation'}))
        self.legacy = self.stack.enter_context(patch.object(release, 'legacy_publisher_present', return_value=False))
        self.cli = self.stack.enter_context(patch.object(release, 'github_cli', return_value=Path('verified-tools/gh')))
        self.preflight = self.stack.enter_context(patch.object(release, 'release_preflight'))
        self.run = self.stack.enter_context(patch.object(release.subprocess, 'run', side_effect=self.process))
        self.process_calls = []
        self.final = {'verified': True, 'tag': 'v2.0.0', 'commit': COMMIT,
                      'url': 'https://github.com/' + release.REPOSITORY + '/releases/tag/v2.0.0'}
        self.publisher_code = 0

    def process(self, command, **kwargs):
        # Snapshot the environment before the helper clears the in-memory child token.
        options = dict(kwargs)
        if 'env' in options:
            options['env'] = dict(options['env'])
        self.process_calls.append((command, options))
        effect = 'scripts/publish_release.py' in command or any('draft_child' in str(arg) for arg in command)
        output = json.dumps(self.final) if effect else ''
        return subprocess.CompletedProcess(command, self.publisher_code if output else 0, output, '')

    def publisher_calls(self):
        return [(command, options) for command, options in self.process_calls if 'scripts/publish_release.py' in command]

    def test_dry_run_completes_qualification_without_publication_or_gh_installation(self):
        report = release.publish(Path('receipts'))
        self.assertTrue(report['qualification_verified'])
        self.assertFalse(report['published'])
        self.assertFalse(report['publication_ready'])
        self.assertEqual(self.publisher_calls(), [])
        self.cli.assert_not_called()
        self.coverage.assert_called_once_with(Path('receipts'), release=True, attempts=1)
        builds = [command for command, _ in self.process_calls if 'scripts/release_bundle.py' in command]
        self.assertEqual(len(builds), 2)
        self.assertIn('--check', builds[-1])

    def test_missing_helper_is_reported_honestly_in_dry_run_and_blocks_execute(self):
        self.credential.side_effect = release.AuthorityError('No ephemeral checkout authority')
        report = release.publish(Path('receipts'))
        self.assertFalse(report['authority']['available'])
        self.assertFalse(report['publication_ready'])
        with self.assertRaises(release.AuthorityError):
            release.publish(Path('receipts'), execute=True, contents_write_confirmed=True)
        self.assertEqual(self.publisher_calls(), [])

    def test_manual_write_confirmation_legacy_retirement_and_pr_exclusion_are_required(self):
        with self.assertRaises(release.AuthorityError):
            release.publish(Path('receipts'), execute=True)
        self.legacy.return_value = True
        with self.assertRaisesRegex(release.AuthorityError, 'Legacy tag publisher'):
            release.publish(Path('receipts'), execute=True, contents_write_confirmed=True)
        with patch.dict(os.environ, {'CIRCLE_PULL_REQUEST': 'https://github.com/example/pull/1'}), self.assertRaises(ValueError):
            release.publish(Path('receipts'), execute=True, contents_write_confirmed=True)
        self.assertEqual(self.publisher_calls(), [])

    def test_real_publish_path_reuses_existing_publisher_with_token_only_in_child_environment(self):
        report = release.publish(Path('receipts'), execute=True, contents_write_confirmed=True)
        self.assertTrue(report['published'])
        self.assertTrue(report['downloads_verified'])
        calls = self.publisher_calls()
        self.assertEqual(len(calls), 1)
        command, options = calls[0]
        self.assertNotIn(CANARY, str(command))
        self.assertEqual(options['env']['GH_TOKEN'], CANARY)
        self.assertNotIn(CANARY, json.dumps(report))
        self.assertFalse(any(CANARY in str(command) for command, _ in self.process_calls))
        self.preflight.assert_called_once_with(self.context)

    def test_bad_hybrid_proof_prevents_credential_access_and_publisher(self):
        self.coverage.side_effect = ValueError('bad Intel proof')
        with self.assertRaises(ValueError):
            release.publish(Path('receipts'), execute=True, contents_write_confirmed=True)
        self.credential.assert_not_called()
        self.assertEqual(self.publisher_calls(), [])

    def test_publisher_failure_does_not_retry_or_claim_success(self):
        self.publisher_code = 1
        with self.assertRaisesRegex(RuntimeError, 'determine remote'):
            release.publish(Path('receipts'), execute=True, contents_write_confirmed=True)
        self.assertEqual(len(self.publisher_calls()), 1)

    def test_publisher_must_return_matching_tag_commit_verified_download_receipt(self):
        for change in ({'verified': False}, {'tag': 'v1.0.0'}, {'commit': 'b' * 40}, {'url': 'https://evil.example'}):
            with self.subTest(change=change):
                original = dict(self.final)
                self.final.update(change)
                with self.assertRaises(ValueError):
                    release.publish(Path('receipts'), execute=True, contents_write_confirmed=True)
                self.final = original

    def test_draft_probe_proves_write_without_publishing_or_manual_claim_of_contents_permission(self):
        self.final = {'tag': 'v2.0.0', 'commit': COMMIT, 'draft_verified': True,
                      'write_performed': True, 'published': False}
        result = release.publish(Path('receipts'), draft_probe=True)
        self.assertTrue(result['draft_probe_verified'])
        self.assertTrue(result['contents_write_proved_by_draft'])
        self.assertFalse(result['published'])
        self.assertEqual(self.publisher_calls(), [])
        calls = [(cmd, opts) for cmd, opts in self.process_calls if any('draft_child' in str(arg) for arg in cmd)]
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0][1]['env']['GH_TOKEN'], CANARY)
        self.assertNotIn(CANARY, str(calls[0][0]))
        self.assertNotIn(CANARY, json.dumps(result))

    def test_probe_and_publish_are_exclusive_and_probe_also_requires_legacy_retirement(self):
        with self.assertRaises(ValueError):
            release.publish(Path('receipts'), execute=True, draft_probe=True)
        self.run.assert_not_called()
        self.legacy.return_value = True
        with self.assertRaisesRegex(release.AuthorityError, 'Legacy tag publisher'):
            release.publish(Path('receipts'), draft_probe=True)
        self.cli.assert_not_called()


class DraftChildTests(unittest.TestCase):
    def setUp(self):
        self.core = Mock()
        self.core.REPOSITORY = release.REPOSITORY
        self.core.verify_bundle.return_value = ({'tag': 'v2.0.0', 'commit': COMMIT, 'version': '2.0.0'}, {'package.zip': b'bytes'})
        self.core.git.return_value = ('b' * 40 + '\trefs/tags/v2.0.0\n' + COMMIT + '\trefs/tags/v2.0.0^{}\n').encode()
        self.core.notes_for.return_value = 'public notes'
        self.complete = {'draft': True, 'assets': [{'name': 'package.zip'}]}

    def child(self):
        output = io.StringIO()
        with patch.dict('sys.modules', {'publish_release': self.core}), contextlib.redirect_stdout(output):
            release.draft_child('v2.0.0')
        return json.loads(output.getvalue())

    def test_probe_creates_draft_uploads_then_verifies_without_publish_patch_or_latest(self):
        self.core.find_release.side_effect = [None, self.complete]
        self.core.wait_for_created_release.return_value = {'draft': True, 'assets': []}
        report = self.child()
        self.assertTrue(report['draft_verified'])
        self.assertTrue(report['write_performed'])
        self.assertFalse(report['published'])
        commands = [call.args for call in self.core.gh.call_args_list]
        self.assertEqual([cmd[1] for cmd in commands], ['create', 'upload'])
        self.assertIn('--draft', commands[0])
        self.assertIn('--verify-tag', commands[0])
        self.assertNotIn('--latest', str(commands))
        self.core.api.assert_not_called()
        self.core.publish.assert_not_called()

    def test_existing_matching_draft_is_verified_without_claiming_new_write_proof(self):
        self.core.find_release.side_effect = [self.complete, self.complete]
        report = self.child()
        self.assertFalse(report['write_performed'])
        self.core.gh.assert_not_called()

    def test_published_release_and_divergent_draft_are_never_overwritten(self):
        self.core.find_release.return_value = self.complete | {'draft': False}
        with self.assertRaisesRegex(ValueError, 'already published'):
            self.child()
        self.core.gh.assert_not_called()
        self.core.find_release.return_value = self.complete
        self.core.verify_assets.side_effect = ValueError('mismatched assets')
        with self.assertRaisesRegex(ValueError, 'mismatched assets'):
            self.child()
        self.core.gh.assert_not_called()

    def test_unknown_draft_creation_result_is_not_replayed(self):
        self.core.find_release.return_value = None
        self.core.wait_for_created_release.side_effect = RuntimeError('not visible')
        with self.assertRaises(RuntimeError):
            self.child()
        self.assertEqual(self.core.gh.call_count, 1)
        self.core.api.assert_not_called()


class LegacyStateTests(unittest.TestCase):
    def test_git_error_is_not_mistaken_for_retired_workflow(self):
        with patch.object(release, 'run_git', side_effect=subprocess.CalledProcessError(128, ['git'])):
            with self.assertRaises(ValueError):
                release.legacy_publisher_present()
        for text, present in [('.github/workflows/release.yml\n', True), ('', False)]:
            with patch.object(release, 'run_git', return_value=text):
                self.assertEqual(release.legacy_publisher_present(), present)


if __name__ == '__main__':
    unittest.main()
