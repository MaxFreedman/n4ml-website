import fcntl
import hashlib
import io
import json
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile
import unittest

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / 'deploy/site.py'


class InstallerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.work = Path(self.temp.name)
        self.root = self.work / 'server'

    def bundle(self, commit='a' * 40, broken=False):
        files = {'index.html': b'home', 'projects/mb4x-radio-archive/index.html': b'archive',
                 'projects/expeditionops/index.html': b'expedition', 'data/contacts.json': b'{}',
                 'data/manifest.json': b'{}', 'release.json': json.dumps({'commit': commit}).encode()}
        files.update({f'audio/recording-{n:02}.mp3': b'sample audio' for n in range(1, 9)})
        files['checksums.sha256'] = ''.join(
            f'{hashlib.sha256(value).hexdigest()}  {name}\n' for name, value in files.items()).encode()
        if broken:
            files['index.html'] = b'tampered'
        archive = self.work / f'{commit}.tar.gz'
        with tarfile.open(archive, 'w:gz') as bundle:
            for name, content in files.items():
                member = tarfile.TarInfo(name)
                member.size = len(content)
                bundle.addfile(member, io.BytesIO(content))
        return archive

    def run_cli(self, *args, success=True):
        result = subprocess.run([sys.executable, str(SCRIPT), '--root', str(self.root), *map(str, args)],
                                text=True, capture_output=True)
        self.assertEqual(result.returncode == 0, success, result.stdout + result.stderr)
        return result

    def test_install_rollback_and_three_release_retention(self):
        for commit in 'abcde':
            self.run_cli('install', self.bundle(commit * 40))
        self.assertEqual(len(list((self.root / 'releases').iterdir())), 3)
        self.assertEqual(json.loads((self.root / 'current/release.json').read_text())['commit'], 'e' * 40)
        self.assertEqual((self.root / 'current').resolve().stat().st_mode & 0o777, 0o755)
        self.run_cli('rollback')
        self.assertEqual(json.loads((self.root / 'current/release.json').read_text())['commit'], 'd' * 40)
        self.run_cli('rollback')
        self.assertEqual(json.loads((self.root / 'current/release.json').read_text())['commit'], 'e' * 40)

    def test_invalid_release_leaves_current_untouched(self):
        self.run_cli('install', self.bundle())
        current = (self.root / 'current').resolve()
        self.run_cli('install', self.bundle('b' * 40, broken=True), success=False)
        self.assertEqual((self.root / 'current').resolve(), current)
        self.assertEqual(list((self.root / 'releases').glob('.incoming-*')), [])

    def test_corrupt_rollback_target_is_not_activated(self):
        self.run_cli('install', self.bundle())
        self.run_cli('install', self.bundle('b' * 40))
        current = (self.root / 'current').resolve()
        (self.root / 'previous/index.html').write_text('corrupt')
        self.run_cli('rollback', success=False)
        self.assertEqual((self.root / 'current').resolve(), current)

    def test_wrong_commit_is_rejected_before_activation(self):
        self.run_cli('install', self.bundle())
        current = (self.root / 'current').resolve()
        self.run_cli('install', self.bundle('b' * 40), '--commit', 'c' * 40, success=False)
        self.assertEqual((self.root / 'current').resolve(), current)
        self.assertEqual(list((self.root / 'releases').glob('.incoming-*')), [])

    def test_traversal_links_and_oversized_archives_are_rejected(self):
        for kind in ('traversal', 'symlink', 'oversized'):
            with self.subTest(kind=kind):
                archive = self.work / f'{kind}.tar.gz'
                with tarfile.open(archive, 'w:gz') as bundle:
                    entry = tarfile.TarInfo('../escaped' if kind == 'traversal' else 'entry')
                    if kind == 'symlink':
                        entry.type = tarfile.SYMTYPE
                        entry.linkname = '/etc/passwd'
                    elif kind == 'oversized':
                        entry.size = 1024 ** 3 + 1
                        bundle.fileobj.write(entry.tobuf())
                        continue
                    bundle.addfile(entry)
                self.run_cli('install', archive, success=False)
                self.assertFalse((self.root / 'escaped').exists())
                self.assertFalse((self.root / 'current').exists())

    def test_lock_prevents_overlapping_installs(self):
        self.root.mkdir()
        with (self.root / '.deploy.lock').open('a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            self.run_cli('install', self.bundle(), success=False)
        self.assertFalse((self.root / 'current').exists())


if __name__ == '__main__':
    unittest.main()
