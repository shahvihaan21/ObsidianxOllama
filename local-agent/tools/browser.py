"""Browser control: open URLs, search the web, manage tabs.

Tab management uses Ctrl+T / Ctrl+W keystrokes because there is no reliable,
dependency-free way to drive an arbitrary running browser. Those keystrokes are
only sent after the target window is focused, so they cannot leak into whatever
the user happens to be typing in.
"""

from __future__ import annotations

import logging
import time
import urllib.parse

from tools.registry import Level, Tool, ToolError

log = logging.getLogger(__name__)

# Search engines keyed by friendly name. Values are URL templates.
SEARCH_ENGINES = {
    "google": "https://www.google.com/search?q={q}",
    "duckduckgo": "https://duckduckgo.com/?q={q}",
    "bing": "https://www.bing.com/search?q={q}",
    "youtube": "https://www.youtube.com/results?search_query={q}",
    "github": "https://github.com/search?q={q}",
    "stackoverflow": "https://stackoverflow.com/search?q={q}",
    "wikipedia": "https://en.wikipedia.org/w/index.php?search={q}",
}

DEFAULT_ENGINE = "duckduckgo"


def _validate_url(url: str) -> str:
    """Ensure the URL is http(s) before handing it to the OS."""
    candidate = url.strip()
    if not candidate:
        raise ToolError("No URL provided.", "bad_arguments")
    if "://" not in candidate:
        candidate = "https://" + candidate
    parsed = urllib.parse.urlparse(candidate)
    if parsed.scheme not in ("http", "https"):
        raise ToolError(
            f"Refusing to open non-web URL scheme {parsed.scheme!r}. "
            "Only http and https are allowed.",
            "unsafe_url",
        )
    if not parsed.netloc:
        raise ToolError(f"{url!r} is not a valid web address.", "bad_arguments")
    return candidate


def _open_in_default_browser(url: str) -> None:
    import webbrowser

    if not webbrowser.open(url, new=2, autoraise=True):
        raise ToolError(
            f"Could not hand {url!r} to a browser.", "browser_failed"
        )


def open_url(url: str) -> str:
    """Open a web address in the default browser."""
    safe = _validate_url(url)
    _open_in_default_browser(safe)
    time.sleep(0.4)
    return f"Opened {safe}"


def search_web(query: str, engine: str = DEFAULT_ENGINE) -> dict[str, str]:
    """Open a search-engine results page for a query."""
    cleaned = query.strip()
    if not cleaned:
        raise ToolError("No search query provided.", "bad_arguments")

    key = (engine or DEFAULT_ENGINE).strip().lower()
    template = SEARCH_ENGINES.get(key)
    if template is None:
        key = DEFAULT_ENGINE
        template = SEARCH_ENGINES[key]

    url = template.format(q=urllib.parse.quote_plus(cleaned))
    _open_in_default_browser(url)
    time.sleep(0.4)
    return {
        "result": (
            f"Opened {key} search results for {cleaned!r} at {url}. "
            "To read a specific result, use read_webpage with its URL."
        ),
        "url": url,
        "engine": key,
    }


def _focus_browser_window() -> bool:
    """Focus a browser window if one is open. Returns success."""
    try:
        import pygetwindow as gw
    except ImportError:
        return False
    markers = ("chrome", "edge", "firefox", "brave", "opera", "vivaldi")
    try:
        for win in gw.getAllWindows():
            title = (win.title or "").lower()
            if any(m in title for m in markers):
                if win.isMinimized:
                    win.restore()
                win.activate()
                time.sleep(0.35)
                return True
    except Exception:  # noqa: BLE001
        log.debug("could not focus a browser window", exc_info=True)
    return False


def _send_hotkey(keys: list[str]) -> None:
    try:
        import pyautogui
    except ImportError as exc:
        raise ToolError(
            "pyautogui is not installed; run install.bat", "missing_dependency"
        ) from exc
    pyautogui.hotkey(*keys)


def new_tab() -> str:
    """Open a new browser tab."""
    if not _focus_browser_window():
        raise ToolError(
            "No browser window found to switch tabs in. Open one first.",
            "browser_not_open",
        )
    _send_hotkey(["ctrl", "t"])
    return "Opened a new browser tab."


def read_webpage(url: str, max_chars: int = 4000) -> dict[str, Any]:
    """Fetch a webpage via HTTP GET and extract its readable plain text."""
    safe_url = _validate_url(url)
    try:
        import httpx
    except ImportError:
        httpx = None

    html_content = ""
    if httpx is not None:
        try:
            with httpx.Client(timeout=15.0, follow_redirects=True, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}) as client:
                resp = client.get(safe_url)
                resp.raise_for_status()
                html_content = resp.text
        except Exception as e:
            raise ToolError(f"HTTP request failed: {e}", "network_error") from e
    else:
        # Fallback to urllib standard library
        try:
            import urllib.request
            req = urllib.request.Request(safe_url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
            with urllib.request.urlopen(req, timeout=15) as resp:
                html_content = resp.read().decode("utf-8", errors="replace")
        except Exception as e:
            raise ToolError(f"Failed to fetch webpage: {e}", "network_error") from e

    # Parse and extract text using BeautifulSoup or regex fallback
    title = ""
    try:
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html_content, "html.parser")
        if soup.title and soup.title.string:
            title = soup.title.string.strip()
        for element in soup(["script", "style", "nav", "footer", "header", "noscript"]):
            element.decompose()
        text = soup.get_text(separator=" ", strip=True)
    except ImportError:
        import re
        # Basic regex tag stripper
        title_match = re.search(r"<title>(.*?)</title>", html_content, re.IGNORECASE | re.DOTALL)
        if title_match:
            title = title_match.group(1).strip()
        clean = re.sub(r"<(script|style|nav|footer|header)[^>]*>.*?</\1>", " ", html_content, flags=re.IGNORECASE | re.DOTALL)
        clean = re.sub(r"<[^>]+>", " ", clean)
        text = " ".join(clean.split())

    limit = max(500, min(max_chars, 20000))
    truncated = False
    if len(text) > limit:
        text = text[:limit] + f"... [truncated: {len(text) - limit} characters omitted]"
        truncated = True

    return {
        "result": text or "(page had no readable text)",
        "url": safe_url,
        "title": title,
        "chars": len(text),
        "truncated": truncated,
    }


def close_tab() -> str:
    """Close the current browser tab."""
    if not _focus_browser_window():
        raise ToolError(
            "No browser window found to switch tabs in.", "browser_not_open"
        )
    _send_hotkey(["ctrl", "w"])
    return "Closed the current browser tab."


TOOLS = [
    Tool(
        name="open_url",
        description="Open a web address (http/https only) in the default browser.",
        parameters={
            "type": "object",
            "properties": {"url": {"type": "string", "description": "Web address"}},
            "required": ["url"],
        },
        handler=open_url,
        level=Level.SAFE,
        timeout=20.0,
        category="browser",
    ),
    Tool(
        name="search_web",
        description=(
            "Open a web search for a query in the browser. This opens the results "
            "page only; combine with read_webpage to actually read a result."
        ),
        parameters={
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search terms"},
                "engine": {
                    "type": "string",
                    "description": "Search engine: google, duckduckgo, bing, youtube, github, wikipedia",
                    "default": "duckduckgo",
                },
            },
            "required": ["query"],
        },
        handler=search_web,
        level=Level.SAFE,
        timeout=20.0,
        category="browser",
    ),
    Tool(
        name="new_tab",
        description="Open a new tab in the most recently used browser window.",
        parameters={"type": "object", "properties": {}},
        handler=new_tab,
        level=Level.SAFE,
        timeout=15.0,
        category="browser",
    ),
    Tool(
        name="close_tab",
        description="Close the current tab in the browser window.",
        parameters={"type": "object", "properties": {}},
        handler=close_tab,
        level=Level.MODERATE,
        timeout=15.0,
        confirm_template="close the current browser tab",
        category="browser",
    ),
    Tool(
        name="read_webpage",
        description="Fetch a URL and extract its readable text content (does not open GUI browser).",
        parameters={
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "Web address to read"},
                "max_chars": {"type": "integer", "description": "Max characters to return", "default": 4000},
            },
            "required": ["url"],
        },
        handler=read_webpage,
        level=Level.SAFE,
        timeout=20.0,
        category="browser",
    ),
]