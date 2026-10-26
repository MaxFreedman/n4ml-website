import os
from pathlib import Path
import subprocess
import sys
import unittest

SCRIPT = Path(__file__).resolve().parents[2] / 'deploy/receive.py'


class ReceiverTests(unittest.TestCase):
    def test_key_cannot_execute_shell_commands(self):
        for command in ('', 'sh', 'cat /etc/shadow', 'deploy',
                        'deploy aaaa bbbb', 'status; id', 'status\nid'):
            with self.subTest(command=command):
                result = subprocess.run([sys.executable, str(SCRIPT)],
                                        env={**os.environ, 'SSH_ORIGINAL_COMMAND': command},
                                        input=b'', capture_output=True)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(b'only permits deploy and status', result.stderr)
