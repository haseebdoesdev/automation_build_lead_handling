"""Run GBP Maps inspection from the command line (Playwright).

Examples::

    python -m reviewarmour.gbp "https://www.google.com/maps/place/..." --headful
    python -m reviewarmour.gbp URL --headless

Defaults to headless; use ``--headful`` to open a visible Chromium window for debugging.
"""

from __future__ import annotations

import argparse
import json
import sys

from reviewarmour.gbp.scraper import run_inspect_gbp_sync


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Inspect a Google Maps place URL (reviews tab sample).")
    p.add_argument("url", help="Maps / g.page URL")
    p.add_argument(
        "--headful",
        action="store_true",
        help="Show Chromium window (not headless). Use this to debug selectors / consent flows.",
    )
    p.add_argument(
        "--max-seconds",
        type=float,
        default=90.0,
        help="Cap scraping time (default 90)",
    )
    p.add_argument(
        "--max-reviews",
        type=int,
        default=24,
        help="Max review rows to collect (default 24)",
    )
    args = p.parse_args(argv)

    out = run_inspect_gbp_sync(
        args.url.strip(),
        headless=not args.headful,
        max_seconds=args.max_seconds,
        max_reviews=args.max_reviews,
    )
    print(json.dumps(out, indent=2, default=str))
    return 0 if out.get("status") == "success" else 1


if __name__ == "__main__":
    sys.exit(main())
