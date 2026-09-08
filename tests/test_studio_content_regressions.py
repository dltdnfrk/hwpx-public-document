from __future__ import annotations

import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_studio_content_regressions() -> None:
    completed = subprocess.run(
        ["node", "--test", "tests/studio-content-regressions.mjs"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
