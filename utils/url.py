from urllib.parse import urlparse, urlunparse, urlencode, parse_qsl

# Query parameters that carry no identity information — strip these
TRACKING_PARAMS = {
    "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
    "refid", "refId", "trackingId", "tracking_id", "ref", "referrer",
    "source", "src", "from", "fromage", "sort", "start",
    "trk", "trkInfo", "originalSubdomain",
}


def clean_url(url: str) -> str:
    """Normalize a job URL for consistent storage and deduplication."""
    if not url:
        return ""
    try:
        parsed = urlparse(url.strip())

        # Lowercase scheme and host
        scheme = parsed.scheme.lower()
        netloc = parsed.netloc.lower()

        # Strip trailing slash from path
        path = parsed.path.rstrip("/")

        # Remove tracking query params, keep identity params
        kept_params = [
            (k, v) for k, v in parse_qsl(parsed.query)
            if k.lower() not in TRACKING_PARAMS
        ]
        query = urlencode(kept_params)

        # Drop fragment entirely
        cleaned = urlunparse((scheme, netloc, path, "", query, ""))
        return cleaned
    except Exception:
        return url
