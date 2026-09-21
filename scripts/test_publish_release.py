import unittest
import contextlib
import copy
import io
import tempfile
from pathlib import Path
from unittest.mock import patch
import publish_release as publisher
from publish_release import verify_assets
from release_bundle import sha256


class PublicationChecks(unittest.TestCase):
    def setUp(self):
        self.files = {'package.zip': b'package'}
        self.asset = {'name': 'package.zip', 'state': 'uploaded', 'size': 7, 'digest': 'sha256:' + sha256(b'package')}

    def test_uploaded_digest_and_size_must_match(self):
        verify_assets({'assets': [self.asset]}, self.files)
        for change in ({'digest': 'sha256:' + '0' * 64}, {'size': 1}, {'state': 'new'}, {'digest': None}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                verify_assets({'assets': [{**self.asset, **change}]}, self.files)

    def test_missing_and_unexpected_assets_block_publication(self):
        with self.assertRaises(ValueError):
            verify_assets({'assets': []}, self.files)
        with self.assertRaises(ValueError):
            verify_assets({'assets': [{**self.asset, 'name': 'private.log'}]}, self.files)
        verify_assets({'assets': []}, self.files, require_all=False)


class PublicationFlowTests(unittest.TestCase):
    def setUp(self):
        self.stack = contextlib.ExitStack()
        self.addCleanup(self.stack.close)
        self.tag, self.commit = 'v2.1.0', '1' * 40
        self.directory = Path(self.stack.enter_context(tempfile.TemporaryDirectory(prefix='csl-publish-test-')))
        self.files = {'package.zip': b'package'}
        (self.directory / 'package.zip').write_bytes(b'package')
        self.asset = {'name': 'package.zip', 'state': 'uploaded', 'size': 7, 'digest': 'sha256:' + sha256(b'package'),
                      'browser_download_url': f'https://github.com/{publisher.REPOSITORY}/releases/download/{self.tag}/package.zip'}
        self.published = {'id': 9, 'tag_name': self.tag, 'draft': False, 'assets': [self.asset],
                          'html_url': f'https://github.com/{publisher.REPOSITORY}/releases/tag/{self.tag}'}
        self.draft = {**self.published, 'draft': True}
        self.empty_draft = {**self.draft, 'assets': []}
        self.stack.enter_context(patch.object(publisher, 'verify_bundle', return_value=({'tag': self.tag, 'version': '2.1.0', 'commit': self.commit}, self.files)))
        self.stack.enter_context(patch.object(publisher.subprocess, 'run'))
        self.remote = self.stack.enter_context(patch.object(publisher.subprocess, 'check_output', return_value=f'{self.commit}\trefs/tags/{self.tag}\n'.encode()))
        self.find = self.stack.enter_context(patch.object(publisher, 'find_release', return_value=self.published))
        self.gh = self.stack.enter_context(patch.object(publisher, 'gh'))
        self.api = self.stack.enter_context(patch.object(publisher, 'api'))
        self.records = self.stack.enter_context(patch.object(publisher, 'release_records', return_value=[]))
        self.notes = self.stack.enter_context(patch.object(publisher, 'notes_for', return_value='Release notes\n'))
        self.sleep = self.stack.enter_context(patch.object(publisher.time, 'sleep'))
        self.download = self.stack.enter_context(patch.object(publisher.urllib.request, 'urlopen', side_effect=lambda *a, **kw: io.BytesIO(b'package')))
        self.stack.enter_context(contextlib.redirect_stdout(io.StringIO()))

    def test_published_release_is_verified_without_mutation(self):
        publisher.publish(self.tag, self.directory)
        self.gh.assert_not_called()
        self.api.assert_not_called()
        self.download.assert_called_once()

    def test_fresh_release_is_draft_then_uploaded_then_published(self):
        self.find.side_effect = [None, self.empty_draft, self.draft, self.published]
        order = []
        self.gh.side_effect = lambda *args, **kwargs: order.append(args[1])
        self.api.side_effect = lambda *args, **kwargs: order.append('publish')
        publisher.publish(self.tag, self.directory)
        self.assertEqual(order, ['create', 'upload', 'publish'])
        self.assertIn('--draft', self.gh.call_args_list[0].args)
        self.assertIn('--verify-tag', self.gh.call_args_list[0].args)
        self.assertEqual(self.api.call_args.args[1], {'draft': False, 'make_latest': 'true'})

    def test_resume_uploads_only_missing_assets(self):
        self.find.side_effect = [self.empty_draft, self.draft, self.published]
        publisher.publish(self.tag, self.directory)
        self.gh.assert_called_once_with('release', 'upload', self.tag, str(self.directory / 'package.zip'))
        self.notes.assert_not_called()

    def test_new_draft_waits_for_release_list_visibility(self):
        self.find.side_effect = [None, None, self.empty_draft, self.draft, self.published]
        publisher.publish(self.tag, self.directory)
        self.sleep.assert_called_once_with(2)
        self.assertEqual([call.args[1] for call in self.gh.call_args_list], ['create', 'upload'])

    def test_invisible_draft_times_out_without_upload_or_publication(self):
        self.find.return_value = None
        with self.assertRaisesRegex(RuntimeError, 'safely rerun'):
            publisher.publish(self.tag, self.directory)
        self.assertEqual(self.find.call_count, 9)
        self.assertEqual(self.sleep.call_count, 7)
        self.gh.assert_called_once()
        self.assertEqual(self.gh.call_args.args[1], 'create')
        self.api.assert_not_called()

    def test_mismatched_draft_is_not_overwritten(self):
        wrong = copy.deepcopy(self.draft)
        wrong['assets'][0]['digest'] = 'sha256:' + '0' * 64
        self.find.return_value = wrong
        with self.assertRaisesRegex(ValueError, 'package.zip'):
            publisher.publish(self.tag, self.directory)
        self.gh.assert_not_called()
        self.api.assert_not_called()

    def test_remote_tag_mismatch_stops_before_release_lookup(self):
        self.remote.return_value = f'{"2" * 40}\trefs/tags/{self.tag}\n'.encode()
        with self.assertRaisesRegex(ValueError, 'Remote tag'):
            publisher.publish(self.tag, self.directory)
        self.find.assert_not_called()
        self.gh.assert_not_called()

    def test_annotated_tag_uses_the_peeled_commit(self):
        self.remote.return_value = f'{"2" * 40}\trefs/tags/{self.tag}\n{self.commit}\trefs/tags/{self.tag}^{{}}\n'.encode()
        publisher.publish(self.tag, self.directory)
        self.download.assert_called_once()

    def test_resuming_old_draft_does_not_demote_newer_stable_release(self):
        self.find.side_effect = [self.draft, self.draft, self.published]
        self.records.return_value = [{'tag_name': 'v2.2.0', 'draft': False, 'prerelease': False}]
        publisher.publish(self.tag, self.directory)
        self.gh.assert_not_called()
        self.assertEqual(self.api.call_args.args[1]['make_latest'], 'false')

    def test_verify_only_rejects_draft_without_mutation(self):
        self.find.return_value = self.draft
        with self.assertRaisesRegex(ValueError, 'published release'):
            publisher.publish(self.tag, self.directory, verify_only=True)
        self.gh.assert_not_called()
        self.api.assert_not_called()

    def test_public_download_bytes_are_checked_in_addition_to_metadata(self):
        self.download.side_effect = lambda *a, **kw: io.BytesIO(b'different bytes')
        with self.assertRaisesRegex(ValueError, 'Public download differs'):
            publisher.publish(self.tag, self.directory, verify_only=True)


class ReleaseNotesTests(unittest.TestCase):
    def test_notes_must_exist_for_exact_version(self):
        with patch.object(publisher, 'git', return_value=b'## [2.0.0] - earlier\n\nPrevious notes\n'):
            with self.assertRaisesRegex(ValueError, 'notes are missing'):
                publisher.notes_for('v2.1.0')

    def test_notes_stop_before_previous_version(self):
        with patch.object(publisher, 'git', return_value=b'## [2.1.0] - today\n\nCurrent notes\n\n## [2.0.0]\n\nOld notes\n'):
            self.assertEqual(publisher.notes_for('v2.1.0'), 'Current notes\n')


if __name__ == '__main__':
    unittest.main()
