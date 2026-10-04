#!/usr/bin/env python3
"""Kit-side entry for the design-token tells check (fonts, neutrals, accent, easing).

The ONE implementation is template/scripts/check_design.py, which ships inside every
generated repo (its `npm run gates` runs it against design/tokens.json). This file loads
that module and re-exports it, so render.py, prototype.py and the kit selftest check
tokens with exactly the code the generated repo runs: there is no second copy to drift.

Usage: check_design.py design/tokens.json      exit 0 pass, 1 fail, 2 usage
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_IMPL = Path(__file__).resolve().parent.parent / "template" / "scripts" / "check_design.py"
_spec = importlib.util.spec_from_file_location("check_design_impl", _IMPL)
if _spec is None or _spec.loader is None:
    raise ImportError(f"design check implementation not found at {_IMPL}")
_impl = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_impl)
globals().update({k: v for k, v in vars(_impl).items() if not k.startswith("__")})

if __name__ == "__main__":
    sys.exit(_impl.main())
