"""TorBox search client — searches TorBox's own torrent/usenet index.

Hits https://search-api.torbox.app (not the main api.torbox.app).
"""

import requests
from typing import List, Dict, Any, Optional
from urllib.parse import urlencode, quote


class TorBoxSearchClient:
    """Client for the TorBox search API."""

    SEARCH_BASE = "https://search-api.torbox.app"

    def __init__(self, api_key: str):
        self.api_key = api_key
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {api_key}",
            "User-Agent": "TorBoxFinder/0.1.0",
        })

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _search(
        self,
        kind: str,  # "torrents" or "usenet"
        query: str,
        search_user_engines: bool = False,
    ) -> List[Dict[str, Any]]:
        """Run a search and return normalized results."""
        params = {
            "metadata": "true",
            "check_cache": "true",
            "search_user_engines": "true" if search_user_engines else "false",
        }

        # Detect search prefixes (imdb, tvdb, jikan)
        prefix = None
        for p in ("imdb", "tvdb", "jikan"):
            if query.startswith(f"{p}:"):
                prefix = p
                break

        if prefix:
            system_id = query[len(prefix) + 1 :]
            endpoint = f"{self.SEARCH_BASE}/{kind}/{prefix}:{system_id}?{urlencode(params)}"
        else:
            endpoint = f"{self.SEARCH_BASE}/{kind}/search/{quote(query, safe='')}?{urlencode(params)}"

        resp = self.session.get(endpoint, timeout=30)
        resp.raise_for_status()
        data = resp.json()

        # Extract results list
        if kind == "usenet":
            results = data.get("data", {}).get("nzbs", [])
        else:
            results = data.get("data", {}).get("torrents", [])

        return [_normalize_result(r, kind) for r in results]

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def search_torrents(self, query: str, search_user_engines: bool = False) -> List[Dict[str, Any]]:
        return self._search("torrents", query, search_user_engines)

    def search_usenet(self, query: str, search_user_engines: bool = False) -> List[Dict[str, Any]]:
        return self._search("usenet", query, search_user_engines)


class TorBoxSearchError(Exception):
    """Custom exception for TorBox search errors."""
    pass


# ---------------------------------------------------------------------------
# Normalization helpers
# ---------------------------------------------------------------------------
def _normalize_result(item: dict, kind: str) -> dict:
    """Normalize a TorBox search result so the TUI can display it uniformly."""
    normalized = {
        "_source": "torbox",
        "_kind": kind,  # "torrents" or "usenet"
        "title": item.get("raw_title") or item.get("title") or "Unnamed",
        "size": int(item.get("size") or 0),
        "age": _parse_age(item.get("age")),
        "tracker": item.get("tracker") or "Unknown",
        "cached": bool(item.get("cached")),
        "hash": item.get("hash") or "",
    }

    if kind == "torrents":
        normalized["seeders"] = int(item.get("last_known_seeders") or 0)
        normalized["peers"] = int(item.get("last_known_peers") or 0)
        normalized["magnet"] = item.get("magnet") or ""
    else:
        normalized["nzb"] = item.get("nzb") or ""

    # Preserve raw data that the TUI may need for adding
    normalized["_raw"] = item
    return normalized


def _parse_age(age_val) -> int:
    """TorBox returns age as a string like '7d' or an int. Convert to days."""
    if age_val is None:
        return 0
    if isinstance(age_val, int):
        return age_val
    try:
        return int(str(age_val).replace("d", "").strip())
    except (ValueError, TypeError):
        return 0
