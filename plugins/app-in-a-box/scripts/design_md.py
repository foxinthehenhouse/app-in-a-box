#!/usr/bin/env python3
"""Kit-side entry for DESIGN.md generation and its drift check.

The ONE implementation is template/scripts/design_md.py, which ships inside every
generated repo (its CI and pre-commit run `python3 scripts/design_md.py --check`). This
file loads that module and re-exports it, so prototype.py freeze and render.py write
DESIGN.md with exactly the code the generated repo checks it with: no second copy.

Usage: design_md.py [--tokens design/tokens.json] [--out DESIGN.md] [--check]
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_IMPL = Path(__file__).resolve().parent.parent / "template" / "scripts" / "design_md.py"
_spec = importlib.util.spec_from_file_location("design_md_impl", _IMPL)
if _spec is None or _spec.loader is None:
    raise ImportError(f"DESIGN.md implementation not found at {_IMPL}")
_impl = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_impl)
globals().update({k: v for k, v in vars(_impl).items() if not k.startswith("__")})

if __name__ == "__main__":
    sys.exit(_impl.main())
