"""Regression tests for NewsService.extract_url.

Guards against the URL over-/under-matching bug: the old pattern used the
character class `[$-_@.&+]`, where a stray hyphen turned the intended literal
set into the range $..._ — matching prose delimiters (< > [ ] \\ ^ ?) into the
URL while dropping legal chars like ~ and #. See app/services/news_service.py.

Run: `uv run pytest tests/`
"""
import pytest

from app.services.news_service import news_service


# URLs that must be extracted intact (path / query / fragment preserved).
KEEP = [
    ("http://example.com", "http://example.com"),
    ("visit https://example.com/path?x=1&y=2 now", "https://example.com/path?x=1&y=2"),
    ("port http://example.com:8080/p here", "http://example.com:8080/p"),
    # ~ and # are legal but were OUTSIDE the old buggy range -> used to truncate.
    ("frag https://site.com/~user/p#frag end", "https://site.com/~user/p#frag"),
    ("enc https://x.com/a%20b%2Fc done", "https://x.com/a%20b%2Fc"),
    ("https://t.me/telegram", "https://t.me/telegram"),
]

# Surrounding markup / punctuation that must NOT be swallowed into the URL.
STOP = [
    ("check http://example.com<script>alert(1)</script> ok", "http://example.com"),
    ("link https://site.com/path?x=1>redirect here", "https://site.com/path?x=1"),
    ("see http://a.com]extra and more", "http://a.com"),
    ("trailing dot http://x.com. end", "http://x.com"),
    ("comma http://x.com, then", "http://x.com"),
    ('quote "http://x.com" done', "http://x.com"),
]


@pytest.mark.parametrize("text,expected", KEEP)
def test_extract_url_keeps_valid(text, expected):
    assert news_service.extract_url(text) == expected


@pytest.mark.parametrize("text,expected", STOP)
def test_extract_url_stops_at_delimiters(text, expected):
    assert news_service.extract_url(text) == expected


def test_extract_url_none_when_absent():
    assert news_service.extract_url("no link here, just text") is None


def test_extract_url_is_linear_on_adversarial_input():
    """A 200k-char blob must not freeze the single-threaded event loop."""
    import time

    blob = "http://" + "a" * 200_000 + " tail"
    start = time.perf_counter()
    news_service.extract_url(blob)
    assert time.perf_counter() - start < 1.0
