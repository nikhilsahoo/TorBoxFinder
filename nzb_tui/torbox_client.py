"""TorBox API client using the official ``torbox_api`` SDK."""

from typing import List, Dict, Any, Optional

import requests

from torbox_api import TorboxApi
from torbox_api.models import CreateUsenetDownloadRequest


class TorBoxClient:
    """Wrapper around the official ``torbox_api`` SDK."""

    BASE_URL = "https://api.torbox.app"
    API_VERSION = "v1"

    def __init__(self, api_key: str):
        self._api_key = api_key
        self._sdk = TorboxApi(
            access_token=api_key,
            base_url=self.BASE_URL,
        )
        self._session = requests.Session()
        self._session.headers["User-Agent"] = "nzb-tui/0.1.0"

    # ------------------------------------------------------------------
    # Usenet
    # ------------------------------------------------------------------
    def list_usenet(self, offset: int = 0, limit: int = 1000) -> List[Dict[str, Any]]:
        resp = self._sdk.usenet.get_usenet_list(
            api_version=self.API_VERSION,
            offset=str(offset),
            limit=str(limit),
            bypass_cache="false",
        )
        data = getattr(resp, "data", None)
        if data is None:
            return []
        if isinstance(data, dict):
            return [data]
        return [_model_to_dict(x) for x in data]

    def add_usenet(self, file: bytes, name: Optional[str] = None) -> Dict[str, Any]:
        url = f"{self.BASE_URL}/v1/api/usenet/createusenetdownload"
        safe_name = (
            "".join(c if c.isalnum() or c in " ._-" else "_" for c in (name or "download")).strip(" .")
            + ".nzb"
        )
        files = {"file": (safe_name, file, "application/octet-stream")}
        headers = {"Authorization": f"Bearer {self._api_key}"}
        try:
            response = self._session.post(url, files=files, headers=headers, timeout=60)
            response.raise_for_status()
            return response.json()
        except requests.HTTPError as exc:
            try:
                payload = exc.response.json() if exc.response is not None else {}
            except ValueError:
                payload = {}
            return {
                "success": False,
                "error": payload.get("error", f"HTTP {exc.response.status_code if exc.response else '?'}"),
                "detail": payload.get("detail", str(exc)),
            }
        except Exception as exc:
            return {"success": False, "error": type(exc).__name__, "detail": str(exc)}

    def delete_usenet(self, usenet_id: int) -> None:
        self._sdk.usenet.control_usenet_download(
            api_version=self.API_VERSION,
            request_body={"usenet_id": usenet_id, "operation": "delete"},
        )

    def add_usenet_link(self, link: str, name: Optional[str] = None) -> Dict[str, Any]:
        """Add a usenet download by passing a direct NZB link."""
        url = f"{self.BASE_URL}/v1/api/usenet/createusenetdownload"
        data = {"link": link}
        if name:
            data["name"] = name
        headers = {"Authorization": f"Bearer {self._api_key}"}
        try:
            response = self._session.post(url, data=data, headers=headers, timeout=60)
            response.raise_for_status()
            return response.json()
        except requests.HTTPError as exc:
            try:
                payload = exc.response.json() if exc.response is not None else {}
            except ValueError:
                payload = {}
            return {
                "success": False,
                "error": payload.get("error", f"HTTP {exc.response.status_code if exc.response else '?'}"),
                "detail": payload.get("detail", str(exc)),
            }
        except Exception as exc:
            return {"success": False, "error": type(exc).__name__, "detail": str(exc)}

    def download_usenet(self, usenet_id: int, file_id: Optional[int] = None, zip_link: bool = False) -> str:
        url = f"{self.BASE_URL}/v1/api/usenet/requestdl?token={self._api_key}&usenet_id={usenet_id}&redirect=true"
        if zip_link:
            url += "&zip_link=true"
        if file_id:
            url += f"&file_id={file_id}"
        return url

    # ------------------------------------------------------------------
    # Torrents
    # ------------------------------------------------------------------
    def list_torrents(self, offset: int = 0, limit: int = 1000) -> List[Dict[str, Any]]:
        resp = self._sdk.torrents.get_torrent_list(
            api_version=self.API_VERSION,
            offset=str(offset),
            limit=str(limit),
            bypass_cache="false",
        )
        data = getattr(resp, "data", None)
        if data is None:
            return []
        if isinstance(data, dict):
            return [data]
        return [_model_to_dict(x) for x in data]

    def delete_torrent(self, torrent_id: int) -> None:
        self._sdk.torrents.control_torrent(
            api_version=self.API_VERSION,
            request_body={"torrent_id": torrent_id, "operation": "delete"},
        )

    def add_torrent_magnet(self, magnet: str, name: Optional[str] = None, seed: int = 3, allow_zip: bool = True) -> Dict[str, Any]:
        url = f"{self.BASE_URL}/v1/api/torrents/createtorrent"
        data = {
            "magnet": magnet,
            "seed": str(seed),
            "allow_zip": "true" if allow_zip else "false",
        }
        if name:
            data["name"] = name
        headers = {"Authorization": f"Bearer {self._api_key}"}
        try:
            response = self._session.post(url, data=data, headers=headers, timeout=60)
            response.raise_for_status()
            return response.json()
        except requests.HTTPError as exc:
            try:
                payload = exc.response.json() if exc.response is not None else {}
            except ValueError:
                payload = {}
            return {
                "success": False,
                "error": payload.get("error", f"HTTP {exc.response.status_code if exc.response else '?'}"),
                "detail": payload.get("detail", str(exc)),
            }
        except Exception as exc:
            return {"success": False, "error": type(exc).__name__, "detail": str(exc)}

    def download_torrent(self, torrent_id: int, file_id: Optional[int] = None, zip_link: bool = False) -> str:
        url = f"{self.BASE_URL}/v1/api/torrents/requestdl?token={self._api_key}&torrent_id={torrent_id}&redirect=true"
        if zip_link:
            url += "&zip_link=true"
        if file_id:
            url += f"&file_id={file_id}"
        return url

    # ------------------------------------------------------------------
    # Web downloads
    # ------------------------------------------------------------------
    def list_web_downloads(self, offset: int = 0, limit: int = 1000) -> List[Dict[str, Any]]:
        resp = self._sdk.web_downloads_debrid.get_web_download_list(
            api_version=self.API_VERSION,
            offset=str(offset),
            limit=str(limit),
            bypass_cache="false",
        )
        data = getattr(resp, "data", None)
        if data is None:
            return []
        if isinstance(data, dict):
            return [data]
        return [_model_to_dict(x) for x in data]

    def delete_web_download(self, web_id: int) -> None:
        self._sdk.web_downloads_debrid.control_web_download(
            api_version=self.API_VERSION,
            request_body={"web_id": web_id, "operation": "delete"},
        )

    def download_web(self, web_id: int, file_id: Optional[int] = None, zip_link: bool = False) -> str:
        url = f"{self.BASE_URL}/v1/api/webdl/requestdl?token={self._api_key}&web_id={web_id}&redirect=true"
        if zip_link:
            url += "&zip_link=true"
        if file_id:
            url += f"&file_id={file_id}"
        return url

    # ------------------------------------------------------------------
    # Convenience helpers
    # ------------------------------------------------------------------
    def get_completed_downloads(self) -> List[Dict[str, Any]]:
        all_items = []
        for item in self.list_usenet():
            item["_type"] = "usenet"
            all_items.append(item)
        for item in self.list_torrents():
            item["_type"] = "torrent"
            all_items.append(item)
        for item in self.list_web_downloads():
            item["_type"] = "web"
            all_items.append(item)
        return [i for i in all_items if i.get("status", "").lower() in ("completed", "complete")]

    def get_active_downloads(self) -> List[Dict[str, Any]]:
        all_items = []
        for item in self.list_usenet():
            item["_type"] = "usenet"
            all_items.append(item)
        for item in self.list_torrents():
            item["_type"] = "torrent"
            all_items.append(item)
        for item in self.list_web_downloads():
            item["_type"] = "web"
            all_items.append(item)
        return [i for i in all_items if i.get("status", "").lower() not in ("completed", "complete")]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _model_to_dict(obj: Any) -> Any:
    """Coerce a SDK model (or collection of models) into plain dicts.

    Normalizes key names so ``id_`` becomes ``id`` and
    ``download_state`` becomes ``status``.
    """
    if obj is None:
        return None
    if isinstance(obj, (list, tuple)):
        return [_model_to_dict(x) for x in obj]
    if isinstance(obj, dict):
        return obj
    if hasattr(obj, "to_dict"):
        return obj.to_dict()
    if hasattr(obj, "__dict__"):
        d: Dict[str, Any] = {}
        for k, v in obj.__dict__.items():
            if k.startswith("_"):
                continue
            key = "id" if k == "id_" else k
            if key == "download_state":
                key = "status"
            d[key] = _model_to_dict(v)
        return d
    return obj
