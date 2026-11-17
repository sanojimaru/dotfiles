#!/usr/bin/env python3
"""本物の Terraform・クラウドを使わず、CLI の許可条件と秘密値の非表示を確かめる。"""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
COMMAND = ROOT / 'bin/terraform-plan-check'


def plan(*actions, **fields):
    return {'format_version': '1.2', 'applyable': True, 'complete': True, 'errored': False,
            'resource_changes': [{'change': {'actions': action}} for action in actions], **fields}


class PlanCheckTest(unittest.TestCase):
    def run_cli(self, value=None, *, raw=None):
        return subprocess.run([sys.executable, str(COMMAND)],
                              input=json.dumps(value) if raw is None else raw,
                              text=True, capture_output=True)

    def test_allowed_actions_can_coexist_across_resources(self):
        result = self.run_cli(plan(['no-op'], ['read'], ['create'], ['update']))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('別途確認', result.stdout)

    def test_one_destructive_or_unknown_resource_blocks_the_whole_plan(self):
        for actions in (['delete'], ['delete', 'create'], ['create', 'delete'],
                        ['forget'], ['create', 'forget'], ['future-action'], [], None):
            with self.subTest(actions=actions):
                result = self.run_cli(plan(['create'], actions, ['update']))
                self.assertEqual(result.returncode, 1, result.stderr)

    def test_missing_actions_or_invalid_resource_shape_is_not_allowed(self):
        for changes in (None, {}, [None], [{}], [{'change': None}], [{'change': {}}]):
            with self.subTest(changes=changes):
                self.assertEqual(self.run_cli(plan(resource_changes=changes)).returncode, 1)

    def test_status_fields_are_required_and_strict_booleans(self):
        for field, values in {'errored': [True, None, 0, 'false'],
                              'complete': [False, None, 1, 'true'],
                              'applyable': [None, 1, 'true']}.items():
            for value in values:
                with self.subTest(field=field, value=value):
                    self.assertEqual(self.run_cli(plan(['create'], **{field: value})).returncode, 1)
            payload = plan(['create'])
            del payload[field]
            with self.subTest(missing=field):
                self.assertEqual(self.run_cli(payload).returncode, 1)

    def test_provider_actions_and_deferred_operations_are_not_ignored(self):
        for field in ('action_invocations', 'deferred_changes', 'deferred_action_invocations'):
            with self.subTest(field=field):
                self.assertEqual(self.run_cli(plan(['create'], **{field: [{}]})).returncode, 1)
                self.assertEqual(self.run_cli(plan(['create'], **{field: []})).returncode, 0)

    def test_format_version_accepts_minor_changes_but_not_unknown_major(self):
        for version, expected in [('1.0', 0), ('1.2', 0), ('1.99', 0), ('2.0', 1),
                                  ('0.1', 1), ('1.', 1), (None, 1), (1.2, 1)]:
            with self.subTest(version=version):
                self.assertEqual(self.run_cli(plan(['create'], format_version=version)).returncode, expected)

    def test_output_only_plan_is_supported(self):
        payload = plan(output_changes={'example': {'actions': ['update']}})
        del payload['resource_changes']
        self.assertEqual(self.run_cli(payload).returncode, 0)

    def test_no_changes_has_a_distinct_exit_code(self):
        for actions in ((), (['no-op'],)):
            with self.subTest(actions=actions):
                result = self.run_cli(plan(*actions, applyable=False))
                self.assertEqual(result.returncode, 3, result.stderr)
                self.assertIn('apply 不要', result.stdout)
        self.assertEqual(self.run_cli(plan(['delete'], applyable=False)).returncode, 1)

    def test_drift_only_plan_needs_confirmation_but_normal_repair_can_pass(self):
        # Terraform 1.17.1 / local_file の外部削除で得た両モードの JSON 構造。
        drift = [{'change': {'actions': ['delete']}}]
        for actions in ((), (['no-op'],), (['read'],)):
            with self.subTest(actions=actions):
                self.assertEqual(self.run_cli(plan(*actions, resource_drift=drift)).returncode, 1)
        for actions in (['create'], ['update']):
            with self.subTest(actions=actions):
                self.assertEqual(self.run_cli(plan(actions, resource_drift=drift)).returncode, 0)
        self.assertEqual(self.run_cli(plan(['create'], resource_drift=None)).returncode, 1)

    def test_invalid_input_never_succeeds_or_leaks_input(self):
        secret = 'SYNTHETIC_SECRET_DO_NOT_PRINT'
        for raw, expected in [('', 2), ('not-json', 2), ('{} {}', 2),
                              ('{"secret": "' + secret, 2), ('{}', 1), ('null', 1),
                              ('[]', 1), (json.dumps(secret), 1)]:
            with self.subTest(raw=raw):
                result = self.run_cli(raw=raw)
                self.assertEqual(result.returncode, expected)
                self.assertNotIn(secret, result.stdout + result.stderr)
                self.assertNotIn('Traceback', result.stderr)

    def test_sensitive_values_are_never_printed_on_success_or_rejection(self):
        secret = 'SYNTHETIC_SECRET_DO_NOT_PRINT'
        for actions in (['create'], ['delete'], [secret]):
            payload = plan(actions)
            payload['variables'] = {'password': {'value': secret}}
            payload['resource_changes'][0]['address'] = secret
            payload['resource_changes'][0]['change']['after'] = {'password': secret}
            result = self.run_cli(payload)
            self.assertEqual(result.returncode, 0 if actions == ['create'] else 1)
            self.assertNotIn(secret, result.stdout + result.stderr)

    def test_upstream_show_failure_is_not_hidden_by_successful_json_check(self):
        payload = json.dumps(plan(['create']))
        result = subprocess.run(
            ['bash', '-o', 'pipefail', '-c',
             '(printf "%s" "$1"; exit 7) | "$2" "$3"',
             '_', payload, sys.executable, str(COMMAND)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 7)

    def test_install_provides_a_runnable_command(self):
        with tempfile.TemporaryDirectory() as directory:
            env = {**os.environ, 'HOME': directory,
                   'PATH': str(Path(sys.executable).parent) + os.pathsep + os.environ['PATH']}
            subprocess.run(['bash', str(ROOT / 'install.sh')], env=env,
                           capture_output=True, check=True)
            installed = Path(directory) / '.local/bin/terraform-plan-check'
            result = subprocess.run([str(installed)], input=json.dumps(plan(['create'])),
                                    env=env, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == '__main__':
    unittest.main()
