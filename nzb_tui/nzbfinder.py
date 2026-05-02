"""NZBFinder API client using the working Newznab XML API."""

import requests
import xml.etree.ElementTree as ET
from typing import List, Dict, Any, Optional
from urllib.parse import urlencode


class NZBFinderClient:
    """Client for NZBFinder Newznab XML API.

    The v2 REST API consistently returns 401 even with valid API keys.
    The legacy /api endpoint works and returns XML.
    """

    BASE_URL = "https://nzbfinder.ws/api"
    NS_NEWZNAB = "http://www.newznab.com/DTD/2010/feeds/attributes/"

    def __init__(self, api_key: str):
        self.api_key = api_key
        self.session = requests.Session()
        self.last_total: Optional[int] = None

    def search(
        self,
        query: str,
        limit: int = 50,
        offset: int = 0,
        category: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Search NZBFinder for NZBs. Returns parsed items from XML."""
        params = {
            "t": "search",
            "q": query,
            "apikey": self.api_key,
            "limit": limit,
            "offset": offset,
        }
        if category:
            params["cat"] = category

        url = f"{self.BASE_URL}?{urlencode(params)}"
        response = self.session.get(url, timeout=30)
        response.raise_for_status()

        root = ET.fromstring(response.content)

        # Extract total from <newznab:response offset="0" total="8221"/>
        self.last_total = None
        resp_tag = root.find(".//{http://www.newznab.com/DTD/2010/feeds/attributes/}response")
        if resp_tag is not None:
            total_str = resp_tag.get("total")
            if total_str is not None:
                try:
                    self.last_total = int(total_str)
                except ValueError:
                    self.last_total = None

        items = root.findall(".//item")
        results = []
        for item in items:
            results.append(self._parse_item(item))
        return results

    def _parse_item(self, item: ET.Element) -> Dict[str, Any]:
        """Parse a single <item> element into a dict."""
        ns = {"nz": self.NS_NEWZNAB}

        def get_text(tag: str) -> str:
            el = item.find(tag)
            return el.text if el is not None else ""

        title = get_text("title")
        guid = get_text("guid")
        link = get_text("link")
        pub_date = get_text("pubDate")
        category = get_text("category")

        # Extract ID from guid URL: https://nzbfinder.ws/details/UUID
        nzb_id = ""
        if guid:
            parts = guid.rstrip("/").split("/")
            if parts:
                nzb_id = parts[-1]

        # Extract size from newznab:attr
        size = 0
        size_attr = item.find(f"nz:attr[@name='size']", ns)
        if size_attr is not None:
            size = int(size_attr.get("value", "0") or "0")

        # Fallback: enclosure length
        if size == 0:
            enclosure = item.find("enclosure")
            if enclosure is not None:
                size = int(enclosure.get("length", "0") or "0")

        return {
            "title": title,
            "guid": guid,
            "id": nzb_id,
            "link": link,
            "size": size,
            "pubDate": pub_date,
            "category": category,
        }

    def get_nzb_download_link(self, nzb_id: str) -> str:
        """Get direct NZB download link.

        Uses the legacy getnzb endpoint which is confirmed to work.
        """
        # nzb_id might already be a full GUID URL; extract just the UUID
        raw_id = nzb_id
        if "/" in raw_id:
            raw_id = raw_id.rstrip("/").split("/")[-1]
        return f"https://nzbfinder.ws/api/v1/getnzb?id={raw_id}.nzb&apikey={self.api_key}"

    def download_nzb(self, nzb_id: str) -> bytes:
        """Download the raw NZB file bytes."""
        url = self.get_nzb_download_link(nzb_id)
        response = self.session.get(url, timeout=60)
        response.raise_for_status()
        return response.content

    def download_nzb_for_item(self, item: Dict[str, Any]) -> bytes:
        """Download the raw NZB for a search result *item* dict.

        Tries the ``link`` field first (pre-built URL from NZBFinder XML),
        otherwise builds the URL from the item's ``id`` / ``guid``.
        """
        link = item.get("link")
        if link:
            response = self.session.get(link, timeout=60)
            response.raise_for_status()
            return response.content
        nzb_id = item.get("id") or item.get("guid", "")
        if not nzb_id:
            raise ValueError("Item has no downloadable NZB link or ID")
        return self.download_nzb(nzb_id)


class NZBFinderError(Exception):
    """Custom exception for NZBFinder API errors."""

    pass
