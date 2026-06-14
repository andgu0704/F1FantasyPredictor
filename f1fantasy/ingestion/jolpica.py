"""Client for the Jolpica-F1 API (the Ergast successor).

Base URL: https://api.jolpi.ca/ergast/f1/
Docs:     https://github.com/jolpica/jolpica-f1

Jolpica keeps Ergast's response envelope: everything lives under
`MRData`, results are paginated with `limit`/`offset`, and `MRData.total`
tells you how many rows exist in total. This client hides the pagination
behind generators and is polite about Jolpica's rate limits (it is run by
volunteers — see the project README).
"""

from __future__ import annotations

import time
from typing import Iterator

import httpx

BASE_URL = "https://api.jolpi.ca/ergast/f1"
PAGE_SIZE = 100          # Jolpica's max page size
_MIN_INTERVAL = 0.30     # seconds between requests (stay well under the burst limit)


class JolpicaClient:
    def __init__(self, base_url: str = BASE_URL, timeout: float = 30.0) -> None:
        self._client = httpx.Client(base_url=base_url, timeout=timeout)
        self._last_request = 0.0

    def __enter__(self) -> "JolpicaClient":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def close(self) -> None:
        self._client.close()

    def _throttle(self) -> None:
        elapsed = time.monotonic() - self._last_request
        if elapsed < _MIN_INTERVAL:
            time.sleep(_MIN_INTERVAL - elapsed)
        self._last_request = time.monotonic()

    def _get(self, path: str, *, limit: int, offset: int) -> dict:
        self._throttle()
        resp = self._client.get(
            f"/{path.strip('/')}/", params={"limit": limit, "offset": offset}
        )
        resp.raise_for_status()
        return resp.json()["MRData"]

    def paginate(self, path: str) -> Iterator[dict]:
        """Yield each `MRData` page for `path`, walking offsets until exhausted."""
        offset = 0
        while True:
            mrdata = self._get(path, limit=PAGE_SIZE, offset=offset)
            yield mrdata
            total = int(mrdata["total"])
            offset += PAGE_SIZE
            if offset >= total:
                break

    # --- Typed-ish convenience accessors -------------------------------------

    def races(self, season: int) -> list[dict]:
        """Full schedule for a season (one dict per race, no results)."""
        races: list[dict] = []
        for page in self.paginate(f"{season}/races"):
            races.extend(page["RaceTable"]["Races"])
        return races

    def results(self, season: int) -> Iterator[dict]:
        """Yield each race dict (with its `Results` list) for a season."""
        for page in self.paginate(f"{season}/results"):
            yield from page["RaceTable"]["Races"]

    def qualifying(self, season: int) -> Iterator[dict]:
        """Yield each race dict (with its `QualifyingResults` list)."""
        for page in self.paginate(f"{season}/qualifying"):
            yield from page["RaceTable"]["Races"]

    def sprint(self, season: int) -> Iterator[dict]:
        """Yield each race dict (with its `SprintResults` list)."""
        for page in self.paginate(f"{season}/sprint"):
            yield from page["RaceTable"]["Races"]
