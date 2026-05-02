"""Download screen for TorBox downloads (usenet, torrents, web)."""

import urllib.request
from pathlib import Path
from typing import Optional

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal
from textual.screen import Screen
from textual.widgets import (
    Button,
    DataTable,
    Footer,
    Header,
    LoadingIndicator,
    ProgressBar,
    Static,
)

from nzb_tui.helpers import _human_size, _extract_filename
from nzb_tui.torbox_client import TorBoxClient


# ---------------------------------------------------------------------------
# DownloadScreen
# ---------------------------------------------------------------------------
class DownloadScreen(Screen):
    """Screen showing TorBox downloads (usenet, torrents, web)."""

    BINDINGS = [
        Binding("j", "cursor_down", "Down", show=False),
        Binding("k", "cursor_up", "Up", show=False),
        Binding("ctrl+d", "page_down", "PgDn", show=False),
        Binding("ctrl+u", "page_up", "PgUp", show=False),
        Binding("g,g", "top", "Top", show=False),
        Binding("G", "bottom", "Bottom", show=False),
        Binding("r", "refresh", "Refresh", show=False),
        Binding("d", "download_selected", "Download", show=False),
        Binding("delete", "delete_selected", "Delete", show=False),
        Binding("x", "delete_selected", "Delete", show=False),
        Binding("escape", "app.pop_screen", "Back", priority=True, show=False),
        Binding("q", "app.quit", "Quit", show=False),
    ]

    def __init__(self, client: TorBoxClient, download_dir: Path) -> None:
        self.client = client
        self.download_dir = download_dir
        self.current_items: list = []
        super().__init__()

    def compose(self) -> ComposeResult:
        yield Header()
        yield Static(
            "[b]TorBox Downloads[/b] "
            "[dim]j/k[/] move  [dim]ctrl+d/ctrl+u[/] page  [dim]gg/G[/] top/bottom",
            id="help_text_1",
        )
        yield Static(
            "[dim]r[/] refresh  [dim]d[/] download  [dim]x[/] delete  [dim]esc[/] back  [dim]q[/] quit",
            id="help_text_2",
        )
        yield LoadingIndicator(id="dl_loading")
        yield ProgressBar(id="dl_progress", show_percentage=True, show_eta=False)
        yield DataTable(id="downloads_table")
        yield Static(id="dl_status")
        yield Footer()

    def on_mount(self) -> None:
        self.query_one("#dl_loading", LoadingIndicator).display = False
        self.query_one("#dl_progress", ProgressBar).display = False
        table = self.query_one("#downloads_table", DataTable)
        table.add_columns("ID", "Type", "Name", "Status", "Size", "Progress")
        table.cursor_type = "row"
        table.zebra_stripes = True
        self.action_refresh()

    def _set_loading(self, visible: bool) -> None:
        self.query_one("#dl_loading", LoadingIndicator).display = visible

    # ------------------------------------------------------------------
    # Cursor movement
    # ------------------------------------------------------------------
    def action_cursor_down(self) -> None:
        self.query_one("#downloads_table", DataTable).action_cursor_down()

    def action_cursor_up(self) -> None:
        self.query_one("#downloads_table", DataTable).action_cursor_up()

    def action_page_down(self) -> None:
        table = self.query_one("#downloads_table", DataTable)
        if table.rows:
            table.move_cursor(row=min((table.cursor_row or 0) + 10, len(table.rows) - 1))

    def action_page_up(self) -> None:
        table = self.query_one("#downloads_table", DataTable)
        if table.rows:
            table.move_cursor(row=max((table.cursor_row or 0) - 10, 0))

    def action_top(self) -> None:
        table = self.query_one("#downloads_table", DataTable)
        if table.rows:
            table.move_cursor(row=0)

    def action_bottom(self) -> None:
        table = self.query_one("#downloads_table", DataTable)
        if table.rows:
            table.move_cursor(row=len(table.rows) - 1)

    # ------------------------------------------------------------------
    # Refresh
    # ------------------------------------------------------------------
    def action_refresh(self) -> None:
        self._set_loading(True)
        self.run_worker(self._worker_refresh, group="downloads", exclusive=True, thread=True)

    def _worker_refresh(self) -> None:
        try:
            all_items: list = []
            for item in self.client.list_usenet():
                item["_type"] = "usenet"
                all_items.append(item)
            for item in self.client.list_torrents():
                item["_type"] = "torrent"
                all_items.append(item)
            for item in self.client.list_web_downloads():
                item["_type"] = "web"
                all_items.append(item)
            self.app.call_from_thread(self._update_table, all_items)
        except Exception as exc:
            self.app.call_from_thread(lambda m=f"Error refreshing: {exc}": self.notify(m, severity="error"))
        finally:
            self.app.call_from_thread(self._set_loading, False)

    def _update_table(self, items: list) -> None:
        table = self.query_one("#downloads_table", DataTable)
        table.clear()
        self.current_items.clear()
        for item in items:
            self.current_items.append(item)
            progress = item.get("progress", 0) or 0
            table.add_row(
                str(item.get("id", "?")),
                str(item.get("_type", "?")),
                str(item.get("name", "Unnamed")),
                str(item.get("status", "unknown")),
                _human_size(item.get("size", 0)),
                f"{progress * 100:.1f}%",
            )
        status = self.query_one("#dl_status", Static)
        if status:
            status.update(f"Loaded {len(items)} downloads.")

    # ------------------------------------------------------------------
    # Download selected
    # ------------------------------------------------------------------
    def action_download_selected(self) -> None:
        table = self.query_one("#downloads_table", DataTable)
        if table.cursor_row is None or table.cursor_row >= len(self.current_items):
            self.notify("Select a row first.", severity="warning")
            return

        item = self.current_items[table.cursor_row]
        if str(item.get("status", "")).lower() not in ("completed", "complete"):
            self.notify("Download is not completed yet.", severity="warning")
            return

        _id = item.get("id")
        _type = item.get("_type", "usenet")
        name = item.get("name", "download")
        if not _id:
            return

        self._set_loading(True)
        self.query_one("#dl_progress", ProgressBar).display = True
        self.query_one("#dl_progress", ProgressBar).update(total=1, progress=0)

        self.run_worker(
            lambda: self._worker_download(_id, name, _type),
            group="downloads",
            exclusive=True,
            thread=True,
        )

    def _worker_download(self, _id: int, name: str, _type: str) -> None:
        try:
            if _type == "usenet":
                url = self.client.download_usenet(_id, zip_link=True)
            elif _type == "torrent":
                url = self.client.download_torrent(_id, zip_link=True)
            elif _type == "web":
                url = self.client.download_web(_id, zip_link=True)
            else:
                self.app.call_from_thread(lambda m=f"Unknown type: {_type}": self.notify(m, severity="error"))
                return
            if not url:
                self.app.call_from_thread(lambda: self.notify("No download URL returned.", severity="error"))
                return
            self._download_to_disk(url, name)
        except Exception as exc:
            self.app.call_from_thread(lambda m=str(exc): self.notify(f"Download failed: {m}", severity="error"))
        finally:
            self.app.call_from_thread(self._set_loading, False)
            self.app.call_from_thread(
                self.query_one("#dl_progress", ProgressBar).update, progress=1, total=1
            )
            self.app.call_from_thread(
                lambda: setattr(self.query_one("#dl_progress", ProgressBar), "display", False)
            )

    def _download_to_disk(self, url: str, name: str) -> None:
        import urllib.request

        self.download_dir.mkdir(parents=True, exist_ok=True)
        req = urllib.request.Request(url, headers={"User-Agent": "nzb-tui/0.1.0"})

        with urllib.request.urlopen(req, timeout=120) as response:
            cd = response.headers.get("Content-Disposition", "")
            real_name = _extract_filename(cd) or name or "download"
            safe_name = "".join(
                c if c.isalnum() or c in " ._-" else "_" for c in real_name
            ).strip(" .")
            if not safe_name:
                safe_name = "download"
            out_path = self.download_dir / safe_name

            total = int(response.headers.get("Content-Length", "0") or "0")
            self.app.call_from_thread(
                self.query_one("#dl_progress", ProgressBar).update,
                total=max(total, 1),
                progress=0,
            )

            downloaded = 0
            with open(out_path, "wb") as f:
                while True:
                    chunk = response.read(8192)
                    if not chunk:
                        break
                    f.write(chunk)
                    downloaded += len(chunk)
                    if total > 0:
                        self.app.call_from_thread(
                            self.query_one("#dl_progress", ProgressBar).advance,
                            len(chunk),
                        )

            size = out_path.stat().st_size
            self.app.call_from_thread(
                lambda: self._set_status(f"Saved {size:,} bytes to {out_path}")
            )

    def _set_status(self, msg: str) -> None:
        status = self.query_one("#dl_status", Static)
        if status:
            status.update(msg)

    # ------------------------------------------------------------------
    # Delete selected
    # ------------------------------------------------------------------
    def action_delete_selected(self) -> None:
        table = self.query_one("#downloads_table", DataTable)
        if table.cursor_row is None or table.cursor_row >= len(self.current_items):
            self.notify("Select a row first.", severity="warning")
            return

        item = self.current_items[table.cursor_row]
        _id = item.get("id")
        _type = item.get("_type", "usenet")
        if not _id:
            return

        self._set_loading(True)
        self.run_worker(
            lambda: self._worker_delete(_id, _type),
            group="downloads",
            exclusive=True,
            thread=True,
        )

    def _worker_delete(self, _id: int, _type: str) -> None:
        try:
            if _type == "usenet":
                self.client.delete_usenet(_id)
            elif _type == "torrent":
                self.client.delete_torrent(_id)
            elif _type == "web":
                self.client.delete_web_download(_id)
            else:
                self.app.call_from_thread(lambda m=f"Unknown type: {_type}": self.notify(m, severity="error"))
                return
            self.app.call_from_thread(lambda: self._set_status(f"Deleted {_type} ID {_id}"))
            self.app.call_from_thread(self.action_refresh)
        except Exception as exc:
            self.app.call_from_thread(lambda m=str(exc): self.notify(f"Delete failed: {m}", severity="error"))
        finally:
            self.app.call_from_thread(self._set_loading, False)
