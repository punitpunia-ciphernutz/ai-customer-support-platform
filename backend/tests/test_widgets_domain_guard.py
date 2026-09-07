"""Unit tests for widget domain allowlist matching."""

from app.modules.widgets.domain_guard import (
    extract_request_host,
    host_matches_allowlist,
    normalize_host,
)


def test_normalize_host_from_origin() -> None:
    assert normalize_host("https://Example.com:443/path") == "example.com"
    assert normalize_host("http://localhost:3000") == "localhost"
    assert normalize_host("www.example.com") == "www.example.com"
    assert normalize_host("example.com:8080") == "example.com"


def test_exact_allowlist_match() -> None:
    allow = ["example.com", "www.example.com"]
    assert host_matches_allowlist("example.com", allow)
    assert host_matches_allowlist("www.example.com", allow)
    assert not host_matches_allowlist("evil.com", allow)
    assert not host_matches_allowlist("example.com.evil.com", allow)
    assert not host_matches_allowlist("notexample.com", allow)


def test_wildcard_single_label() -> None:
    allow = ["*.example.com"]
    assert host_matches_allowlist("a.example.com", allow)
    assert host_matches_allowlist("staging.example.com", allow)
    assert not host_matches_allowlist("example.com", allow)
    assert not host_matches_allowlist("a.b.example.com", allow)
    assert not host_matches_allowlist("evil.com", allow)


def test_empty_allowlist_rejects() -> None:
    assert not host_matches_allowlist("example.com", [])
    assert not host_matches_allowlist("example.com", None)
    assert not host_matches_allowlist(None, ["example.com"])


def test_extract_request_host_prefers_page_host() -> None:
    host = extract_request_host(
        origin="https://spoofed.com",
        referer="https://spoofed.com/x",
        page_host="example.com",
    )
    assert host == "example.com"
