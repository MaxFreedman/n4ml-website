#!/usr/bin/env python3
"""Forced SSH command for the unprivileged GitHub deployment key."""
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

ROOT = Path("/srv/n4ml")
MAX_UPLOAD = 1024 ** 3


def main():
    command = os.environ.get("SSH_ORIGINAL_COMMAND", "")
    if command == "status":
        receipt = ROOT / "current/release.json"
        print(receipt.read_text() if receipt.is_file() else '{"status":"not deployed"}')
        return
    match = re.fullmatch(r"deploy ([a-f0-9]{40}) ([a-f0-9]{64})", command)
    if not match:
        raise ValueError("This key only permits deploy and status; shell access is disabled")
    commit, expected_hash = match.groups()
    with (ROOT / ".receive.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if shutil.disk_usage(ROOT).free < 2 * MAX_UPLOAD + 256 * 1024 ** 2:
            raise ValueError("Need at least 2.25 GiB free to receive and unpack a release")
        with tempfile.TemporaryDirectory(prefix="upload-", dir=ROOT / "incoming") as temporary:
            archive = Path(temporary) / "site.tar.gz"
            checksum = hashlib.sha256()
            total = 0
            with archive.open("xb") as output:
                while True:
                    block = sys.stdin.buffer.read(1024 * 1024)
                    if not block:
                        break
                    total += len(block)
                    if total > MAX_UPLOAD:
                        raise ValueError("Upload exceeds the 1 GiB limit")
                    checksum.update(block)
                    output.write(block)
            if checksum.hexdigest() != expected_hash:
                raise ValueError("Upload checksum does not match")
            previous = ROOT / "current/release.json"
            previous_commit = json.loads(previous.read_text())["commit"] if previous.is_file() else None
            subprocess.run(["/usr/local/sbin/n4ml-site", "install", str(archive), "--commit", commit], check=True)
            result = subprocess.run(["/usr/local/libexec/n4ml-check-live", "http://127.0.0.1", commit])
            if result.returncode:
                if previous_commit:
                    subprocess.run(["/usr/local/sbin/n4ml-site", "rollback"], check=True)
                    print(f"Restored previous release {previous_commit}", file=sys.stderr)
                raise ValueError("Live verification failed")
            print(f"Deployment complete: {commit}")


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, KeyError, subprocess.CalledProcessError) as error:
        print(f"Deployment rejected: {error}", file=sys.stderr)
        sys.exit(1)
