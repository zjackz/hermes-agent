"""Crawl4AI deep crawling provider for Hermes web tools."""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class Crawl4AIProvider:
    """Deep web crawling via Crawl4AI (https://github.com/unclecode/crawl4ai).

    Provides real depth-controlled crawling with JS rendering, unlike the
    Firecrawl wrapper which is limited to 20 pages with no depth control.
    """

    def provider_name(self) -> str:
        return "crawl4ai"

    def is_configured(self) -> bool:
        """Always available — runs locally, no API key needed."""
        try:
            import crawl4ai  # noqa: F401
            return True
        except ImportError:
            return False

    @staticmethod
    def _clean_with_trafilatura(html: str, url: str = "") -> Optional[str]:
        """Extract clean article text from HTML using trafilatura.

        Returns markdown-formatted text, or None if extraction fails.
        """
        try:
            import trafilatura
            result = trafilatura.extract(
                html,
                url=url,
                output_format="markdown",
                include_links=True,
                include_tables=True,
                favor_recall=True,
            )
            return result
        except Exception:
            return None

    async def crawl(
        self,
        url: str,
        *,
        max_depth: int = 3,
        max_pages: int = 100,
        include_patterns: Optional[List[str]] = None,
        exclude_patterns: Optional[List[str]] = None,
        extract_markdown: bool = True,
        use_trafilatura: bool = True,
        headless: bool = True,
        timeout: int = 30000,
    ) -> Dict[str, Any]:
        """Crawl a website with configurable depth and page limits.

        Args:
            url: Starting URL to crawl.
            max_depth: Maximum link-following depth from start URL (1-10).
            max_pages: Maximum total pages to crawl.
            include_patterns: URL patterns to include (glob-style).
            exclude_patterns: URL patterns to exclude (glob-style).
            extract_markdown: Whether to extract markdown content.
            use_trafilatura: Use trafilatura for cleaner article extraction.
            headless: Run browser in headless mode.
            timeout: Page load timeout in ms.

        Returns:
            Normalized result dict with 'success', 'results' list.
        """
        from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig, CacheMode

        browser_cfg = BrowserConfig(headless=headless)

        results: List[Dict[str, Any]] = []

        try:
            async with AsyncWebCrawler(config=browser_cfg) as crawler:
                from crawl4ai.deep_crawling import BFSDeepCrawlStrategy
                from crawl4ai.deep_crawling.filters import FilterChain, URLPatternFilter

                # Build filter chain from include/exclude patterns
                filters = []
                if include_patterns:
                    filters.append(URLPatternFilter(patterns=include_patterns, use_glob=True))
                if exclude_patterns:
                    filters.append(URLPatternFilter(patterns=exclude_patterns, use_glob=True, reverse=True))

                strategy = BFSDeepCrawlStrategy(
                    max_depth=max_depth,
                    max_pages=max_pages,
                    filter_chain=FilterChain(filters=filters) if filters else FilterChain(),
                )

                run_cfg = CrawlerRunConfig(
                    cache_mode=CacheMode.BYPASS,
                    page_timeout=timeout,
                    deep_crawl_strategy=strategy,
                )

                crawl_results = await crawler.arun(url=url, config=run_cfg)

                # Normalize to list
                if not isinstance(crawl_results, list):
                    crawl_results = [crawl_results]

                for r in crawl_results:
                    if r.success:
                        # Try trafilatura for cleaner extraction, fall back to crawl4ai markdown
                        content = ""
                        if use_trafilatura and r.html:
                            cleaned = self._clean_with_trafilatura(r.html, r.url)
                            if cleaned:
                                content = cleaned
                        if not content:
                            content = str(r.markdown) if (extract_markdown and r.markdown) else (r.cleaned_html or "")

                        results.append({
                            "url": r.url,
                            "title": r.metadata.get("title", "") if r.metadata else "",
                            "content": content,
                            "links_found": len(r.links.get("internal", [])) if r.links else 0,
                        })
                    else:
                        results.append({
                            "url": r.url,
                            "title": "",
                            "content": "",
                            "error": r.error_message or "Crawl failed",
                        })

                logger.info(
                    "Crawl4AI completed: %d pages crawled (max_depth=%d, max_pages=%d)",
                    len(results), max_depth, max_pages,
                )

        except Exception as e:
            logger.error("Crawl4AI error: %s", e)
            return {"success": False, "error": str(e), "results": []}

        return {"success": True, "results": results}

    async def extract(
        self,
        urls: List[str],
        *,
        headless: bool = True,
        timeout: int = 30000,
    ) -> Dict[str, Any]:
        """Extract content from specific URLs (single-page, no link following).

        Args:
            urls: List of URLs to extract content from.
            headless: Run browser in headless mode.
            timeout: Page load timeout in ms.

        Returns:
            Normalized result dict.
        """
        from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig, CacheMode

        browser_cfg = BrowserConfig(headless=headless)
        run_cfg = CrawlerRunConfig(
            cache_mode=CacheMode.BYPASS,
            page_timeout=timeout,
        )

        results: List[Dict[str, Any]] = []

        try:
            async with AsyncWebCrawler(config=browser_cfg) as crawler:
                for url in urls:
                    r = await crawler.arun(url=url, config=run_cfg)
                    if r.success:
                        results.append({
                            "url": r.url,
                            "title": r.metadata.get("title", "") if r.metadata else "",
                            "content": str(r.markdown) if r.markdown else "",
                        })
                    else:
                        # Fallback to Scrapling for anti-bot protected sites
                        try:
                            from tools.web_providers.scrapling_provider import scrapling_extract
                            import asyncio
                            sr = await scrapling_extract([url])
                            if sr.get("success") and sr.get("results"):
                                s = sr["results"][0]
                                if s.get("content"):
                                    results.append(s)
                                    logger.info("Scrapling fallback succeeded for %s", url)
                                    continue
                        except Exception:
                            pass
                        results.append({
                            "url": url,
                            "title": "",
                            "content": "",
                            "error": r.error_message or "Extract failed",
                        })
        except Exception as e:
            logger.error("Crawl4AI extract error: %s", e)
            return {"success": False, "error": str(e), "results": []}

        return {"success": True, "results": results}
