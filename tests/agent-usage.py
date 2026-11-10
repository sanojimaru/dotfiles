#!/usr/bin/env python3
"""Isolated CLI checks; never access real settings, session logs or Orca."""
import fcntl
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time
import unittest
from datetime import datetime, timezone

COMMAND = Path(__file__).resolve().parents[1] / 'bin/agent-usage'


class UsageTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name)
        self.env = {**os.environ, 'HOME': str(self.home),
                    'CLAUDE_CONFIG_DIR': str(self.home / '.claude'),
                    'CODEX_HOME': str(self.home / '.codex'), 'CLAUDE_JOB_DIR': ''}
        self.state = self.home / '.claude/agent-usage'
        self.state.mkdir(parents=True)
        self.now = time.time()
        self.reset = self.now + 3600

    def run_cli(self, *args, payload=b''):
        return subprocess.run([str(COMMAND), *args], input=payload,
                              env=self.env, capture_output=True, check=True).stdout.decode()

    def save(self, path, value):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value))

    def delegate(self):
        self.save(self.state / 'delegate.json', {'command': 'cat; printf "orca-output"'})

    def test_capture_preserves_input_output_and_last_valid_sample(self):
        self.delegate()
        payload = json.dumps({'rate_limits': {'seven_day': {
            'used_percentage': 68, 'resets_at': self.reset}}, 'private': 'not cached'}).encode()
        self.assertEqual(self.run_cli('--claude-statusline', payload=payload), payload.decode() + 'orca-output')
        cached = (self.state / 'claude.json').read_text()
        self.assertNotIn('private', cached)
        self.assertEqual((self.state / 'claude.json').stat().st_mode & 0o777, 0o600)
        for bad in (b'{}', b'{"rate_limits":null}', b'invalid'):
            self.run_cli('--claude-statusline', payload=bad)
            self.assertEqual((self.state / 'claude.json').read_text(), cached)
        self.assertIn('Claude（週）: 68%', self.run_cli())

    def claude_payload(self, used, reset):
        return json.dumps({'rate_limits': {'seven_day': {
            'used_percentage': used, 'resets_at': reset}}}).encode()

    def test_cache_failure_does_not_break_delegate(self):
        self.delegate()
        payload = self.claude_payload(68, self.reset)
        (self.state / 'claude.json').mkdir()
        self.assertEqual(self.run_cli('--claude-statusline', payload=payload), payload.decode() + 'orca-output')
        (self.state / '.lock').unlink()
        (self.state / '.lock').mkdir()
        self.assertEqual(self.run_cli('--claude-statusline', payload=payload), payload.decode() + 'orca-output')

    def test_lower_sample_in_same_window_keeps_saved_value_and_time(self):
        self.delegate()
        self.run_cli('--claude-statusline', payload=self.claude_payload(70, self.reset))
        saved = (self.state / 'claude.json').read_text()
        self.run_cli('--claude-statusline', payload=self.claude_payload(60, self.reset))
        self.assertEqual((self.state / 'claude.json').read_text(), saved)
        self.run_cli('--claude-statusline', payload=self.claude_payload(5, self.reset + 604800))
        saved = (self.state / 'claude.json').read_text()
        self.assertIn('Claude（週）: 5%', self.run_cli())
        # An idle session redrawing the previous week must not roll the new week back.
        self.run_cli('--claude-statusline', payload=self.claude_payload(70, self.reset))
        self.assertEqual((self.state / 'claude.json').read_text(), saved)

    def test_capture_waits_for_another_writer_lock(self):
        self.delegate()
        with open(self.state / '.lock', 'a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            proc = subprocess.Popen([str(COMMAND), '--claude-statusline'], stdin=subprocess.PIPE,
                                    stdout=subprocess.PIPE, env=self.env)
            proc.stdin.write(self.claude_payload(70, self.reset))
            proc.stdin.close()
            time.sleep(0.5)
            self.assertIsNone(proc.poll())
            self.assertFalse((self.state / 'claude.json').exists())
        self.assertEqual(proc.wait(timeout=5), 0)
        self.assertIn('Claude（週）: 70%', self.run_cli())

    def event(self, used, observed, primary=True, limit_id='codex'):
        weekly = {'used_percent': used, 'window_minutes': 10080, 'resets_at': self.reset}
        return {'timestamp': datetime.fromtimestamp(observed, timezone.utc).isoformat(),
                'type': 'event_msg', 'payload': {'type': 'token_count', 'rate_limits': {
                    'limit_id': limit_id, 'primary': weekly if primary else None,
                    'secondary': None if primary else weekly}}}

    def test_codex_selects_latest_weekly_event_not_file_mtime_or_model_limit(self):
        root = self.home / '.codex/sessions'
        self.save(root / 'new.jsonl', self.event(23, self.now, primary=False))
        self.save(root / 'old.jsonl', self.event(80, self.now - 200))
        self.save(root / 'model.jsonl', self.event(95, self.now + 2, limit_id='codex-other'))
        with (root / 'new.jsonl').open('a') as stream:
            stream.write('\n{"partial":')
        self.assertIn('Codex（週）: 23%', self.run_cli())
        self.save(root / 'primary.jsonl', self.event(24, self.now + 1))
        self.assertIn('Codex（週）: 24%', self.run_cli())

    def test_codex_uses_event_time_and_only_the_newest_snapshot(self):
        root = self.home / '.codex/sessions'
        self.save(root / 'older-event.jsonl', self.event(30, self.now - 50))
        self.save(root / 'newer-event.jsonl', self.event(31, self.now - 5))
        empty = self.event(0, self.now - 1)
        empty['payload']['rate_limits']['primary'] = None
        with (root / 'newer-event.jsonl').open('a') as stream:
            stream.write('\n' + json.dumps(empty))
        os.utime(root / 'older-event.jsonl', (self.now, self.now))
        os.utime(root / 'newer-event.jsonl', (self.now - 10, self.now - 10))
        out = self.run_cli()
        self.assertIn('Codex（週）: 31%', out)

    def test_missing_stale_and_expired_are_explicit(self):
        out = self.run_cli()
        self.assertIn('Claude（週）: 取得不可', out)
        self.assertIn('最終取得: 不明', out)
        self.assertNotIn('0%', out)
        self.save(self.state / 'claude.json', {'used_percent': 68,
                  'observed_at': self.now - 1000, 'resets_at': self.now - 1})
        out = self.run_cli()
        self.assertIn('古い値', out)
        self.assertIn('リセット日時経過', out)
        self.assertIn('Claude（週）: 68%', out)

    def test_install_preserves_orca_command_and_other_settings(self):
        link = self.home / '.local/bin/agent-usage'
        link.parent.mkdir(parents=True)
        link.symlink_to(COMMAND)
        original = 'echo agent-hooks/claude-statusline.sh'
        settings_path = self.home / '.claude/settings.json'
        self.save(settings_path, {'statusLine': {'type': 'command', 'command': original, 'padding': 2},
                                  'other': {'keep': True}})
        self.run_cli('--install-claude-statusline')
        settings = json.loads(settings_path.read_text())
        self.assertEqual(settings['other'], {'keep': True})
        self.assertEqual(settings['statusLine']['padding'], 2)
        self.assertNotIn('agent-hooks/claude-statusline', settings['statusLine']['command'])
        self.assertEqual(json.loads((self.state / 'delegate.json').read_text())['command'], original)
        self.run_cli('--install-claude-statusline')
        self.assertEqual(json.loads((self.state / 'delegate.json').read_text())['command'], original)
        self.assertEqual(self.run_cli('--claude-statusline'), 'agent-hooks/claude-statusline.sh\n')

    def test_install_rejects_missing_status_line_without_changes(self):
        settings_path = self.home / '.claude/settings.json'
        for value in (None, 'echo agent-hooks/claude-statusline.sh', {'command': None}):
            self.save(settings_path, {'statusLine': value})
            before = settings_path.read_text()
            result = subprocess.run([str(COMMAND), '--install-claude-statusline'], env=self.env,
                                    capture_output=True, text=True)
            self.assertEqual(result.returncode, 1)
            self.assertNotIn('Traceback', result.stderr)
            self.assertEqual(settings_path.read_text(), before)
            self.assertFalse((self.state / 'delegate.json').exists())


if __name__ == '__main__':
    unittest.main()
