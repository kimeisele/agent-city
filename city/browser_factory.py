"""
BROWSER FACTORY — Lazy Browser for City Agents.

Creates an AgentWebBrowser from agent-internet on first use.
Conditional import: agent-city works without agent-internet installed.

The browser is a SENSE, not a requirement. Agents without browsers
still function — they just can't perceive the external web.

    Hare Krishna Hare Krishna Krishna Krishna Hare Hare
    Hare Rama   Hare Rama   Rama   Rama   Hare Hare
"""

from __future__ import annotations

import logging
import re

logger = logging.getLogger("AGENT_CITY.BROWSER_FACTORY")

_browser_instance: object | None = None
_browser_checked: bool = False

# URL pattern for extraction from text
_URL_PATTERN = re.compile(r"https?://[^\s<>\"')\]]+")


def get_browser() -> object | None:
    """Get or create the shared browser instance.

    Returns AgentWebBrowser or None if agent-internet not available.
    Lazy init — only imports on first call.
    """
    global _browser_instance, _browser_checked

    if _browser_checked:
        return _browser_instance

    _browser_checked = True

    try:
        from agent_internet.agent_web_browser import AgentWebBrowser
        from agent_internet.agent_web_browser_github import GitHubBrowserSource

        browser = AgentWebBrowser()
        browser.register_source(GitHubBrowserSource())
        _browser_instance = browser
        logger.info("Browser initialized (GitHub source registered)")
        return _browser_instance

    except ImportError:
        logger.debug("agent-internet not available — browser disabled")
        return None
    except Exception as e:
        logger.warning("Browser init failed: %s", e)
        return None


def extract_urls(text: str) -> list[str]:
    """Extract HTTP(S) URLs from text."""
    return _URL_PATTERN.findall(text)


def browse_url(url: str) -> dict | None:
    """Open a URL and return structured page data.

    Returns dict with: url, title, content_text, links
    Or None if browser unavailable or fetch fails.
    """
    browser = get_browser()
    if browser is None:
        return None

    try:
        page = browser.open(url)
        return {
            "url": page.url,
            "title": page.title,
            "content_text": page.content_text[:1000],  # Cap for MicroBrain context
            "links": [(l.text, l.href) for l in page.links[:10]],
            "status": page.status_code,
        }
    except Exception as e:
        logger.debug("Browse %s failed: %s", url, e)
        return None
