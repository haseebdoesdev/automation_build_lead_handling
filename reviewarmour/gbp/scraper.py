"""
Google Maps / GBP public profile inspection using Patchright.

Uses the same core approach as the production negative-review scraper:
  - patchright (anti-bot bypass)
  - domcontentloaded + smart place-shell wait
  - .jftiEf card selector (current Maps DOM)
  - Tile request blocking for speed
  - Optional saved Google session (auth state)

Collects visible review metadata (stars, relative date, images) to infer
``RecencyProfile`` for :class:`reviewarmour.models.LeadRecord`.

Usage::

    python -m reviewarmour.gbp "https://www.google.com/maps/place/..." --headful

Optional env:
    SCRAPER_DEBUG=1         save screenshot+HTML on failure
    SCRAPER_DEBUG_DIR       default: debug-artifacts
    SCRAPER_BLOCK_TILES=0   disable tile blocking
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
from typing import Any, Dict, List, Optional
from urllib.parse import unquote

from reviewarmour.gbp.inference import (
    guess_category_from_business_name,
    infer_recency_profile,
)
from reviewarmour.models import RecencyProfile

logger = logging.getLogger(__name__)

DEBUG = os.environ.get("SCRAPER_DEBUG", "").lower() in ("1", "true", "yes")
DEBUG_DIR = os.environ.get("SCRAPER_DEBUG_DIR", "debug-artifacts")
BLOCK_TILES = os.environ.get("SCRAPER_BLOCK_TILES", "1").lower() not in ("0", "false", "no")

NAV_TIMEOUT_MS = 90_000
STEP_TIMEOUT_MS = 30_000
PAUSE_AFTER_NAV_MS = 2_000
PAUSE_AFTER_TAB_MS = 3_000
PAUSE_AFTER_SORT_MS = 2_500
MAX_SCROLL_ROUNDS = 30
SCROLL_STEP_PX = 1200
SCROLL_PAUSE_MS = 1000

_BLOCKED_URL_SUBSTRINGS = (
    "/maps/vt",
    "/vt/pb",
    "khms",
    "mts.googleapis.com",
    "mts0.googleapis.com",
    "mts1.googleapis.com",
    "streetviewpixels-pa.googleapis.com",
    "streetviewpixels.googleapis.com",
)


def _require_patchright() -> None:
    try:
        from patchright.async_api import async_playwright  # noqa: F401
    except ImportError as e:
        raise RuntimeError(
            "Patchright is required for GBP inspection. "
            "Install: pip install patchright && patchright install chromium"
        ) from e


def _context_options(storage_state: Optional[str] = None) -> dict:
    opts: dict = {
        "user_agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36"
        ),
        "locale": "en-US",
        "viewport": {"width": 1280, "height": 900},
    }
    if storage_state and os.path.exists(storage_state):
        opts["storage_state"] = storage_state
    return opts


async def _abort_map_tiles_route(route: Any) -> None:
    if any(marker in route.request.url for marker in _BLOCKED_URL_SUBSTRINGS):
        await route.abort()
    else:
        await route.continue_()


async def _dismiss_overlays(page: Any) -> None:
    for label in ("Accept all", "Reject all", "I agree"):
        btn = page.get_by_role("button", name=re.compile(label, re.I))
        if await btn.count() > 0:
            try:
                await btn.first.click(timeout=2000)
                await page.wait_for_timeout(400)
            except Exception:
                pass


async def _wait_for_place_shell(page: Any) -> None:
    """Wait for place panel to load — title fallback + collapsed panel expansion."""
    h1 = page.locator("h1.DUwDvf, h1").first
    try:
        await h1.wait_for(state="visible", timeout=STEP_TIMEOUT_MS)
        return
    except Exception:
        pass

    # Fallback 1: poll page title (e.g. "Joe's Pizza - Google Maps")
    for _ in range(20):
        title = (await page.title()) or ""
        if "google maps" in title.lower() and title.strip().lower() != "google maps":
            return
        await page.wait_for_timeout(500)

    # Fallback 2: h1 exists but is hidden (collapsed side panel) — try to expand it
    if await h1.count() > 0:
        expand_selectors = [
            ".lMbq3e",           # Place card in collapsed state
            ".Nv2PK",            # Search result card
            "a.hfpxzc",          # Result link
            '[role="article"]',  # Article card
        ]
        for sel in expand_selectors:
            loc = page.locator(sel)
            if await loc.count() > 0:
                try:
                    await loc.first.click(timeout=5000)
                    await page.wait_for_timeout(2500)
                    if await h1.is_visible():
                        return
                except Exception:
                    pass

    # Fallback 3: just proceed (attached is enough — reviews tab may still work)
    if await h1.count() > 0:
        return  # h1 attached, proceed and let tab click reveal content

    raise RuntimeError("Place shell not loaded — h1 never appeared")


async def _open_reviews_tab(page: Any) -> None:
    candidates = [
        page.get_by_role("tab", name=re.compile(r"^reviews$", re.I)),
        page.locator('button[role="tab"][aria-label*="Reviews"]'),
        page.locator('button:has-text("Reviews")'),
        page.get_by_role("button", name=re.compile(r"reviews", re.I)),
    ]
    for loc in candidates:
        if await loc.count() == 0:
            continue
        try:
            await loc.first.click(timeout=15_000)
            await page.wait_for_timeout(PAUSE_AFTER_TAB_MS)
            return
        except Exception:
            continue
    raise RuntimeError("could not open Reviews tab")


async def _wait_for_reviews_panel(page: Any) -> None:
    heading = page.locator('[aria-label^="Reviews for"]').first
    cards = page.locator(".jftiEf").first
    for _ in range(60):
        if await heading.count() > 0 and await heading.is_visible():
            return
        if await cards.count() > 0 and await cards.is_visible():
            return
        await page.wait_for_timeout(500)
    await heading.wait_for(state="visible", timeout=15_000)


async def _open_sort_newest(page: Any) -> None:
    """Open sort menu and select Newest."""
    sort_btn_candidates = [
        page.locator('[aria-label="Sort reviews"]').first,
        page.locator('button[aria-label="Most relevant"]').first,
        page.get_by_role("button", name=re.compile(r"most relevant", re.I)).first,
        page.locator('button:has-text("Most relevant")').first,
    ]
    for btn in sort_btn_candidates:
        if await btn.count() == 0:
            continue
        try:
            await btn.wait_for(state="visible", timeout=10_000)
            await btn.click(timeout=15_000)
            await page.wait_for_timeout(600)
            break
        except Exception:
            continue

    menu = page.locator('[role="menu"]').first
    try:
        await menu.wait_for(state="visible", timeout=STEP_TIMEOUT_MS)
    except Exception:
        return  # sort unavailable — proceed with default order

    newest_candidates = [
        page.locator('[role="menu"] [data-index="1"]').filter(
            has_text=re.compile(r"newest", re.I)
        ).first,
        page.locator('[data-index="1"]').filter(has_text=re.compile(r"newest", re.I)).first,
        page.get_by_role("menuitem", name=re.compile(r"newest", re.I)).first,
    ]
    for newest in newest_candidates:
        if await newest.count() > 0:
            try:
                await newest.wait_for(state="visible", timeout=STEP_TIMEOUT_MS)
                await newest.click()
                await page.wait_for_timeout(PAUSE_AFTER_SORT_MS)
                return
            except Exception:
                continue


async def _extract_business_data(page: Any) -> Dict[str, Any]:
    data: Dict[str, Any] = {
        "business_name_extracted": None,
        "address": None,
        "website": None,
        "phone": None,
    }
    try:
        name_el = page.locator("h1.DUwDvf, h1").first
        if await name_el.count() > 0:
            name = await name_el.text_content()
            data["business_name_extracted"] = name.strip() if name else None
    except Exception:
        pass

    try:
        addr_el = page.locator('[data-item-id="address"]').first
        if await addr_el.count() > 0:
            addr = await addr_el.text_content()
            data["address"] = addr.strip() if addr else None
    except Exception:
        pass

    try:
        web_el = page.locator('[aria-label="Open website"]').first
        if await web_el.count() > 0:
            data["website"] = await web_el.get_attribute("href")
    except Exception:
        pass

    try:
        phone_el = page.locator('[data-item-id*="phone:tel:"]').first
        if await phone_el.count() > 0:
            pid = await phone_el.get_attribute("data-item-id")
            if pid and "phone:tel:" in pid:
                data["phone"] = pid.split("phone:tel:")[-1]
    except Exception:
        pass

    return data


async def _parse_review_card(card: Any) -> Dict[str, Any]:
    """Extract stars, age, image flag from a .jftiEf card."""
    stars = None
    star_els = card.locator('[aria-label*=" star"]')
    for j in range(await star_els.count()):
        aria = await star_els.nth(j).get_attribute("aria-label") or ""
        m = re.search(r"(\d)\s*stars?", aria, re.I)
        if m:
            stars = int(m.group(1))
            break
    if stars is None:
        aria = await card.get_attribute("aria-label") or ""
        m = re.search(r"(\d)\s*stars?", aria, re.I)
        if m:
            stars = int(m.group(1))

    age_text = ""
    for age_sel in (".rsqaWe", ".DU9Pgb", "span[class*='rsqa']"):
        age_el = card.locator(age_sel).first
        if await age_el.count() > 0:
            t = await age_el.inner_text()
            if t and t.strip():
                age_text = t.strip()
                break
    if not age_text:
        blob = (await card.inner_text()) or ""
        m = re.search(
            r"(Edited\s+)?\d+\s+(day|week|month|year)s?\s+ago|"
            r"(Edited\s+)?(a|one)\s+(day|week|month|year)\s+ago|"
            r"(Edited\s+)?(a|one)\s+month\b|last\s+month",
            blob,
            re.I,
        )
        if m:
            age_text = m.group(0).strip()

    has_img = await card.locator("[data-photo-index]").count() > 0

    return {
        "stars": stars,
        "published_at": age_text or None,
        "has_images": has_img,
    }


async def _scrape_reviews(page: Any, max_reviews: int) -> List[Dict[str, Any]]:
    """Scroll and collect review cards, stop at max_reviews."""
    card_selectors = [
        ".m6QErb.DxyBCb.kA9KIf.dS8AEf.XiKgde .jftiEf",
        "motion-reviews-response .jftiEf",
        ".jftiEf",
    ]
    cards = None
    for sel in card_selectors:
        loc = page.locator(sel)
        if await loc.count() > 0:
            cards = loc
            break
    if cards is None:
        return []

    scroll_container = page.locator(".m6QErb.DxyBCb.kA9KIf.dS8AEf.XiKgde").first
    has_container = await scroll_container.count() > 0

    reviews_out: List[Dict[str, Any]] = []
    processed = 0

    for _ in range(MAX_SCROLL_ROUNDS):
        total = await cards.count()
        for i in range(processed, total):
            card = await _parse_review_card(cards.nth(i))
            reviews_out.append(card)
            if len(reviews_out) >= max_reviews:
                break
        processed = total

        if len(reviews_out) >= max_reviews:
            break

        if has_container:
            await scroll_container.evaluate(f"el => el.scrollTop += {SCROLL_STEP_PX}")
        else:
            await page.evaluate(f"window.scrollBy(0, {SCROLL_STEP_PX})")
        await page.wait_for_timeout(SCROLL_PAUSE_MS)

        if await cards.count() == total:
            break  # no new cards loaded

    return reviews_out


async def inspect_maps_place(
    url: str,
    *,
    max_seconds: float = 90.0,
    headless: bool = True,
    max_reviews: int = 24,
    storage_state: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Open a Google Maps place URL, read the Reviews tab (sorted newest first),
    and return structured data for the AI layer.

    Returns a dict with ``status``, ``reviews``, ``inferred_recency_profile``, etc.
    Uses Patchright for anti-bot bypass.
    """
    _require_patchright()
    from patchright.async_api import async_playwright

    result: Dict[str, Any] = {
        "status": "pending",
        "url": url,
        "error": None,
        "business_name_extracted": None,
        "address": None,
        "website": None,
        "phone": None,
        "reviews": [],
        "review_count_inferred": None,
        "total_reviews_text": None,
        "inferred_recency_profile": RecencyProfile.UNCERTAIN.value,
        "any_review_has_images": False,
        "category_hints": [],
    }

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=headless,
            args=["--no-sandbox", "--disable-dev-shm-usage"],
        )
        context = await browser.new_context(**_context_options(storage_state))
        if BLOCK_TILES:
            await context.route("**/*", _abort_map_tiles_route)
        page = await context.new_page()

        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=NAV_TIMEOUT_MS)
            await page.wait_for_timeout(PAUSE_AFTER_NAV_MS)

            # Block/captcha check
            page_url = page.url.lower()
            if "google.com/sorry" in page_url or "consent.google" in page_url:
                raise RuntimeError(f"Google blocked/consent page: {page.url[:120]}")

            await _dismiss_overlays(page)
            await _wait_for_place_shell(page)

            biz = await _extract_business_data(page)
            result.update(biz)

            await _open_reviews_tab(page)
            await _wait_for_reviews_panel(page)

            # Try to read total review count from header
            try:
                hdr = await page.locator("span:has-text('reviews')").first.text_content(timeout=3000)
                if hdr:
                    m = re.search(r"([\d,]+)\s*reviews", hdr, re.I)
                    if m:
                        result["total_reviews_text"] = hdr.strip()
                        result["review_count_inferred"] = int(m.group(1).replace(",", ""))
            except Exception:
                pass

            await _open_sort_newest(page)

            reviews_out = await _scrape_reviews(page, max_reviews)
            result["reviews"] = reviews_out

            if result["review_count_inferred"] is None:
                result["review_count_inferred"] = len(reviews_out) or None

            # Infer RecencyProfile from dates
            dates = [r.get("published_at") for r in reviews_out]
            rp = infer_recency_profile(dates)
            result["inferred_recency_profile"] = rp.value

            # Check for image reviews
            result["any_review_has_images"] = any(r.get("has_images") for r in reviews_out)

            # Category hints from business name
            nm = result.get("business_name_extracted") or ""
            gh = guess_category_from_business_name(nm)
            result["category_hints"] = [gh] if gh else []

            result["status"] = "success"

        except Exception as e:
            result["status"] = "error"
            result["error"] = str(e)
            logger.error("GBP inspect failed for %s: %s", url[:80], e)
            if DEBUG:
                try:
                    os.makedirs(DEBUG_DIR, exist_ok=True)
                    await page.screenshot(path=os.path.join(DEBUG_DIR, "gbp_error.png"))
                    html = await page.content()
                    with open(os.path.join(DEBUG_DIR, "gbp_error.html"), "w", encoding="utf-8") as f:
                        f.write(html[:500_000])
                except Exception:
                    pass
        finally:
            await context.close()
            await browser.close()

    return result


def run_inspect_gbp_sync(
    url: str,
    *,
    max_seconds: float = 90.0,
    headless: bool = True,
    max_reviews: int = 24,
    storage_state: Optional[str] = None,
) -> Dict[str, Any]:
    """Blocking wrapper for workers / CLI."""
    return asyncio.run(
        inspect_maps_place(
            url,
            max_seconds=max_seconds,
            headless=headless,
            max_reviews=max_reviews,
            storage_state=storage_state,
        )
    )
