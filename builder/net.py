"""HTTP for the snapshot builder: standard library only, polite, offline-capable.

Online: GET with an identifying User-Agent, > 1 s between requests to one host, retries on
429/5xx, a per-host request budget. Offline (`--offline DIR`): the same call returns a saved
Sprint 0 fixture instead, so the builder runs in tests with no network.
"""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

USER_AGENT = ("AWQP-CO-Waters-snapshot/1 (Colorado State University Agricultural Water Quality "
              "Program; public display of Colorado water conditions; "
              "github.com/mannydeleon99/awqp-co-waters-data)")
MIN_INTERVAL_S = 1.1
TIMEOUT_S = 120
ATTEMPTS = 3
RETRY_STATUS = {429, 500, 502, 503, 504}
HOST_BUDGET = 50  # per run; Sprint 0 rule: more than ~50 to one host needs Manny's OK


class FetchError(Exception):
    pass


class Net:
    def __init__(self, offline: Path | None = None):
        self.offline = offline
        self.last: dict[str, float] = {}
        self.count: dict[str, int] = {}
        self.bytes = 0

    def get_json(self, url: str, params: list[tuple[str, str]] | dict | None = None,
                 fixture: str | None = None):
        """GET url and parse JSON. Offline: read `fixture` (path under the fixtures dir)."""
        data = self._get(url, params, fixture, "application/json, application/geo+json")
        try:
            return json.loads(data)
        except json.JSONDecodeError as e:
            raise FetchError(f"JSONDecodeError: {e} from {url}") from e

    def get_text(self, url: str, params: list[tuple[str, str]] | dict | None = None,
                 fixture: str | None = None, accept: str = "text/csv") -> str:
        """GET url as UTF-8 text (CSV). Offline: read `fixture`. An empty body is returned as ''."""
        return self._get(url, params, fixture, accept).decode("utf-8")

    def _get(self, url: str, params, fixture: str | None, accept: str) -> bytes:
        if self.offline is not None:
            if not fixture:
                raise FetchError(f"offline: no fixture for {url}")
            p = self.offline / fixture
            if not p.exists():
                raise FetchError(f"offline: fixture missing: {p}")
            data = p.read_bytes()
            self.bytes += len(data)
            return data
        q = urllib.parse.urlencode(params or [], doseq=True)
        full = f"{url}?{q}" if q else url
        host = urllib.parse.urlsplit(url).netloc
        n = self.count.get(host, 0) + 1
        if n > HOST_BUDGET:
            raise FetchError(f"request budget for {host} used up ({HOST_BUDGET})")
        self.count[host] = n
        err = None
        for attempt in range(ATTEMPTS):
            wait = self.last.get(host, 0) + MIN_INTERVAL_S - time.time()
            if wait > 0:
                time.sleep(wait)
            self.last[host] = time.time()
            req = urllib.request.Request(full, headers={"User-Agent": USER_AGENT, "Accept": accept})
            try:
                with urllib.request.urlopen(req, timeout=TIMEOUT_S) as r:
                    data = r.read()
                self.bytes += len(data)
                return data
            except urllib.error.HTTPError as e:
                err = f"HTTP {e.code} from {full}"
                if e.code not in RETRY_STATUS:
                    break
            except (urllib.error.URLError, TimeoutError) as e:
                err = f"{type(e).__name__}: {e} from {full}"
            time.sleep(5 * (attempt + 1))
        raise FetchError(err)
