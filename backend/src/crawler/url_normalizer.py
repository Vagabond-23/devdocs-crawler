"""
URL Normalizer / Canonicalizer.

Normalizes URLs to prevent duplicate crawling of equivalent pages.

Handles:
- Lowercasing scheme and hostname
- Removing fragments (#section)
- Removing trailing slashes (except root)
- Sorting query parameters
- Resolving relative URLs
- Removing default ports (80/443)
"""

from urllib.parse import urlparse, urlunparse, urlencode, parse_qs, urljoin


def normalize_url(url: str, base_url: str | None = None) -> str | None:
    """
    Canonicalize a URL into a normalized form.

    Args:
        url: The URL to normalize (can be relative if base_url is provided).
        base_url: Base URL for resolving relative URLs.

    Returns:
        Normalized URL string, or None if the URL is invalid/unsupported.
    """
    # Resolve relative URLs
    if base_url and not url.startswith(("http://", "https://")):
        url = urljoin(base_url, url)

    try:
        parsed = urlparse(url)
    except Exception:
        return None

    # Only crawl HTTP/HTTPS
    scheme = parsed.scheme.lower()
    if scheme not in ("http", "https"):
        return None

    # Lowercase hostname
    hostname = parsed.hostname
    if not hostname:
        return None
    hostname = hostname.lower()

    # Remove default ports
    port = parsed.port
    if (scheme == "http" and port == 80) or (scheme == "https" and port == 443):
        port = None

    # Build netloc
    netloc = hostname
    if port:
        netloc = f"{hostname}:{port}"

    # Normalize path — remove trailing slash (except for root "/")
    path = parsed.path or "/"
    if path != "/" and path.endswith("/"):
        path = path.rstrip("/")

    # Sort query parameters for consistency
    # e.g., ?b=2&a=1 → ?a=1&b=2
    query = ""
    if parsed.query:
        params = parse_qs(parsed.query, keep_blank_values=True)
        sorted_params = sorted(params.items())
        query = urlencode(sorted_params, doseq=True)

    # Strip fragment entirely — fragments are client-side only
    fragment = ""

    return urlunparse((scheme, netloc, path, parsed.params, query, fragment))


def extract_hostname(url: str) -> str | None:
    """Extract the hostname from a URL."""
    try:
        return urlparse(url).hostname
    except Exception:
        return None


def is_same_host(url: str, hostname: str) -> bool:
    """Check if a URL belongs to the given hostname."""
    url_host = extract_hostname(url)
    return url_host is not None and url_host.lower() == hostname.lower()
