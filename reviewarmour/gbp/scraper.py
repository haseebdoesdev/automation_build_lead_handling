"""
Google Maps / GBP public profile inspection using Playwright.

Adapted from a standalone scraper; collects visible review metadata (dates,
stars, images) to infer ``RecencyProfile`` for :class:`reviewarmour.models.LeadRecord`.

Requires optional dependency: ``pip install playwright`` then ``playwright install chromium``.
"""

from __future__ import annotations

import asyncio
import re
from typing import Any, Dict, List, Optional
from urllib.parse import unquote

from reviewarmour.gbp.inference import (
    guess_category_from_business_name,
    infer_recency_profile,
)
from reviewarmour.models import RecencyProfile


def _require_playwright():
    try:
        from playwright.async_api import async_playwright  # noqa: F401
    except ImportError as e:
        raise RuntimeError(
            "Playwright is required for GBP inspection. Install: pip install playwright "
            "&& playwright install chromium"
        ) from e


def generate_review_link(address_url: str, review_id: str) -> str:
    """Build a review permalink from the current Maps URL and review id."""
    address_url = unquote(address_url)
    lat_lng_zoom_match = re.search(r"@(-?\d+\.\d+),(-?\d+\.\d+),(\d+)z", address_url)
    if not lat_lng_zoom_match:
        raise ValueError("Could not extract lat/lng/zoom from address URL")
    lat, lng, zoom = lat_lng_zoom_match.groups()
    cid_match = re.search(r"0x[a-fA-F0-9]+:0x[a-fA-F0-9]+", address_url)
    if not cid_match:
        raise ValueError("Could not extract CID from address URL")
    cid = cid_match.group(0)
    return (
        f"https://www.google.com/maps/reviews/@{lat},{lng},{zoom}z/data="
        f"!4m6!14m5!1m4!2m3!1s{review_id}!2m1!1s{cid}"
    )


async def extract_business_data(page: Any, attempt: int = 1) -> Dict[str, Any]:
    data: Dict[str, Any] = {
        "business_name_extracted": None,
        "address": None,
        "booking_link": None,
        "website": None,
        "phone": None,
    }
    try:
        try:
            await page.wait_for_selector('[data-item-id="address"]', timeout=10000, state="visible")
        except Exception:
            if attempt == 1:
                articles = await page.locator('[role="article"]').all()
                if articles:
                    await articles[0].click()
                    await page.wait_for_timeout(1500)
                    return await extract_business_data(page, attempt=2)
            raise

        try:
            name_elem = await page.locator(".DUwDvf.lfPIob").first.text_content()
            data["business_name_extracted"] = name_elem.strip() if name_elem else None
        except Exception:
            pass

        try:
            address_elem = await page.locator('[data-item-id="address"]').first.text_content()
            data["address"] = address_elem.strip() if address_elem else None
        except Exception:
            pass

        try:
            website_count = await page.locator('[aria-label="Open website"]').count()
            if website_count > 0:
                data["website"] = await page.locator('[aria-label="Open website"]').first.get_attribute(
                    "href"
                )
        except Exception:
            pass

        try:
            phone_count = await page.locator('[data-item-id*="phone:tel:"]').count()
            if phone_count > 0:
                pid = await page.locator('[data-item-id*="phone:tel:"]').first.get_attribute(
                    "data-item-id"
                )
                if pid and "phone:tel:" in pid:
                    data["phone"] = pid.split("phone:tel:")[-1]
        except Exception:
            pass
    except Exception:
        pass
    return data


async def _click_reviews_tab(page: Any) -> None:
    try:
        tab = page.locator("button[role='tab']:has-text('Review')")
        await tab.wait_for(state="visible", timeout=15000)
        await tab.click()
    except Exception:
        alt = page.locator('button[class="C9cOMe"]')
        if await alt.count() > 0:
            await alt.first.click()
            await page.wait_for_timeout(1500)
            tab = page.locator("button[role='tab']:has-text('Review')")
            await tab.wait_for(state="visible", timeout=15000)
            await tab.click()


async def _sort_newest_first(page: Any) -> None:
    try:
        await page.locator('[data-value="Sort"]').wait_for(state="visible", timeout=10000)
        await page.locator('[data-value="Sort"]').click()
        await page.wait_for_timeout(400)
        # Prefer "Newest" label if present
        newest = page.get_by_role("menu").get_by_text("Newest", exact=True)
        if await newest.count() > 0:
            await newest.first.click()
            await page.wait_for_timeout(600)
            return
        # Fallback: first menu item (often Most relevant) — still usable
        opt = page.locator('[role="menu"] [role="menuitem"]').first
        if await opt.count() > 0:
            await opt.click()
            await page.wait_for_timeout(600)
    except Exception:
        pass


async def inspect_maps_place(
    url: str,
    *,
    max_seconds: float = 90.0,
    headless: bool = True,
    max_reviews: int = 24,
) -> Dict[str, Any]:
    """
    Open a Google Maps place URL (including ``g.page`` redirects), read the Reviews tab,
    sample visible reviews, and infer recency / flags for the AI layer.

    Returns a dict with ``status``, ``reviews``, ``inferred_recency_profile``, etc.
    """
    _require_playwright()
    from playwright.async_api import async_playwright

    result: Dict[str, Any] = {
        "status": "pending",
        "url": url,
        "error": None,
        "business_name_extracted": None,
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
            args=["--disable-blink-features=AutomationControlled", "--no-sandbox"],
        )
        context = await browser.new_context(viewport={"width": 1280, "height": 900})
        page = await context.new_page()
        t0 = asyncio.get_event_loop().time()
        try:
            await page.goto(url, wait_until="load", timeout=45000)

            biz = await extract_business_data(page)
            result.update(biz)
            await _click_reviews_tab(page)

            await page.locator(".m6QErb.XiKgde > [data-review-id]").first.wait_for(
                state="visible", timeout=15000
            )
            await _sort_newest_first(page)

            try:
                hdr = await page.locator("span:has-text('reviews')").first.text_content(timeout=3000)
                if hdr:
                    m = re.search(r"([\d,]+)\s*reviews", hdr, re.I)
                    if m:
                        result["total_reviews_text"] = hdr.strip()
                        result["review_count_inferred"] = int(m.group(1).replace(",", ""))
            except Exception:
                pass

            scroll = page.locator(
                '.m6QErb.DxyBCb.kA9KIf.dS8AEf.XiKgde[jslog*="mutable:true"]'
            )
            if await scroll.count() == 0:
                scroll = page.locator(".m6QErb.XiKgde")

            processed: set[str] = set()
            reviews_out: List[Dict[str, Any]] = []

            while asyncio.get_event_loop().time() - t0 < max_seconds and len(reviews_out) < max_reviews:
                items = await page.locator(".m6QErb.XiKgde > [data-review-id]").all()
                for rv in items:
                    rid = await rv.get_attribute("data-review-id")
                    if not rid or rid in processed:
                        continue
                    processed.add(rid)

                    stars = None
                    for n in (5, 4, 3, 2, 1):
                        if await rv.locator(f'[aria-label="{n} star"], [aria-label="{n} stars"]').count() > 0:
                            stars = n
                            break

                    pub = None
                    try:
                        t = await rv.locator(".rsqaWe").first.text_content(timeout=1500)
                        pub = t.strip() if t else None
                    except Exception:
                        pass

                    has_img = await rv.locator("[data-photo-index]").count() > 0
                    if has_img:
                        result["any_review_has_images"] = True

                    reviews_out.append(
                        {
                            "review_id": rid,
                            "stars": stars,
                            "published_at": pub,
                            "has_images": has_img,
                        }
                    )
                    if len(reviews_out) >= max_reviews:
                        break

                if len(reviews_out) >= max_reviews:
                    break

                try:
                    prev_h = await scroll.evaluate("el => el.scrollHeight")
                    await scroll.evaluate("el => el.scrollTop = el.scrollHeight")
                    await page.wait_for_timeout(800)
                    new_h = await scroll.evaluate("el => el.scrollHeight")
                    if new_h == prev_h:
                        break
                except Exception:
                    break

            result["reviews"] = reviews_out
            if result["review_count_inferred"] is None:
                result["review_count_inferred"] = len(reviews_out) or None

            dates = [r.get("published_at") for r in reviews_out]
            rp = infer_recency_profile(dates)
            result["inferred_recency_profile"] = rp.value

            nm = result.get("business_name_extracted") or ""
            gh = guess_category_from_business_name(nm)
            result["category_hints"] = [gh] if gh else []

            result["status"] = "success"

        except Exception as e:
            result["status"] = "error"
            result["error"] = str(e)
        finally:
            await browser.close()

    return result


def run_inspect_gbp_sync(
    url: str,
    *,
    max_seconds: float = 90.0,
    headless: bool = True,
    max_reviews: int = 24,
) -> Dict[str, Any]:
    """Blocking wrapper for workers / Flask / tester."""
    return asyncio.run(
        inspect_maps_place(url, max_seconds=max_seconds, headless=headless, max_reviews=max_reviews)
    )
