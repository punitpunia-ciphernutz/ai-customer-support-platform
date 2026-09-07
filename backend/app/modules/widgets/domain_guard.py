"""Origin / host allowlist matching for embeddable widgets."""

from __future__ import annotations

from urllib.parse import urlparse


def normalize_host(value: str | None) -> str | None:
    """Normalize a host or Origin/Referer URL to a lowercase hostname without port."""
    if not value:
        return None
    raw = value.strip().lower()
    if not raw:
        return None

    if "://" in raw:
        parsed = urlparse(raw)
        host = parsed.hostname
    else:
        # Strip path/query if a bare host with junk was passed
        host = raw.split("/")[0].split("?")[0]
        if host.startswith("[") and "]" in host:
            host = host[1 : host.index("]")]
        elif ":" in host:
            # hostname:port — drop port for standard comparison
            maybe_host, maybe_port = host.rsplit(":", 1)
            if maybe_port.isdigit():
                host = maybe_host

    if not host:
        return None
    return host.rstrip(".")


def host_matches_allowlist(host: str | None, allowed_domains: list[str] | None) -> bool:
    """
    Exact match against allowlist entries, or single-level wildcard prefix.

    Examples:
      - example.com matches example.com
      - www.example.com matches www.example.com
      - *.example.com matches a.example.com but NOT example.com and NOT a.b.example.com
    """
    if not host:
        return False
    allow = [d.strip().lower().rstrip(".") for d in (allowed_domains or []) if d and d.strip()]
    if not allow:
        return False

    host = host.rstrip(".").lower()
    for entry in allow:
        if entry.startswith("*."):
            suffix = entry[2:]
            if not suffix:
                continue
            # Require exactly one additional label before the suffix
            if host.endswith("." + suffix):
                prefix = host[: -(len(suffix) + 1)]
                if prefix and "." not in prefix:
                    return True
            continue
        if host == entry:
            return True
    return False


def extract_request_host(
    *,
    origin: str | None = None,
    referer: str | None = None,
    page_host: str | None = None,
) -> str | None:
    """Prefer explicit page_host (iframe attestation), then Origin, then Referer."""
    for candidate in (page_host, origin, referer):
        host = normalize_host(candidate)
        if host:
            return host
    return None
