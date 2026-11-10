#!/usr/bin/env python3
"""Isolated CLI checks; never access real settings, session logs or Orca."""
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


if __name__ == '__main__':
    unittest.main()
