#!/usr/bin/env python3
"""Bounded, verified static releases. Only Python's standard library is needed."""
import argparse
import datetime
import fcntl
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import sys
import tarfile
import tempfile

MAX_BYTES = 1024 ** 3
RELEASE_ID = re.compile(r"\d{8}T\d{12}Z-[a-f0-9]{7,40}\Z")


def relative(name):
    path = PurePosixPath(name)
    if path.is_absolute() or ".." in path.parts or "\\" in name:
        raise ValueError(f"Unsafe archive path: {name}")
    return path


def digest(path):
    value = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def verify(folder):
    expected = {}
    for line in (folder / "checksums.sha256").read_text().splitlines():
        match = re.fullmatch(r"([a-f0-9]{64})  (.+)", line)
        if not match:
            raise ValueError("Invalid checksums.sha256")
        checksum, name = match.groups()
        path = relative(name).as_posix()
        if path in expected or path == "checksums.sha256":
            raise ValueError("Duplicate or self-referencing checksum")
        expected[path] = checksum
    actual = {p.relative_to(folder).as_posix() for p in folder.rglob("*") if p.is_file()}
    if actual != set(expected) | {"checksums.sha256"}:
        raise ValueError("Release inventory does not match its checksums")
    for name, checksum in expected.items():
        if digest(folder / name) != checksum:
            raise ValueError(f"Checksum failed: {name}")
    required = ["index.html", "projects/mb4x-radio-archive/index.html",
                "projects/expeditionops/index.html", "data/contacts.json", "data/manifest.json"]
    required += [f"audio/recording-{number:02}.mp3" for number in range(1, 9)]
    if any(not (folder / name).is_file() or (folder / name).stat().st_size == 0 for name in required):
        raise ValueError("Release is missing a page, archive data, or recording")
    commit = json.loads((folder / "release.json").read_text())["commit"]
    if not re.fullmatch(r"[a-f0-9]{7,40}", commit):
        raise ValueError("Release commit must be a Git SHA")
    return commit


def extract(archive, destination):
    total = 0
    seen = set()
    with tarfile.open(archive, "r|gz") as bundle:
        for member in bundle:
            path = relative(member.name)
            if path.as_posix() == "." and member.isdir():
                continue
            if path.as_posix() in seen:
                raise ValueError("Duplicate archive entry")
            seen.add(path.as_posix())
            target = destination.joinpath(*path.parts)
            if member.isdir():
                target.mkdir(parents=True, exist_ok=True, mode=0o755)
            elif member.isfile():
                total += member.size
                if total > MAX_BYTES:
                    raise ValueError("Release exceeds the 1 GiB unpacked limit")
                target.parent.mkdir(parents=True, exist_ok=True, mode=0o755)
                with bundle.extractfile(member) as source, target.open("xb") as output:
                    shutil.copyfileobj(source, output, 1024 * 1024)
                target.chmod(0o644)
            else:
                raise ValueError("Links and special files are not allowed in releases")
    # mkdtemp starts at 0700; Nginx needs to traverse the final release.
    destination.chmod(0o755)


def target_of(root, name):
    link = root / name
    if not link.is_symlink():
        if link.exists():
            raise ValueError(f"{link} must be a symlink")
        return None
    target = link.resolve(strict=True)
    if target.parent != root / "releases" or not RELEASE_ID.fullmatch(target.name):
        raise ValueError(f"Unexpected {name} target")
    return target


def point(root, name, target):
    temporary = root / f".{name}-next"
    temporary.unlink(missing_ok=True)
    temporary.symlink_to(Path("releases") / target.name)
    os.replace(temporary, root / name)


def prune(root, keep):
    protected = {target_of(root, name) for name in ("current", "previous")}
    releases = sorted((p for p in (root / "releases").iterdir()
                       if p.is_dir() and not p.is_symlink() and RELEASE_ID.fullmatch(p.name)), reverse=True)
    retained = {p for p in protected if p}
    for release in releases:
        if len(retained) < keep:
            retained.add(release)
    for release in releases:
        if release not in retained:
            shutil.rmtree(release)


def install(root, archive, keep, expected_commit=None):
    if shutil.disk_usage(root).free < MAX_BYTES + 256 * 1024 ** 2:
        raise ValueError("Need at least 1.25 GiB free before installing a release")
    current = target_of(root, "current")
    target_of(root, "previous")
    staging = Path(tempfile.mkdtemp(prefix=".incoming-", dir=root / "releases"))
    try:
        extract(archive, staging)
        commit = verify(staging)
        if expected_commit and commit != expected_commit:
            raise ValueError("Release commit does not match the requested deployment")
        stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        release = root / "releases" / f"{stamp}-{commit[:12]}"
        staging.rename(release)
    finally:
        if staging.exists():
            shutil.rmtree(staging)
    if current:
        point(root, "previous", current)
    point(root, "current", release)
    prune(root, keep)
    print(f"Installed {release.name}; keeping {keep} releases. No Nginx restart is needed.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("/srv/n4ml"))
    commands = parser.add_subparsers(dest="command", required=True)
    deploy = commands.add_parser("install")
    deploy.add_argument("archive", type=Path)
    deploy.add_argument("--keep", type=int, choices=range(2, 6), default=3)
    deploy.add_argument("--commit", help="Require this exact Git SHA before activation")
    commands.add_parser("rollback")
    commands.add_parser("status")
    args = parser.parse_args()
    root = args.root.resolve()
    if root in (Path("/"), Path("/srv"), Path("/etc"), Path("/var")):
        raise ValueError("Choose a dedicated site directory")
    (root / "releases").mkdir(parents=True, exist_ok=True, mode=0o755)
    with (root / ".deploy.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if args.command == "install":
            install(root, args.archive, args.keep, args.commit)
        elif args.command == "rollback":
            previous = target_of(root, "previous")
            current = target_of(root, "current")
            if not previous or not current:
                raise ValueError("No previous release is available")
            verify(previous)
            point(root, "current", previous)
            point(root, "previous", current)
            print(f"Restored {previous.name}")
        else:
            for name in ("current", "previous"):
                print(f"{name}: {target_of(root, name) or 'none'}")


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, KeyError, tarfile.TarError) as error:
        print(f"Deployment failed: {error}", file=sys.stderr)
        sys.exit(1)
