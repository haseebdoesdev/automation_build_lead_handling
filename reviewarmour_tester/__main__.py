"""Allow ``python -m reviewarmour_tester`` after installing ``nicegui``."""

from __future__ import annotations

import os
import sys


def main() -> None:
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if root not in sys.path:
        sys.path.insert(0, root)

    import reviewarmour_tester.app  # noqa: F401 — registers NiceGUI page

    from nicegui import ui

    port = int(os.environ.get("REVIEWARMOUR_TESTER_PORT", "8085"))
    ui.run(title="ReviewArmour tester", port=port, reload=False, show=True)


if __name__ == "__main__":
    main()
