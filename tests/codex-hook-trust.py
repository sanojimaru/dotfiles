#!/usr/bin/env python3
"""bin/codex と bin/codex-hook-trust の検査。本物の codex は呼ばず、偽の app-server で確かめる。"""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

BIN = Path(__file__).resolve().parents[1] / 'bin'

# hooks/list に FAKE_HOOKS の内容を返し、config/batchWrite で受け取った値を FAKE_WRITES に足す偽の codex。
# 書いたキーは次の hooks/list から trusted を返す。app-server 以外で起動されたら引数を FAKE_EXEC に書く。
FAKE_CODEX = r'''#!/usr/bin/env python3
import json, os, sys
if sys.argv[1:] != ['app-server']:
    open(os.environ['FAKE_EXEC'], 'w').write(json.dumps(sys.argv[1:]))
    sys.exit(0)
hooks = json.load(open(os.environ['FAKE_HOOKS']))
trusted = set()
for line in sys.stdin:
    msg = json.loads(line)
    if 'id' not in msg:
        continue
    method, result = msg['method'], {}
    if method == 'hooks/list':
        result = {'data': [{'cwd': msg['params']['cwds'][0], 'errors': [], 'warnings': [], 'hooks': [
            {**h, 'trustStatus': 'trusted' if h['key'] in trusted else h['trustStatus']} for h in hooks]}]}
        with open(os.environ['FAKE_CWDS'], 'a') as f:
            f.write(msg['params']['cwds'][0] + '\n')
    elif method == 'config/batchWrite':
        value = msg['params']['edits'][0]['value']
        trusted |= set(value)
        with open(os.environ['FAKE_WRITES'], 'a') as f:
            f.write(json.dumps(msg['params']) + '\n')
    print(json.dumps({'id': msg['id'], 'result': result}), flush=True)
'''


class CodexHookTrustTest(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.tmp = Path(temp.name).resolve()
        self.fake_bin = self.tmp / 'fake-bin'
        self.fake_bin.mkdir()
        (self.fake_bin / 'codex').write_text(FAKE_CODEX)
        (self.fake_bin / 'codex').chmod(0o755)
        self.files = {name: self.tmp / name.lower() for name in
                      ('FAKE_HOOKS', 'FAKE_WRITES', 'FAKE_EXEC', 'FAKE_CWDS')}
        self.env = {**os.environ, **{k: str(v) for k, v in self.files.items()},
                    'HOME': str(self.tmp), 'GIT_CONFIG_NOSYSTEM': '1',
                    'PATH': f'{BIN}{os.pathsep}{self.fake_bin}{os.pathsep}{os.environ["PATH"]}'}

    def repo(self, name, *remotes):
        path = self.tmp / name
        (path / '.codex').mkdir(parents=True)
        subprocess.run(['git', 'init', '-q', str(path)], check=True, env=self.env)
        for i, url in enumerate(remotes):
            subprocess.run(['git', '-C', str(path), 'remote', 'add', f'r{i}', url], check=True, env=self.env)
        return path / '.codex/hooks.json'

    def hook(self, key, source, status='untrusted', path=None):
        return {'key': key, 'source': source, 'trustStatus': status, 'currentHash': f'sha256:{key}',
                'sourcePath': str(path or self.tmp / 'hooks.json')}

    def run_codex(self, hooks, *args, cwd=None):
        self.files['FAKE_HOOKS'].write_text(json.dumps(hooks))
        out = subprocess.run([str(BIN / 'codex'), *args], env=self.env, cwd=cwd or self.tmp,
                             capture_output=True, text=True, check=True)
        return out.stderr

    def written(self):
        if not self.files['FAKE_WRITES'].exists():
            return {}
        params = [json.loads(line) for line in self.files['FAKE_WRITES'].read_text().splitlines()]
        self.assertTrue(all(p['edits'][0]['keyPath'] == 'hooks.state' and
                            p['edits'][0]['mergeStrategy'] == 'upsert' for p in params))
        return {k: v for p in params for k, v in p['edits'][0]['value'].items()}

    def test_trusts_user_plugin_and_own_project_hooks(self):
        hooks = [
            self.hook('user', 'user'),
            self.hook('plugin', 'plugin', 'modified'),
            self.hook('ssh', 'project', path=self.repo('ssh', 'git@github.com:sanojimaru/dotfiles.git')),
            self.hook('https', 'project', 'modified',
                      self.repo('https', 'https://github.com/SpikeStudio/app', 'https://github.com/sanojimaru/app.git')),
        ]
        stderr = self.run_codex(hooks)
        self.assertEqual(self.written(), {h['key']: {'trusted_hash': h['currentHash']} for h in hooks})
        self.assertIn('フック 4 件を信頼した', stderr)
        self.assertNotIn('信頼しなかった', stderr)

    def test_skips_project_hooks_outside_own_repositories(self):
        own = self.repo('own', 'git@github.com:sanojimaru/x.git')
        hooks = [
            self.hook('own', 'project', path=own),
            self.hook('other', 'project', path=self.repo('other', 'https://github.com/someone/x.git')),
            self.hook('mixed', 'project', path=self.repo(
                'mixed', 'git@github.com:sanojimaru/x.git', 'https://github.com/someone/x.git')),
            self.hook('lookalike', 'project', path=self.repo('lookalike', 'https://github.com/sanojimaru-evil/x')),
            self.hook('gitlab', 'project', path=self.repo('gitlab', 'git@gitlab.com:sanojimaru/x.git')),
            self.hook('local-path', 'project', path=self.repo('local-path', 'github.com/sanojimaru/x')),
            self.hook('no-remote', 'project', path=self.repo('no-remote')),
            self.hook('no-repo', 'project', path=self.tmp / 'plain/.codex/hooks.json'),
        ]
        # 自分のリポジトリの hooks.json が、外のリポジトリのファイルへのリンクになっている。
        linked = self.repo('linked', 'git@github.com:sanojimaru/x.git')
        linked.symlink_to(self.repo('target', 'https://github.com/someone/x.git'))
        hooks.append(self.hook('linked', 'project', path=linked))
        stderr = self.run_codex(hooks)
        self.assertEqual(set(self.written()), {'own'})
        self.assertIn('プロジェクトのフック 8 件は信頼しなかった', stderr)

    def test_leaves_trusted_managed_and_other_sources(self):
        hooks = [self.hook('trusted', 'user', 'trusted'), self.hook('managed', 'project', 'managed'),
                 self.hook('mdm', 'mdm')]
        self.assertEqual(self.run_codex(hooks), '')
        self.assertEqual(self.written(), {})

    def test_wrapper_execs_real_codex_with_same_args_and_cd(self):
        work = self.tmp / 'work'
        work.mkdir()
        for args in (['-C', 'work', 'exec', 'hi'], ['-Cwork', 'exec', 'hi'], ['--cd=work'],
                     ['-C', 'other', 'exec', '-C', 'work']):
            self.files['FAKE_CWDS'].unlink(missing_ok=True)
            self.run_codex([self.hook('user', 'user')], *args)
            self.assertEqual(json.loads(self.files['FAKE_EXEC'].read_text()), args)
            self.assertEqual(self.files['FAKE_CWDS'].read_text().split(), [str(work)] * 2)

    def test_wrapper_leaves_hooks_for_calls_without_session(self):
        for args in (['--version'], ['-c', 'x=1', '--help'], ['login', 'status'], ['completion', 'fish']):
            self.assertEqual(self.run_codex([self.hook('user', 'user')], *args), '')
            self.assertEqual(json.loads(self.files['FAKE_EXEC'].read_text()), args)
        self.assertFalse(self.files['FAKE_CWDS'].exists())
        self.assertEqual(self.written(), {})

    def test_wrapper_still_starts_codex_when_trust_fails(self):
        self.files['FAKE_HOOKS'].write_text('not json')
        out = subprocess.run([str(BIN / 'codex'), 'resume'], env=self.env, cwd=self.tmp,
                             capture_output=True, text=True)
        self.assertEqual(out.returncode, 0)
        self.assertIn('フックを信頼できなかった', out.stderr)
        self.assertEqual(json.loads(self.files['FAKE_EXEC'].read_text()), ['resume'])


if __name__ == '__main__':
    unittest.main(verbosity=2)
