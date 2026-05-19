"""Scrapling anti-detection web extraction — fallback for Crawl4AI when sites block.

Scrapling automatically bypasses Cloudflare, WAF, and other anti-bot measures.
It adapts to site structure changes without needing selector updates.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


async def scrapling_extract(urls: List[str], *, timeout: int = 30) -> Dict[str, Any]:
    """Extract content from URLs using Scrapling's anti-detection engine.

    Use when Crawl4AI or Firecrawl fails due to anti-bot protection.

    Args:
        urls: URLs to extract.
        timeout: Request timeout in seconds.

    Returns:
        Normalized result dict.
    """
    from scrapling import Fetcher

    fetcher = Fetcher(auto_match=True)
    results: List[Dict[str, Any]] = []

    for url in urls:
        try:
            page = fetcher.get(url, timeout=timeout)
            # Extract main content
            title = page.css_first("title").text() if page.css_first("title") else ""
            # Try article/main content first, fallback to body
            content_el = (
                page.css_first("article")
                or page.css_first("main")
                or page.css_first("[role='main']")
                or page.css_first("body")
            )
            content = content_el.text(separator="\n", strip=True) if content_el else ""

            results.append({"url": url, "title": title, "content": content})
        except Exception as e:
            logger.warning("Scrapling extract failed for %s: %s", url, e)
            results.append({"url": url, "title": "", "content": "", "error": str(e)})

    return {"success": True, "results": results}


def is_available() -> bool:
    try:
        from scrapling import Fetcher  # noqa: F401
        return True
    except ImportError:
        return False
