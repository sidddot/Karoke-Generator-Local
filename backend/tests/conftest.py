"""Pytest configuration and shared fixtures."""
from __future__ import annotations

import sys
from pathlib import Path

# Make sure `app` is importable when running tests from backend/
sys.path.insert(0, str(Path(__file__).parent.parent))
