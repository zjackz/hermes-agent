"""Playwright persistent connection manager for Hermes browser tools.

Replaces the agent-browser CLI subprocess model with direct Playwright API calls.
Each task_id gets a persistent browser context that is reused across commands,
eliminating the ~100-500ms subprocess overhead per operation.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Session inactivity timeout (seconds) — matches browser_tool.py default
_SESSION_TIMEOUT = 300


class PlaywrightSession:
    """A persistent browser session tied to a task_id."""

    __slots__ = ("task_id", "context", "page", "last_used", "_console_logs", "_errors")

    def __init__(self, task_id: str, context, page):
        self.task_id = task_id
        self.context = context
        self.page = page
        self.last_used = time.time()
        self._console_logs: List[str] = []
        self._errors: List[str] = []

        # Wire up console/error listeners
        page.on("console", lambda msg: self._console_logs.append(
            f"[{msg.type}] {msg.text}"
        ))
        page.on("pageerror", lambda err: self._errors.append(str(err)))

    def touch(self):
        self.last_used = time.time()

    @property
    def is_expired(self) -> bool:
        return (time.time() - self.last_used) > _SESSION_TIMEOUT

    def drain_console(self) -> List[str]:
        logs = self._console_logs[:]
        self._console_logs.clear()
        return logs

    def drain_errors(self) -> List[str]:
        errs = self._errors[:]
        self._errors.clear()
        return errs


class PlaywrightManager:
    """Manages Playwright browser instances and sessions.

    Usage:
        mgr = PlaywrightManager()
        await mgr.start()
        result = await mgr.execute(task_id, "open", ["https://example.com"])
        await mgr.stop()
    """

    def __init__(self, headless: bool = True):
        self._headless = headless
        self._playwright = None
        self._browser = None
        self._sessions: Dict[str, PlaywrightSession] = {}
        self._lock = asyncio.Lock()
        self._started = False

    async def start(self):
        """Launch the browser (lazy — called on first command if needed)."""
        if self._started:
            return
        from playwright.async_api import async_playwright
        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(
            headless=self._headless,
            args=["--no-sandbox", "--disable-dev-shm-usage"],
        )
        self._started = True
        logger.info("PlaywrightManager: browser launched (headless=%s)", self._headless)

    async def stop(self):
        """Close all sessions and the browser."""
        for session in list(self._sessions.values()):
            await self._close_session(session)
        self._sessions.clear()
        if self._browser:
            await self._browser.close()
            self._browser = None
        if self._playwright:
            await self._playwright.stop()
            self._playwright = None
        self._started = False

    async def _get_session(self, task_id: str) -> PlaywrightSession:
        """Get or create a session for the given task_id."""
        async with self._lock:
            if not self._started:
                await self.start()

            if task_id in self._sessions:
                session = self._sessions[task_id]
                if not session.is_expired:
                    session.touch()
                    return session
                # Expired — close and recreate
                await self._close_session(session)

            context = await self._browser.new_context(
                viewport={"width": 1280, "height": 720},
                user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            )
            page = await context.new_page()
            session = PlaywrightSession(task_id, context, page)
            self._sessions[task_id] = session
            return session

    async def _close_session(self, session: PlaywrightSession):
        """Close a session's context."""
        try:
            await session.context.close()
        except Exception as e:
            logger.debug("Error closing session %s: %s", session.task_id, e)

    async def close_session(self, task_id: str):
        """Explicitly close a task's session."""
        async with self._lock:
            session = self._sessions.pop(task_id, None)
            if session:
                await self._close_session(session)

    async def execute(self, task_id: str, command: str, args: List[str] = None) -> Dict[str, Any]:
        """Execute a browser command, returning the same JSON format as agent-browser CLI.

        Args:
            task_id: Task identifier.
            command: One of: open, snapshot, click, fill, scroll, back, press, eval, console, errors, close.
            args: Command arguments.

        Returns:
            Dict with 'success' bool and 'data' or 'error'.
        """
        args = args or []

        try:
            if command == "close":
                await self.close_session(task_id)
                return {"success": True}

            session = await self._get_session(task_id)
            page = session.page

            if command == "open":
                url = args[0] if args else "about:blank"
                await page.goto(url, wait_until="domcontentloaded", timeout=60000)
                return {"success": True, "data": {"url": page.url, "title": await page.title()}}

            elif command == "snapshot":
                # Return page content as structured text
                title = await page.title()
                url = page.url
                # Use aria_snapshot for accessibility tree (Playwright 1.49+)
                try:
                    tree_text = await page.locator("body").aria_snapshot()
                except Exception:
                    # Fallback: get visible text content
                    tree_text = await page.inner_text("body")
                return {"success": True, "data": {"snapshot": tree_text, "title": title, "url": url}}

            elif command == "click":
                ref = args[0] if args else ""
                # Try aria snapshot ref format or CSS selector
                locator = self._resolve_ref(page, ref)
                await locator.click(timeout=10000)
                await page.wait_for_load_state("domcontentloaded", timeout=5000)
                return {"success": True}

            elif command == "fill":
                ref = args[0] if len(args) > 0 else ""
                text = args[1] if len(args) > 1 else ""
                locator = self._resolve_ref(page, ref)
                await locator.fill(text, timeout=10000)
                return {"success": True}

            elif command == "scroll":
                direction = args[0] if args else "down"
                pixels = int(args[1]) if len(args) > 1 else 500
                delta = pixels if direction == "down" else -pixels
                await page.mouse.wheel(0, delta)
                await asyncio.sleep(0.3)
                return {"success": True}

            elif command == "back":
                await page.go_back(wait_until="domcontentloaded", timeout=30000)
                return {"success": True}

            elif command == "press":
                key = args[0] if args else "Enter"
                await page.keyboard.press(key)
                return {"success": True}

            elif command == "eval":
                expression = args[0] if args else ""
                result = await page.evaluate(expression)
                return {"success": True, "data": {"result": result}}

            elif command == "console":
                return {"success": True, "data": {"logs": session.drain_console()}}

            elif command == "errors":
                return {"success": True, "data": {"errors": session.drain_errors()}}

            elif command == "record":
                # Recording not supported in direct Playwright mode
                return {"success": False, "error": "Recording not supported in Playwright direct mode"}

            # ── Advanced capabilities (Playwright-only) ──

            elif command == "new_tab":
                # Open a new tab, optionally navigate to URL
                url = args[0] if args else "about:blank"
                new_page = await session.context.new_page()
                if url != "about:blank":
                    await new_page.goto(url, wait_until="domcontentloaded", timeout=60000)
                session.page = new_page  # Switch active page
                return {"success": True, "data": {"url": new_page.url, "title": await new_page.title()}}

            elif command == "switch_tab":
                # Switch to tab by index
                idx = int(args[0]) if args else 0
                pages = session.context.pages
                if 0 <= idx < len(pages):
                    session.page = pages[idx]
                    return {"success": True, "data": {"url": session.page.url, "tab_count": len(pages)}}
                return {"success": False, "error": f"Tab index {idx} out of range (0-{len(pages)-1})"}

            elif command == "list_tabs":
                pages = session.context.pages
                tabs = [{"index": i, "url": p.url, "title": await p.title()} for i, p in enumerate(pages)]
                return {"success": True, "data": {"tabs": tabs, "active": pages.index(session.page)}}

            elif command == "get_cookies":
                cookies = await session.context.cookies()
                return {"success": True, "data": {"cookies": cookies}}

            elif command == "set_cookie":
                # args: [name, value, domain, path]
                cookie = {
                    "name": args[0] if len(args) > 0 else "",
                    "value": args[1] if len(args) > 1 else "",
                    "domain": args[2] if len(args) > 2 else "",
                    "path": args[3] if len(args) > 3 else "/",
                }
                await session.context.add_cookies([cookie])
                return {"success": True}

            elif command == "clear_cookies":
                await session.context.clear_cookies()
                return {"success": True}

            elif command == "intercept":
                # Network interception: block or modify requests
                # args: [action, pattern]  action=block|log
                action = args[0] if args else "log"
                pattern = args[1] if len(args) > 1 else "**/*"
                if action == "block":
                    await page.route(pattern, lambda route: route.abort())
                    return {"success": True, "data": {"action": "block", "pattern": pattern}}
                elif action == "log":
                    # Just return current network requests (last 50)
                    return {"success": True, "data": {"note": "Use eval with performance.getEntries() for network log"}}
                return {"success": False, "error": f"Unknown intercept action: {action}"}

            elif command == "wait":
                # Wait for selector or timeout
                selector = args[0] if args else ""
                wait_timeout = int(args[1]) if len(args) > 1 else 10000
                await page.wait_for_selector(selector, timeout=wait_timeout)
                return {"success": True}

            else:
                return {"success": False, "error": f"Unknown command: {command}"}

        except Exception as e:
            logger.warning("Playwright command '%s' failed: %s", command, e)
            return {"success": False, "error": str(e)}

    def _resolve_ref(self, page, ref: str):
        """Resolve an element reference to a Playwright locator.

        Supports:
        - @ref format from aria snapshots (e.g., "@button[Submit]")
        - CSS selectors as fallback
        - Role-based selectors (e.g., "role=button[name='Submit']")
        """
        if ref.startswith("@"):
            # aria snapshot ref — extract role and name
            # Format: @role[name] or just @name
            inner = ref[1:]
            if "[" in inner:
                role = inner.split("[")[0]
                name = inner.split("[")[1].rstrip("]")
                return page.get_by_role(role, name=name)
            else:
                return page.get_by_text(inner)
        elif ref.startswith("role="):
            # Playwright role selector
            return page.locator(ref)
        else:
            # CSS selector or text
            return page.locator(ref)

    def _format_ax_tree(self, node: dict, indent: int = 0) -> str:
        """Format accessibility tree as indented text."""
        if not node:
            return ""
        lines = []
        role = node.get("role", "")
        name = node.get("name", "")
        value = node.get("value", "")

        parts = []
        if role:
            parts.append(role)
        if name:
            parts.append(f'"{name}"')
        if value:
            parts.append(f'value="{value}"')

        if parts:
            lines.append("  " * indent + " ".join(parts))

        for child in node.get("children", []):
            lines.append(self._format_ax_tree(child, indent + 1))

        return "\n".join(lines)


# ─── Singleton instance ───────────────────────────────────────────────────────

_manager: Optional[PlaywrightManager] = None


async def get_playwright_manager() -> PlaywrightManager:
    """Get or create the global PlaywrightManager singleton."""
    global _manager
    if _manager is None:
        _manager = PlaywrightManager(headless=True)
    if not _manager._started:
        await _manager.start()
    return _manager


async def playwright_execute(task_id: str, command: str, args: List[str] = None) -> Dict[str, Any]:
    """Convenience function: execute a browser command via Playwright.

    Drop-in replacement for _run_browser_command() return format.
    """
    mgr = await get_playwright_manager()
    return await mgr.execute(task_id, command, args)
