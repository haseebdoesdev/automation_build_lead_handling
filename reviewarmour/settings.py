"""Runtime settings (no secrets)."""

from __future__ import annotations

import os

FIRST_TOUCH_VARIATION = os.environ.get("REVIEWARMOUR_FIRST_TOUCH_VARIATION", "A")
