#!/usr/bin/env python3
"""GET/POST helper with retries for the monthly job. Standard library only.

Why retries matter: a monthly job that fails once for a few seconds (a passing
network or server problem) would otherwise lose a whole month, because the search
window only overlaps the next run by about two weeks. Older papers would never be
scanned again.

`describe` turns an exception into a short readable text ("HTTP 503 ...") so the
report can say WHY a topic could not be checked, not just that it failed.
"""
import http.client
import time
import urllib.error
import urllib.request

ATTEMPTS = 3
DELAYS = (5, 30)        # seconds to wait before the 2nd and 3rd attempt
MAX_RETRY_AFTER = 120   # never sleep longer than this, even if the server asks
# 403 is included on purpose: it is usually permanent, but shared CI addresses are
# sometimes blocked for a short while, and a monthly job can afford two more tries.
RETRY_STATUS = {403, 408, 425, 429, 500, 502, 503, 504}

# What callers should catch. OSError covers URLError, HTTPError, timeouts and a
# connection reset mid-read; HTTPException covers a truncated or malformed response.
FETCH_ERRORS = (OSError, http.client.HTTPException)


def fetch(req, timeout, sleep=time.sleep, opener=urllib.request.urlopen):
    """Return the body bytes of `req`. Raise the last error once the attempts run out."""
    for attempt in range(ATTEMPTS):
        try:
            with opener(req, timeout=timeout) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            if e.code not in RETRY_STATUS or attempt == ATTEMPTS - 1:
                raise
            delay = _retry_after(e) or DELAYS[attempt]
        except FETCH_ERRORS:
            if attempt == ATTEMPTS - 1:
                raise
            delay = DELAYS[attempt]
        sleep(delay)
    raise AssertionError("unreachable")


def _retry_after(e):
    try:
        return min(int(e.headers.get("Retry-After", "")), MAX_RETRY_AFTER)
    except (AttributeError, TypeError, ValueError):
        return None     # header absent, or in the HTTP-date form: use our own schedule


def describe(e):
    """Short text for a report: 'HTTP 503 Service Unavailable', not just 'HTTPError'."""
    if isinstance(e, urllib.error.HTTPError):
        return f"HTTP {e.code} {e.reason}"
    if isinstance(e, urllib.error.URLError):
        return f"{type(e).__name__}: {e.reason}"
    return type(e).__name__
