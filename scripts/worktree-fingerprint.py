#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import os
from pathlib import Path
import stat
import subprocess
import sys


def git_paths(repository: Path, arguments: list[str]) -> list[bytes]:
    output = subprocess.check_output(
        ["git", "-C", str(repository), *arguments],
    )
    return [path for path in output.split(b"\0") if path]


def fingerprint(repository: Path) -> str:
    repository = repository.resolve(strict=True)
    top_level = Path(
        subprocess.check_output(
            ["git", "-C", str(repository), "rev-parse", "--show-toplevel"],
            text=True,
        ).strip()
    ).resolve(strict=True)
    if repository != top_level:
        raise ValueError(f"repository must be the Git top-level: {repository}")

    tracked = git_paths(repository, ["ls-files", "-z"])
    untracked = git_paths(
        repository,
        [
            "ls-files",
            "--others",
            "--exclude-standard",
            "-z",
        ],
    )
    digest = hashlib.sha256(b"public-document-worktree-v1\0")
    for relative_bytes in sorted(set(tracked + untracked)):
        relative = Path(os.fsdecode(relative_bytes))
        path = repository / relative
        digest.update(relative_bytes)
        digest.update(b"\0")
        try:
            metadata = path.lstat()
        except FileNotFoundError:
            digest.update(b"missing\0")
            continue
        if stat.S_ISLNK(metadata.st_mode):
            digest.update(b"symlink\0")
            digest.update(os.fsencode(os.readlink(path)))
            digest.update(b"\0")
            continue
        if not stat.S_ISREG(metadata.st_mode):
            digest.update(f"mode:{metadata.st_mode:o}\0".encode())
            continue
        digest.update(b"file\0")
        digest.update(f"mode:{stat.S_IMODE(metadata.st_mode):o}\0".encode())
        with path.open("rb") as source:
            while chunk := source.read(1024 * 1024):
                digest.update(chunk)
        digest.update(b"\0")
    return digest.hexdigest()


def main() -> int:
    if len(sys.argv) > 2:
        print("usage: worktree-fingerprint.py [repository]", file=sys.stderr)
        return 2
    repository = Path(sys.argv[1]) if len(sys.argv) == 2 else Path.cwd()
    try:
        print(fingerprint(repository))
    except (OSError, subprocess.CalledProcessError, ValueError) as error:
        print(str(error), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
