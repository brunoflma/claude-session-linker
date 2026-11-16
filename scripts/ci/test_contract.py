"""Pure tests: no GUI, real profiles, network, provisioning or publication."""
import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import gate
import native


def host_for(lane):
    os_name, arch, series = native.LANES[lane]
    return {'platform': os_name, 'machine': arch, 'python': native.runtime_pin(os_name, series)['version'],
            'windows_build': 26100, 'windows_product_type': 3,
            'macos_version': '15.6', 'arm_hardware': arch == 'arm64'}


class HostChecks(unittest.TestCase):
    def test_six_required_native_lanes(self):
        self.assertEqual(len(native.LANES), 6)
        for lane in native.LANES:
            native.check_host(lane, host_for(lane), 'validation')

    def test_windows_2022_probe_cannot_count_as_2025(self):
        host = host_for('windows-py314') | {'windows_build': 20348}
        native.check_host('windows-py314', host, 'probe')
        with self.assertRaisesRegex(ValueError, 'probe-only'):
            native.check_host('windows-py314', host, 'validation')

    def test_linux_wrong_python_macos_and_architecture_fail_closed(self):
        for lane, changes in [
            ('windows-py311', {'platform': 'linux'}),
            ('windows-py315', {'python': '3.14.9'}),
            ('windows-py314', {'python': '3.14.9'}),
            ('windows-py314', {'windows_product_type': 1}),
            ('macos-arm-py314', {'machine': 'x86_64'}),
            ('macos-arm-py315', {'macos_version': '14.7'}),
            ('macos-intel-py314', {'arm_hardware': True}),
        ]:
            with self.subTest(lane=lane, changes=changes), self.assertRaises(ValueError):
                native.check_host(lane, host_for(lane) | changes, 'validation')

    def test_identity_requires_actual_circleci_context(self):
        with self.assertRaises(ValueError):
            native.identity({'GITHUB_RUN_ID': '123'})


class EvidenceGateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='csl-ci-test-')
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.expected = {'CIRCLE_SHA1': 'a' * 40, 'CIRCLE_WORKFLOW_ID': 'workflow-A',
                         'CSL_PIPELINE_ID': 'pipeline-A', 'CIRCLE_TAG': 'v2.0.0'}
        self.receipts = {}
        for index, lane in enumerate(native.LANES):
            receipt = {'schema': 1, 'provider': 'circleci', 'lane': lane,
                       'mode': 'validation', 'status': 'passed', 'gui_checked': True,
                       'config_sha256': 'digest', 'commit': self.expected['CIRCLE_SHA1'],
                       'host': host_for(lane),
                       'identity': self.expected | {'CIRCLE_BUILD_NUM': str(index + 1),
                                                   'CIRCLE_JOB': lane,
                                                   'CIRCLE_BUILD_URL': f'https://circleci.com/job/{index + 1}'}}
            self.receipts[lane] = receipt
        self.write()

    def write(self):
        for lane, receipt in self.receipts.items():
            (self.directory / f'{lane}.json').write_text(json.dumps(receipt), encoding='utf-8')

    def verify(self):
        return gate.verify_receipts(self.directory, self.expected, 'digest')

    def test_complete_same_workflow_native_evidence_passes(self):
        self.assertEqual(self.verify(), sorted(native.LANES))

    def test_missing_lane_cannot_be_skipped(self):
        (self.directory / 'macos-arm-py315.json').unlink()
        with self.assertRaisesRegex(ValueError, 'all six'):
            self.verify()

    def test_probe_gui_false_config_mismatch_and_stale_identity_rejected(self):
        lane = 'windows-py314'
        original = copy.deepcopy(self.receipts[lane])
        cases = [{'mode': 'probe', 'status': 'probe-passed'}, {'gui_checked': False},
                 {'config_sha256': 'other'}, {'commit': 'b' * 40}, {'provider': 'github'}]
        for key in self.expected:
            cases.append({'identity': original['identity'] | {key: 'foreign'}})
        for changes in cases:
            with self.subTest(changes=changes):
                self.receipts[lane] = original | changes
                self.write()
                with self.assertRaises(ValueError):
                    self.verify()

    def test_build_cannot_supply_two_native_lanes(self):
        self.receipts['windows-py314']['identity']['CIRCLE_BUILD_NUM'] = '1'
        self.write()
        with self.assertRaisesRegex(ValueError, 'separate'):
            self.verify()

    def test_windows2022_cannot_pass_by_renaming_probe_status(self):
        self.receipts['windows-py311']['host']['windows_build'] = 20348
        self.write()
        with self.assertRaisesRegex(ValueError, 'probe-only'):
            self.verify()

    def test_extra_receipt_rejected(self):
        (self.directory / 'unexpected.json').write_text('{}')
        with self.assertRaisesRegex(ValueError, 'all six'):
            self.verify()

    def supported(self):
        return gate.verify_receipts(self.directory, self.expected, 'digest', 'supported-native')

    def remove_intel(self):
        (self.directory / 'macos-intel-py314.json').unlink()

    def test_supported_gate_accepts_exactly_five_real_native_lanes(self):
        self.remove_intel()
        passed = self.supported()
        self.assertEqual(len(passed), 5)
        self.assertNotIn('macos-intel-py314', passed)
        with self.assertRaisesRegex(ValueError, 'all six'):
            self.verify()

    def test_supported_gate_refuses_missing_or_extra_native_lane(self):
        with self.assertRaisesRegex(ValueError, 'all five'):
            self.supported()
        self.remove_intel()
        (self.directory / 'windows-py315.json').unlink()
        with self.assertRaisesRegex(ValueError, 'all five'):
            self.supported()

    def test_supported_gate_preserves_provenance_gui_and_host_guards(self):
        self.remove_intel()
        lane = 'macos-arm-py315'
        original = copy.deepcopy(self.receipts[lane])
        cases = [{'mode': 'probe', 'status': 'probe-passed'}, {'gui_checked': False},
                 {'config_sha256': 'different'}, {'provider': 'github'},
                 {'identity': original['identity'] | {'CIRCLE_WORKFLOW_ID': 'old'}},
                 {'identity': original['identity'] | {'CSL_PIPELINE_ID': 'old'}},
                 {'identity': original['identity'] | {'CIRCLE_TAG': 'v1.0.0'}},
                 {'commit': 'b' * 40},
                 {'host': original['host'] | {'machine': 'x86_64'}}]
        for changes in cases:
            with self.subTest(changes=changes):
                (self.directory / f'{lane}.json').write_text(json.dumps(original | changes))
                with self.assertRaises(ValueError):
                    self.supported()

    def test_supported_scope_cannot_authorize_release(self):
        with self.assertRaisesRegex(ValueError, 'never Intel or release'):
            gate.check_scope('supported-native', release=True)
        with self.assertRaisesRegex(ValueError, 'Unknown'):
            gate.check_scope('arbitrary-subset')

    def test_supported_cli_reports_no_intel_or_release_authority(self):
        self.remove_intel()
        env = self.expected | {'CIRCLECI': 'true', 'CIRCLE_BUILD_NUM': '90',
                               'CIRCLE_JOB': 'supported-native-coverage',
                               'CIRCLE_BUILD_URL': 'https://circleci.com/job/90'}
        import contextlib
        import io
        output = io.StringIO()
        with patch.dict(gate.os.environ, env), patch.object(gate, 'git', return_value=self.expected['CIRCLE_SHA1']), \
                patch.object(gate, 'config_digest', return_value='digest'), \
                patch('sys.argv', ['gate.py', '--receipts', str(self.directory), '--expectation', 'supported-native']), \
                contextlib.redirect_stdout(output):
            gate.main()
        report = json.loads(output.getvalue())
        self.assertEqual(len(report['native_lanes']), 5)
        for field in ('intel_verified', 'complete_native_coverage', 'release_authorized', 'release_preflight', 'published'):
            self.assertIs(report[field], False)

    def test_release_cli_rejects_supported_scope_before_reading_context_or_executing(self):
        with patch('sys.argv', ['gate.py', '--receipts', str(self.directory),
                                '--expectation', 'supported-native', '--release']), \
                patch.object(gate, 'identity') as context, patch.object(gate.subprocess, 'run') as effect:
            with self.assertRaisesRegex(ValueError, 'never Intel or release'):
                gate.main()
            context.assert_not_called()
            effect.assert_not_called()


class TagChecks(unittest.TestCase):
    def test_annotated_tag_must_point_to_pipeline_commit(self):
        with patch('gate.git', return_value='unused'):
            gate.check_release_tag('v2.0.0', 'commit', resolve=lambda *args: 'tag' if args[0] == 'cat-file' else 'commit')
        with self.assertRaisesRegex(ValueError, 'annotated'):
            gate.check_release_tag('v2.0.0', 'commit', resolve=lambda *args: 'commit')
        with self.assertRaisesRegex(ValueError, 'pipeline commit'):
            gate.check_release_tag('v2.0.0', 'commit', resolve=lambda *args: 'tag')
        for tag in ('main', 'v2.0', 'v2.0.0-rc1', 'v02.0.0'):
            with self.subTest(tag=tag), self.assertRaises(ValueError):
                gate.check_release_tag(tag, 'commit')


class NativeFailureTests(unittest.TestCase):
    def test_failed_gui_smoke_never_emits_success_evidence(self):
        with tempfile.TemporaryDirectory(prefix='csl-ci-failure-test-') as folder:
            root = Path(folder)
            env = {'CIRCLECI': 'true', 'CIRCLE_SHA1': 'commit', 'CIRCLE_WORKFLOW_ID': 'workflow',
                   'CIRCLE_BUILD_NUM': '1', 'CIRCLE_JOB': 'native',
                   'CIRCLE_BUILD_URL': 'https://circleci.com/job/1', 'CSL_PIPELINE_ID': 'pipeline'}

            def command_result(command, **kwargs):
                if 'scripts/smoke_package.py' in command:
                    raise native.subprocess.CalledProcessError(1, command)

            with patch.object(native, 'ROOT', root), patch.dict(native.os.environ, env), \
                    patch.object(native, 'git', return_value='commit'), \
                    patch.object(native, 'observed_host', return_value=host_for('windows-py314')), \
                    patch.object(native.subprocess, 'run', side_effect=command_result):
                with self.assertRaises(native.subprocess.CalledProcessError):
                    native.run_lane('windows-py314', 'validation')
            self.assertFalse((root / 'release-artifacts/ci-receipts/windows-py314.json').exists())


if __name__ == '__main__':
    unittest.main()
