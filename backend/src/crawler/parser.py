"""
HTML parser and content extractor using selectolax.

selectolax is chosen over BeautifulSoup for its significantly better
performance (10-20x faster) — critical when parsing thousands of pages.

Responsibilities:
- Extract page title
- Extract clean text content (stripping nav, footer, scripts)
- Extract outgoing links
"""

from urllib.parse import urljoin

from selectolax.parser import HTMLParser


# Tags to remove entirely before extracting text content.
# These typically contain navigation, boilerplate, or non-content elements.
REMOVE_TAGS = [
    "script", "style", "nav", "footer", "header",
    "aside", "noscript", "iframe", "svg",
]

# CSS selectors for common boilerplate elements in documentation sites.
REMOVE_SELECTORS = [
    ".sidebar", ".navigation", ".nav-links", ".breadcrumb",
    ".footer", ".header", "#sidebar", "#navigation",
    "[role='navigation']", "[role='banner']", "[role='contentinfo']",
]


def extract_title(html: str) -> str:
    """Extract the page title from HTML."""
    tree = HTMLParser(html)

    # Try <title> tag first
    title_node = tree.css_first("title")
    if title_node and title_node.text():
        return title_node.text().strip()

    # Fall back to first <h1>
    h1_node = tree.css_first("h1")
    if h1_node and h1_node.text():
        return h1_node.text().strip()

    return ""


def extract_content(html: str) -> str:
    """
    Extract clean text content from HTML.

    Strips all boilerplate (nav, sidebar, footer) and returns only
    the main content text. This is what gets indexed for search.
    """
    tree = HTMLParser(html)

    # Remove boilerplate tags
    for tag in REMOVE_TAGS:
        for node in tree.css(tag):
            node.decompose()

    # Remove boilerplate by CSS selector
    for selector in REMOVE_SELECTORS:
        for node in tree.css(selector):
            node.decompose()

    # Try to find the main content area first
    main = tree.css_first("main, article, [role='main'], .content, #content")
    if main:
        text = main.text(separator="\n", strip=True)
    else:
        # Fall back to body
        body = tree.css_first("body")
        text = body.text(separator="\n", strip=True) if body else ""

    # Clean up excessive whitespace
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    return "\n".join(lines)


def extract_links(html: str, base_url: str) -> list[dict[str, str]]:
    """
    Extract all outgoing links from HTML.

    Returns a list of dicts with 'url' and 'anchor_text' keys.
    Resolves relative URLs against the base URL.
    """
    tree = HTMLParser(html)
    links = []
    seen = set()

    for node in tree.css("a[href]"):
        href = node.attributes.get("href", "")
        if not href:
            continue

        # Skip non-HTTP links
        if href.startswith(("mailto:", "javascript:", "tel:", "#")):
            continue

        # Resolve relative URL
        absolute_url = urljoin(base_url, href)

        # Deduplicate within this page
        if absolute_url in seen:
            continue
        seen.add(absolute_url)

        anchor_text = node.text(strip=True) or ""
        links.append({
            "url": absolute_url,
            "anchor_text": anchor_text[:1024],  # Cap anchor text length
        })

    return links
