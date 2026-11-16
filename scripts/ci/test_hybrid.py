"""Hybrid proof tests: synthetic API responses; no network, GUI or release effects."""
import base64
import copy
import hashlib
import io
import json
import os
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import Mock, patch
from urllib.parse import urlsplit
import hybrid

COMMIT = 'a' * 40
SOURCE = (hybrid.ROOT / hybrid.WORKFLOW_PATH).read_bytes().replace(b'\r\n', b'\n')


class API:
    def __init__(self):
        self.calls = []
        self.repository = {'id': hybrid.REPOSITORY_ID, 'full_name': hybrid.REPOSITORY, 'private': False}
        self.workflow = {'id': 77, 'path': hybrid.WORKFLOW_PATH, 'state': 'active'}
        blob = hashlib.sha1(b'blob ' + str(len(SOURCE)).encode() + b'\0' + SOURCE).hexdigest()
        self.content = {'encoding': 'base64', 'content': base64.b64encode(SOURCE).decode(), 'sha': blob}
        self.run = {'id': 101, 'run_number': 9, 'run_attempt': 1, 'workflow_id': 77,
                    'path': hybrid.WORKFLOW_PATH, 'head_sha': COMMIT, 'event': 'push',
                    'head_branch': 'v2.0.0', 'repository': self.repository, 'head_repository': self.repository,
                    'status': 'completed', 'conclusion': 'success'}
        self.runs = [self.run]
        self.current = self.run
        self.job = {'id': 501, 'name': hybrid.INTEL_JOB, 'run_id': 101, 'head_sha': COMMIT,
                    'run_attempt': 1, 'status': 'completed', 'conclusion': 'success',
                    'labels': ['macos-15-intel'],
                    'steps': [{'name': name, 'number': i + 3, 'status': 'completed', 'conclusion': 'success'}
                              for i, name in enumerate(hybrid.REQUIRED_STEPS)]}
        self.jobs = [self.job]

    def __call__(self, path):
        self.calls.append(path)
        route = urlsplit(path).path
        root = '/repos/' + hybrid.REPOSITORY
        if route == root:
            result = self.repository
        elif route == root + '/actions/workflows/validate.yml':
            result = self.workflow
        elif route == root + '/contents/' + hybrid.WORKFLOW_PATH:
            result = self.content
        elif route == root + '/actions/workflows/validate.yml/runs':
            result = {'total_count': len(self.runs), 'workflow_runs': self.runs}
        elif route == root + '/actions/runs/101/attempts/1':
            result = self.run
        elif route == root + '/actions/runs/101/attempts/1/jobs':
            result = {'total_count': len(self.jobs), 'jobs': self.jobs}
        elif route == root + '/actions/runs/101':
            result = self.current
        else:
            raise AssertionError('Unexpected API route: ' + path)
        return copy.deepcopy(result)


class IntelProofTests(unittest.TestCase):
    def verify(self, api, tag='v2.0.0', **kwargs):
        return hybrid.verify_intel(COMMIT, SOURCE, tag, api=api, attempts=1, **kwargs)

    def test_reviewed_workflow_is_intel_only_and_sha_checkout_with_gui(self):
        self.assertEqual(hashlib.sha256(SOURCE).hexdigest(), hybrid.WORKFLOW_SHA256)
        text = SOURCE.decode()
        self.assertEqual(text.count('- os:'), 1)
        self.assertIn('macos-15-intel', text)
        self.assertIn('github.event.pull_request.head.sha || github.sha', text)
        self.assertIn('workflow_dispatch:', text)
        self.assertIn("tags: ['v*']", text)
        self.assertIn('python scripts/smoke_package.py --ref HEAD --gui', text)

    def test_complete_tag_proof_has_real_provider_ids_and_content_version(self):
        api = API()
        result = self.verify(api)
        self.assertEqual(result['provider'], 'github-actions')
        self.assertEqual((result['run_id'], result['job_id'], result['run_attempt']), (101, 501, 1))
        self.assertEqual(result['workflow_sha256'], hybrid.WORKFLOW_SHA256)
        self.assertEqual(result['tag'], 'v2.0.0')
        self.assertTrue(result['gui_checked'])
        self.assertFalse(any(key.startswith('GITHUB_') for key in os.environ if key in result))

    def test_wrong_repo_private_or_workflow_version_fails_closed(self):
        cases = [('repository', {'id': 8}), ('repository', {'private': True}),
                 ('repository', {'full_name': 'other/repository'}), ('workflow', {'path': '.github/workflows/release.yml'}),
                 ('workflow', {'state': 'disabled_manually'}), ('content', {'sha': 'b' * 40}),
                 ('content', {'content': base64.b64encode(b'unreviewed').decode()})]
        for name, changes in cases:
            with self.subTest(name=name, changes=changes):
                api = API()
                getattr(api, name).update(changes)
                with self.assertRaises(ValueError):
                    self.verify(api)
        with self.assertRaisesRegex(ValueError, 'reviewed CI policy'):
            hybrid.verify_intel(COMMIT, b'changed source', api=API(), attempts=1)

    def test_release_refuses_wrong_sha_repo_path_event_and_tag(self):
        for changes in [{'head_sha': 'b' * 40}, {'head_repository': {'id': 7}},
                        {'repository': {'id': 7}}, {'workflow_id': 88},
                        {'path': '.github/workflows/release.yml'}, {'event': 'workflow_dispatch'},
                        {'event': 'pull_request'}, {'head_branch': 'main'}]:
            with self.subTest(changes=changes):
                api = API()
                api.run.update(changes)
                with self.assertRaises(TimeoutError):
                    self.verify(api)

    def test_manual_and_pr_runs_can_prove_validation_but_never_release(self):
        for event in ('pull_request', 'workflow_dispatch'):
            api = API()
            api.run.update(event=event, head_branch='codex/example')
            self.assertEqual(self.verify(api, tag='')['event'], event)
            with self.assertRaises(TimeoutError):
                self.verify(api)

    def test_latest_failure_cannot_be_replaced_with_older_green_run(self):
        api = API()
        older = copy.deepcopy(api.run)
        older.update(id=99, run_number=8)
        api.runs.append(older)
        api.run['conclusion'] = 'failure'
        with self.assertRaisesRegex(ValueError, 'older successes'):
            self.verify(api)

    def test_intel_skipped_failed_missing_gui_or_arm_label_is_not_success(self):
        for change in ('skipped', 'failure', 'missing', 'duplicate', 'arm', 'sha', 'run', 'attempt'):
            with self.subTest(change=change):
                api = API()
                gui = next(step for step in api.job['steps'] if step['name'].startswith('Open the extracted'))
                if change in ('skipped', 'failure'):
                    gui['conclusion'] = change
                elif change == 'missing':
                    api.job['steps'].remove(gui)
                elif change == 'duplicate':
                    api.job['steps'].append(gui)
                elif change == 'arm':
                    api.job['labels'] = ['macos-15']
                elif change == 'sha':
                    api.job['head_sha'] = 'b' * 40
                elif change == 'run':
                    api.job['run_id'] = 99
                else:
                    api.job['run_attempt'] = 2
                with self.assertRaises(ValueError):
                    self.verify(api)

    def test_rerun_started_during_inspection_invalidates_proof(self):
        api = API()
        api.current = api.run | {'run_attempt': 2, 'status': 'in_progress', 'conclusion': None}
        with self.assertRaisesRegex(ValueError, 'changed during verification'):
            self.verify(api)

    def test_pending_run_poll_is_bounded_and_never_uses_real_sleep(self):
        api = API()
        api.run.update(status='in_progress', conclusion=None)
        sleeps = []
        with patch('builtins.print'):
            with self.assertRaises(TimeoutError):
                hybrid.verify_intel(COMMIT, SOURCE, api=api, attempts=3, interval=2, sleep=sleeps.append)
        self.assertEqual(sleeps, [2, 2])
        self.assertEqual(sum('/runs?' in path for path in api.calls), 3)
        self.assertFalse(any('/jobs?' in path for path in api.calls))

    def test_incomplete_pagination_or_invalid_poll_policy_is_rejected(self):
        api = Mock(return_value={'total_count': 3, 'jobs': [1]})
        with self.assertRaisesRegex(ValueError, 'pagination incomplete'):
            hybrid.pages(api, '/jobs', 'jobs')
        self.assertEqual(api.call_count, 2)
        for changes in ({'attempts': 25}, {'interval': 31}, {'attempts': 0}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                hybrid.verify_intel(COMMIT, SOURCE, api=API(), **changes)


class PublicHTTPTests(unittest.TestCase):
    def test_all_owned_git_commands_are_captured_and_cannot_start_pager(self):
        result = Mock(stdout='ok')
        with patch.object(hybrid.subprocess, 'run', return_value=result) as run:
            self.assertEqual(hybrid.run_git('diff', '--check'), 'ok')
        self.assertEqual(run.call_args.args[0][:2], ['git', '--no-pager'])
        self.assertTrue(run.call_args.kwargs['capture_output'])
        self.assertEqual(run.call_args.kwargs['env']['GIT_PAGER'], 'cat')
        self.assertEqual(run.call_args.kwargs['env']['GIT_TERMINAL_PROMPT'], '0')

    def test_public_get_never_uses_ambient_token(self):
        opener = Mock()
        opener.open.return_value = io.BytesIO(b'{"id": 1}')
        with patch.dict(os.environ, {'GH_TOKEN': 'ghs_SYNTHETIC_CANARY'}), \
                patch('hybrid.urllib.request.build_opener', return_value=opener):
            self.assertEqual(hybrid.get_json('/repos/' + hybrid.REPOSITORY), {'id': 1})
        request = opener.open.call_args.args[0]
        self.assertEqual(request.get_method(), 'GET')
        self.assertFalse(any(key.lower() == 'authorization' for key, _ in request.header_items()))

    def test_api_errors_are_errors_and_do_not_echo_response_or_credential(self):
        opener = Mock()
        opener.open.side_effect = urllib.error.HTTPError('https://api.github.com', 403, 'secret-canary', {}, None)
        with patch('hybrid.urllib.request.build_opener', return_value=opener):
            with self.assertRaisesRegex(RuntimeError, 'HTTP 403') as failure:
                hybrid.get_json('/repos/' + hybrid.REPOSITORY)
        self.assertNotIn('secret-canary', str(failure.exception))
        with patch('hybrid.urllib.request.build_opener') as network, self.assertRaises(ValueError):
            hybrid.get_json('/repos/other/repository')
        network.assert_not_called()


class HybridCompositionTests(unittest.TestCase):
    def test_five_circleci_receipts_and_intel_remain_separate_providers(self):
        context = {'CIRCLE_SHA1': COMMIT, 'CIRCLE_TAG': ''}
        intel = {'provider': 'github-actions', 'run_id': 101, 'job_id': 501}
        with patch.object(hybrid, 'identity', return_value=context), patch.object(hybrid, 'git', return_value=COMMIT), \
                patch.object(hybrid, 'config_digest', return_value='digest'), \
                patch.object(hybrid, 'verify_receipts', return_value=['lane'] * 5) as receipts, \
                patch.object(hybrid, 'workflow_source', return_value=SOURCE), \
                patch.object(hybrid, 'verify_intel', return_value=intel):
            result = hybrid.verify_hybrid(Path('synthetic-receipts'))
        self.assertEqual(receipts.call_args.args[-1], 'supported-native')
        self.assertEqual(result['intel'], intel)
        self.assertTrue(result['complete_coverage'])
        self.assertFalse(result['published'])
        self.assertFalse(result['release_authorized'])

    def test_release_preflight_rejects_changed_annotated_object_even_for_same_commit(self):
        expected = {'CIRCLE_SHA1': COMMIT, 'CIRCLE_TAG': 'v2.0.0'}
        remote = 'c' * 40 + '\trefs/tags/v2.0.0\n' + COMMIT + '\trefs/tags/v2.0.0^{}\n'
        with patch.object(hybrid, 'check_release_tag'), \
                patch.object(hybrid, 'run_git', side_effect=['', remote]), \
                patch.object(hybrid, 'git', return_value='b' * 40):
            with self.assertRaisesRegex(ValueError, 'annotated tag/object changed'):
                hybrid.release_preflight(expected)


if __name__ == '__main__':
    unittest.main()
