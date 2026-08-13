"""Import helper for the external Stage 2 package under scripts/external-stage2.

The package directory name contains a hyphen, so it cannot be imported as a
regular top-level package from the repository root. Tests load modules through
this helper, which puts the scripts directory on ``sys.path`` exactly once.
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path
from types import ModuleType

_SCRIPTS_ROOT = Path(__file__).resolve().parents[2] / "scripts" / "external-stage2"


def load(module_name: str) -> ModuleType:
    scripts_root = str(_SCRIPTS_ROOT)
    if scripts_root not in sys.path:
        sys.path.insert(0, scripts_root)
    return importlib.import_module(module_name)
