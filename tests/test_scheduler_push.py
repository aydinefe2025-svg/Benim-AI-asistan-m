"""Run the actual workflow push code against isolated local Git remotes."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

WORKFLOW = Path(__file__).resolve().parents[1] / '.github/workflows/daily-research-archive.yml'


def push_code():
    text = WORKFLOW.read_text(encoding='utf-8-sig')
    code = text.split('          # BEGIN bounded archive push\n', 1)[1]
    code = code.split('          # END bounded archive push', 1)[0]
    return 'import subprocess\nimport sys\n' + '\n'.join(line[10:] for line in code.splitlines())


class ArchivePushTests(unittest.TestCase):
    def test_push_outage_is_bounded_to_three_attempts(self):
        def run(command, **kwargs):
            return subprocess.CompletedProcess(command, 1 if command[1] == 'push' else 0)
        with patch.dict(os.environ, {'ARCHIVE_TARGET_BRANCH': 'test-archive'}):
            with patch('subprocess.run', side_effect=run) as calls:
                with self.assertRaisesRegex(SystemExit, '3 attempts'):
                    exec(compile(push_code(), str(WORKFLOW), 'exec'), {})
        commands = [call.args[0][1] for call in calls.call_args_list]
        self.assertEqual(commands, ['push', 'fetch', 'rebase', 'push', 'fetch', 'rebase', 'push'])

    def test_clean_push_and_concurrent_changes(self):
        for conflict in (None, False, True):
            with self.subTest(conflict=conflict), tempfile.TemporaryDirectory() as folder:
                root = Path(folder)
                remote, worker, peer = (root / name for name in ('remote.git', 'worker', 'peer'))
                env = dict(os.environ, GIT_AUTHOR_NAME='Test', GIT_AUTHOR_EMAIL='test@example.org',
                           GIT_COMMITTER_NAME='Test', GIT_COMMITTER_EMAIL='test@example.org',
                           GIT_TERMINAL_PROMPT='0', GIT_CONFIG_NOSYSTEM='1')

                def git(where, *args):
                    return subprocess.run(['git', '-C', str(where), *args], env=env,
                                          text=True, capture_output=True, check=True).stdout.strip()

                subprocess.run(['git', 'init', '--bare', str(remote)], env=env,
                               capture_output=True, check=True)
                subprocess.run(['git', 'clone', str(remote), str(worker)], env=env,
                               capture_output=True, check=True)
                branch = 'fix/sqlite-backup-restore-20261031'
                git(worker, 'checkout', '-b', branch)
                (worker / 'report.json').write_text('old\n')
                git(worker, 'add', '.')
                git(worker, 'commit', '-m', 'initial')
                git(worker, 'push', 'origin', branch)
                subprocess.run(['git', 'clone', '--branch', branch, str(remote), str(peer)],
                               env=env, capture_output=True, check=True)
                (worker / 'report.json').write_text('new report\n')
                git(worker, 'add', '.')
                git(worker, 'commit', '-m', 'report')
                if conflict is not None:
                    path = peer / ('report.json' if conflict else 'peer.txt')
                    path.write_text('concurrent author data\n')
                    git(peer, 'add', '.')
                    git(peer, 'commit', '-m', 'peer change')
                    git(peer, 'push', 'origin', branch)
                previous_remote = git(remote, 'rev-parse', 'refs/heads/' + branch)
                result = subprocess.run([sys.executable, '-c', push_code()], cwd=worker,
                                        env=env, text=True, capture_output=True, timeout=30)
                if conflict:
                    self.assertNotEqual(result.returncode, 0)
                    self.assertEqual(git(remote, 'rev-parse', 'refs/heads/' + branch), previous_remote)
                    self.assertEqual(git(remote, 'show', branch + ':report.json'), 'concurrent author data')
                else:
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertEqual(git(remote, 'show', branch + ':report.json'), 'new report')
                    if conflict is False:
                        self.assertEqual(git(remote, 'show', branch + ':peer.txt'), 'concurrent author data')
                        self.assertIn('peer change', git(remote, 'log', '--format=%s', branch))


if __name__ == '__main__':
    unittest.main()
