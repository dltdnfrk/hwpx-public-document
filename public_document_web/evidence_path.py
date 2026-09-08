from __future__ import annotations

from pathlib import Path
import sys


def _reject_symlink_ancestors(path: Path) -> None:
    current = path.parent
    while True:
        if current.is_symlink():
            raise ValueError(f"evidence path has symbolic-link ancestor: {current}")
        if current == current.parent:
            break
        current = current.parent


def prepare_output_file(path: Path) -> Path:
    path = path.absolute()
    if path.exists() or path.is_symlink():
        raise ValueError(f"evidence output already exists: {path}")
    _reject_symlink_ancestors(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    _reject_symlink_ancestors(path)
    return path


def create_evidence_directory(path: Path) -> Path:
    path = path.absolute()
    if path.exists() or path.is_symlink():
        raise ValueError(f"evidence directory already exists: {path}")
    _reject_symlink_ancestors(path)
    path.mkdir(parents=True, exist_ok=False)
    _reject_symlink_ancestors(path / "sentinel")
    return path


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: evidence_path.py <new-evidence-directory>", file=sys.stderr)
        return 2
    try:
        print(create_evidence_directory(Path(sys.argv[1])))
    except (OSError, ValueError) as error:
        print(str(error), file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
