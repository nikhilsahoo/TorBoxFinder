"""Main TUI application for TorBoxFinder."""

import datetime
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Optional

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal
from textual.reactive import reactive
from textual.screen import Screen
from textual.widgets import (
    Button,
    Checkbox,
    DataTable,
    Footer,
    Header,
    Input,
    Label,
    LoadingIndicator,
    Select,
    Static,
)
from textual.worker import Worker

from torboxfinder.config import Config
from torboxfinder.download_screen import DownloadScreen
from torboxfinder.helpers import _human_size, _extract_filename
from torboxfinder.nzbfinder import NZBFinderClient, NZBFinderError
from torboxfinder.nzb_parser import get_subject
from torboxfinder.torbox_client import TorBoxClient
from torboxfinder.torbox_search import TorBoxSearchClient, TorBoxSearchError


# ---------------------------------------------------------------------------
# ConfigScreen
# ---------------------------------------------------------------------------
class ConfigScreen(Screen):
    """Modal screen to configure API keys."""

    BINDINGS = [
        Binding("escape", "dismiss", "Close", priority=True, show=False),
        Binding("ctrl+s", "save", "Save", show=False),
    ]

    def __init__(self, config: Config) -> None:
        self.cfg = config
        super().__init__()

    def compose(self) -> ComposeResult:
        yield Static("Configuration", classes="title")
        yield Label("NZBFinder API Key:")
        yield Input(
            value=self.cfg.nzb_api_key or "",
            password=True,
            id="nzb_key",
        )
        yield Label("TorBox API Key:")
        yield Input(
            value=self.cfg.torbox_api_key or "",
            password=True,
            id="torbox_key",
        )
        yield Label("Download Directory:")
        yield Input(
            value=str(self.cfg.download_dir),
            id="download_dir",
        )
        yield Horizontal(
            Button("Save", id="save_btn", variant="primary"),
            Button("Cancel", id="cancel_btn"),
            classes="buttons",
        )
        yield Static(id="status_msg")

    def action_save(self) -> None:
        self._do_save()

    def _do_save(self) -> None:
        nzb = self.query_one("#nzb_key", Input).value.strip()
        tor = self.query_one("#torbox_key", Input).value.strip()
        ddir = self.query_one("#download_dir", Input).value.strip()

        self.cfg.nzb_api_key = nzb
        self.cfg.torbox_api_key = tor
        if ddir:
            self.cfg.download_dir = Path(ddir)
        self.cfg.save()

        self.query_one("#status_msg", Static).update(
            "[green]Configuration saved.[/]"
        )

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "save_btn":
            self._do_save()
        elif event.button.id == "cancel_btn":
            self.dismiss()


# ---------------------------------------------------------------------------
# SearchScreen (main)
# ---------------------------------------------------------------------------
class SearchScreen(Screen):
    """Main search screen supporting NZBFinder and TorBox search."""

    BINDINGS = [
        Binding("j", "cursor_down", "Down", show=False),
        Binding("k", "cursor_up", "Up", show=False),
        Binding("ctrl+d", "page_down", "PgDn", show=False),
        Binding("ctrl+u", "page_up", "PgUp", show=False),
        Binding("g,g", "top", "Top", show=False),
        Binding("G", "bottom", "Bottom", show=False),
        Binding("n", "next_page", "Next Page", show=False),
        Binding("N", "prev_page", "Prev Page", show=False),
        Binding("c", "config", "Config", show=False),
        Binding("s", "focus_search", "Search", show=False),
        Binding("a", "add_to_torbox", "Add to TorBox", show=False),
        Binding("t", "show_downloads", "Downloads", show=False),
        Binding("q", "app.quit", "Quit", show=False),
        Binding("escape", "escape_search", "Back/Quit", priority=True, show=False),
    ]

    # Reactive state driven from UI widgets; actual data lives in instance attrs
    search_results = reactive(list)
    _provider = reactive("both")
    _search_type = reactive("all")

    def __init__(self, config: Config) -> None:
        self.cfg = config
        self.nzb_client: Optional[NZBFinderClient] = None
        self.torbox_client: Optional[TorBoxClient] = None
        self.torbox_search_client: Optional[TorBoxSearchClient] = None
        self._init_clients()

        # Search / pagination
        self._search_query: str = ""
        self._items_per_page: int = 50
        self._current_page: int = 0
        self._eager_fetch_limit: int = 500

        # Filter / sort
        self._sort_key: str = "age"      # "age" | "seeders" | "size"
        self._sort_desc: bool = True
        self._title_max_len: int = 45      # dynamic; recalculated on mount/resize

        # Result storage
        self._all_results: list = []
        self._filtered_results: list = []

        super().__init__()

    def _init_clients(self) -> None:
        if self.cfg.nzb_api_key:
            self.nzb_client = NZBFinderClient(self.cfg.nzb_api_key)
        if self.cfg.torbox_api_key:
            self.torbox_client = TorBoxClient(self.cfg.torbox_api_key)
            self.torbox_search_client = TorBoxSearchClient(self.cfg.torbox_api_key)

    def compose(self) -> ComposeResult:
        yield Header()
        yield Static(
            "[b]Search[/b] "
            "[dim]j/k[/] move  [dim]ctrl+d/ctrl+u[/] page  [dim]gg/G[/] top/bottom  [dim]n/N[/] next/prev",
            id="help_text_1",
        )
        yield Static(
            "[dim]s[/] search  [dim]a[/] add  [dim]t[/] downloads  [dim]c[/] config  [dim]q[/] quit",
            id="help_text_2",
        )
        # Provider / type filters
        yield Horizontal(
            Select(
                [("Both", "both"), ("NZBFinder", "nzbfinder"), ("TorBox", "torbox")],
                value="both",
                id="provider_select",
                allow_blank=False,
            ),
            Select(
                [("All", "all"), ("Usenet", "usenet"), ("Torrents", "torrents")],
                value="all",
                id="type_select",
                allow_blank=False,
            ),
            classes="filters_bar",
        )
        yield Horizontal(
            Input(placeholder="Enter search query...", id="search_input"),
            Button("Search", id="search_btn", variant="primary"),
            classes="search_bar",
        )
        # Sort / extra controls
        yield Horizontal(
            Select(
                [("Newest First", "age"), ("Most Seeders", "seeders"), ("Largest Size", "size")],
                value="age",
                id="sort_select",
                allow_blank=False,
            ),
            Button("↓", id="sort_dir_btn"),
            Checkbox("Cached only", id="cached_only"),
            classes="controls_bar",
        )
        yield LoadingIndicator(id="search_loading")
        yield DataTable(id="results_table")
        yield Static(id="detail_pane")
        yield Static(id="pagination_status")
        yield Footer()

    def on_mount(self) -> None:
        self.query_one("#search_loading", LoadingIndicator).display = False
        table = self.query_one("#results_table", DataTable)
        # No fixed widths — we calculate per-row truncation dynamically
        table.add_column("Title")
        table.add_column("Size")
        table.add_column("Age")
        table.add_column("Src")
        table.add_column("Type")
        table.add_column("Extra")
        table.cursor_type = "row"
        table.zebra_stripes = True
        self._title_max_len = self._calc_title_max_len()
        self.query_one("#search_input", Input).focus()

    def on_resize(self, event) -> None:
        # Recalculate title column width when terminal resizes
        self._title_max_len = self._calc_title_max_len()
        self._refresh_table()

    def _calc_title_max_len(self) -> int:
        """Compute how many characters the Title column can hold."""
        term_w = getattr(self, "size", None)
        if term_w is not None:
            term_w = term_w.width if hasattr(term_w, "width") else 80
        else:
            term_w = 80

        # Minimum reasonable title width
        MIN_TITLE = 20

        # Fixed column visual widths (Size ~10, Age ~7, Src ~8, Extra ~12)
        # plus internal borders (~3) and padding (~4)  
        reserved = 10 + 7 + 8 + 12 + 3 + 4  # ≈ 44
        available = max(term_w - reserved, MIN_TITLE)
        return available

    def on_data_table_row_highlighted(self, event) -> None:
        if event.data_table.id == "results_table":
            cursor = getattr(event, "cursor_row", None)
            if cursor is not None:
                self._update_detail_pane(cursor)

    def _update_detail_pane(self, row_idx: int) -> None:
        pane = self.query_one("#detail_pane", Static)
        if not self.search_results or row_idx is None or row_idx >= len(self.search_results):
            pane.update("")
            return
        item = self.search_results[row_idx]
        lines = [f"[b]Title:[/b] {item.get('title', 'Unnamed')}"]
        if item.get("magnet"):
            lines.append(f"[dim]Magnet:[/dim] {item.get('magnet', '')[:80]}...")
        if item.get("nzb"):
            lines.append(f"[dim]NZB:[/dim] {item.get('nzb', '')[:80]}...")
        lines.append(
            f"[dim]Size:[/dim] {_human_size(item.get('size', 0))}   "
            f"[dim]Age:[/dim] {_human_age(item)}   "
            f"[dim]Source:[/dim] {item.get('_source', '?')}   "
            f"[dim]Type:[/dim] {item.get('_kind', '?')}"
        )
        pane.update("\n".join(lines))

    def on_checkbox_changed(self, event) -> None:
        if event.checkbox.id == "cached_only":
            self._apply_filters()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "search_btn":
            self._current_page = 0
            self._do_search()
        elif event.button.id == "sort_dir_btn":
            btn = self.query_one("#sort_dir_btn", Button)
            if btn.label == "↓":
                btn.label = "↑"
                self._sort_desc = False
            else:
                btn.label = "↓"
                self._sort_desc = True
            self._apply_filters()

    def on_select_changed(self, event: Select.Changed) -> None:
        if event.select.id == "provider_select":
            self._provider = str(event.value) if event.value else "both"
        elif event.select.id == "type_select":
            self._search_type = str(event.value) if event.value else "all"
        elif event.select.id == "sort_select":
            self._sort_key = str(event.value) if event.value else "seeders"
            self._apply_filters()

    def watch__provider(self, value: str) -> None:
        self._all_results.clear()
        self._filtered_results.clear()
        self.search_results.clear()
        self._refresh_table()

    def watch__search_type(self, value: str) -> None:
        self._all_results.clear()
        self._filtered_results.clear()
        self.search_results.clear()
        self._refresh_table()

    def _set_loading(self, visible: bool) -> None:
        self.query_one("#search_loading", LoadingIndicator).display = visible

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------
    def action_escape_search(self) -> None:
        table = self.query_one("#results_table", DataTable)
        if table.has_focus:
            self.query_one("#search_input", Input).focus()
        else:
            self.app.exit()

    def action_cursor_down(self) -> None:
        self.query_one("#results_table", DataTable).action_cursor_down()

    def action_cursor_up(self) -> None:
        self.query_one("#results_table", DataTable).action_cursor_up()

    def action_page_down(self) -> None:
        table = self.query_one("#results_table", DataTable)
        if table.rows:
            table.move_cursor(row=min((table.cursor_row or 0) + 10, len(table.rows) - 1))

    def action_page_up(self) -> None:
        table = self.query_one("#results_table", DataTable)
        if table.rows:
            table.move_cursor(row=max((table.cursor_row or 0) - 10, 0))

    def action_top(self) -> None:
        table = self.query_one("#results_table", DataTable)
        if table.rows:
            table.move_cursor(row=0)

    def action_bottom(self) -> None:
        table = self.query_one("#results_table", DataTable)
        if table.rows:
            table.move_cursor(row=len(table.rows) - 1)

    def action_next_page(self) -> None:
        if not self._filtered_results:
            return
        max_page = max(0, (len(self._filtered_results) - 1) // self._items_per_page)
        if self._current_page >= max_page:
            return
        self._current_page += 1
        self._refresh_table()

    def action_prev_page(self) -> None:
        if not self._filtered_results:
            return
        if self._current_page <= 0:
            return
        self._current_page -= 1
        self._refresh_table()

    def action_focus_search(self) -> None:
        self.query_one("#search_input", Input).focus()

    def action_config(self) -> None:
        def on_config_changed(_: ConfigScreen) -> None:
            self.cfg = Config()
            self._init_clients()

        self.app.push_screen(ConfigScreen(self.cfg), on_config_changed)

    def action_show_downloads(self) -> None:
        if not self.torbox_client:
            self.notify(
                "TorBox not configured. Press [c] to set keys.", severity="error"
            )
            return
        self.app.push_screen(
            DownloadScreen(self.torbox_client, self.cfg.download_dir)
        )

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id == "search_input":
            self._current_page = 0
            self._do_search()

    # ------------------------------------------------------------------
    # Search logic
    # ------------------------------------------------------------------
    def _do_search(self) -> None:
        query = self.query_one("#search_input", Input).value.strip()
        if not query:
            self.notify("Enter a search query.", severity="warning")
            return

        provider = self._provider
        search_type = self._search_type

        # Validate configured clients
        if provider in ("nzbfinder", "both") and not self.nzb_client:
            self.notify(
                "NZBFinder not configured. Press [c] to set keys.", severity="error"
            )
            if provider == "nzbfinder":
                return
        if provider in ("torbox", "both") and not self.torbox_search_client:
            self.notify(
                "TorBox not configured. Press [c] to set keys.", severity="error"
            )
            if provider == "torbox":
                return

        self._search_query = query
        self._set_loading(True)
        self._all_results.clear()
        self._filtered_results.clear()

        # Build list of worker lambdas
        workers = []
        if provider in ("nzbfinder", "both") and self.nzb_client:
            if search_type in ("all", "usenet"):
                workers.append(lambda: self._worker_search_nzbfinder(query))
        if provider in ("torbox", "both") and self.torbox_search_client:
            if search_type in ("all", "torrents"):
                workers.append(lambda: self._worker_search_torbox(query, "torrents"))
            if search_type in ("all", "usenet"):
                workers.append(lambda: self._worker_search_torbox(query, "usenet"))

        if not workers:
            self._set_loading(False)
            self.notify("No search targets configured.", severity="warning")
            return

        # Run all workers and accumulate results
        self.run_worker(
            lambda: self._multi_search(workers),
            group="search",
            exclusive=True,
            thread=True,
        )

    def _multi_search(self, workers: list) -> None:
        errors = []
        for worker in workers:
            try:
                results = worker()
                self._all_results.extend(results)
            except Exception as exc:
                errors.append(str(exc))
        self.app.call_from_thread(self._apply_filters)
        if errors:
            msg = f"Search errors: {'; '.join(errors[:3])}"
            self.app.call_from_thread(lambda m=msg: self.notify(m, severity="error"))
        self.app.call_from_thread(self._set_loading, False)

    def _worker_search_nzbfinder(self, query: str) -> list:
        """Eagerly fetch NZBFinder results up to limit, normalizing keys."""
        all_nzb = []
        offset = 0
        while len(all_nzb) < self._eager_fetch_limit:
            results = self.nzb_client.search(
                query, limit=self._items_per_page, offset=offset
            )
            if not results:
                break
            all_nzb.extend(_normalize_nzbfinder(r) for r in results)
            if len(results) < self._items_per_page:
                break
            if self.nzb_client.last_total is not None and offset >= self.nzb_client.last_total:
                break
            offset += self._items_per_page
        return all_nzb

    def _worker_search_torbox(self, query: str, kind: str) -> list:
        if kind == "torrents":
            return self.torbox_search_client.search_torrents(query)
        return self.torbox_search_client.search_usenet(query)

    # ------------------------------------------------------------------
    # Filtering / Sorting / Pagination
    # ------------------------------------------------------------------
    def _apply_filters(self) -> None:
        """Apply cached-only filter, sort, then paginate."""
        cached_only = self.query_one("#cached_only", Checkbox).value
        sort_key = getattr(self, "_sort_key", "seeders")
        sort_desc = getattr(self, "_sort_desc", True)

        filtered = list(self._all_results)

        # Cached-only filter
        if cached_only:
            filtered = [r for r in filtered if r.get("cached")]

        # Sort
        def _sort_key_fn(item):
            if sort_key == "seeders":
                return int(item.get("seeders", 0) or 0)
            if sort_key == "size":
                return int(item.get("size", 0) or 0)
            if sort_key == "age":
                # younger first when descending
                return -int(item.get("age", 0) or 0)
            return 0

        filtered.sort(key=_sort_key_fn, reverse=sort_desc)

        self._filtered_results = filtered
        self._refresh_table()

    def _refresh_table(self) -> None:
        table = self.query_one("#results_table", DataTable)
        table.clear()
        self.search_results.clear()

        start = self._current_page * self._items_per_page
        end = start + self._items_per_page
        page_items = self._filtered_results[start:end]

        for item in page_items:
            self.search_results.append(item)
            source = item.get("_source", "nzbfinder")
            source = "NZB" if source == "nzbfinder" else "TB"
            kind = item.get("_kind", "usenet")
            extra = ""
            if kind == "usenet":
                extra = "U"
            elif kind == "torrents":
                extra = f"T S{item.get('seeders', 0)}"
                if item.get("cached"):
                    extra += " C"
            table.add_row(
                _trunc_title(item.get("title", "Unnamed"), self._title_max_len),
                _human_size(item.get("size", 0)),
                _human_age(item),
                source,
                kind[:1].upper() if kind else "?",
                extra,
            )

        self._show_pagination_status()

        if self.search_results:
            table.focus()

    def _show_pagination_status(self) -> None:
        total = len(self._filtered_results)
        max_page = max(0, (total - 1) // self._items_per_page) if total else 0
        current = self._current_page + 1
        start = self._current_page * self._items_per_page + 1
        end = min((self._current_page + 1) * self._items_per_page, total)

        msg = f"Page {current}/{max_page + 1} | Showing {start}-{end} of {total}"
        status = self.query_one("#pagination_status", Static)
        if status:
            status.update(msg)

    # ------------------------------------------------------------------
    # Add to TorBox
    # ------------------------------------------------------------------
    def action_add_to_torbox(self) -> None:
        if not self.torbox_client:
            self.notify(
                "TorBox not configured. Press [c] to set keys.", severity="error"
            )
            return
        table = self.query_one("#results_table", DataTable)
        if table.cursor_row is None or table.cursor_row >= len(self.search_results):
            self.notify("Select a result first.", severity="warning")
            return

        item = self.search_results[table.cursor_row]
        self._set_loading(True)
        self.run_worker(
            lambda: self._do_add_worker(item),
            group="search",
            exclusive=True,
            thread=True,
        )

    def _do_add_worker(self, item: dict) -> None:
        source = item.get("_source", "nzbfinder")
        kind = item.get("_kind", "usenet")
        title = item.get("title", "Unnamed")

        if source == "nzbfinder":
            nzb_url = item.get("link")
            nzb_id = item.get("id") or item.get("guid", "")
            if not nzb_url and not nzb_id:
                self.app.call_from_thread(
                    lambda: self.notify("No NZB link available for this item.", severity="error")
                )
                self.app.call_from_thread(self._set_loading, False)
                return

            self.app.call_from_thread(self.notify, f"Fetching NZB for {title[:50]}...")
            try:
                if nzb_url:
                    nzb_bytes = self._fetch_url(nzb_url)
                else:
                    nzb_bytes = self.nzb_client.download_nzb(nzb_id)
            except Exception as exc:
                self.app.call_from_thread(
                    lambda m=str(exc): self.notify(f"Failed to fetch NZB: {m}", severity="error")
                )
                self.app.call_from_thread(self._set_loading, False)
                return

            self.app.call_from_thread(
                self.notify, f"Adding to TorBox: {title[:50]}..."
            )
            try:
                nzb_name = get_subject(nzb_bytes) or title
                resp = self.torbox_client.add_usenet(file=nzb_bytes, name=nzb_name)
                if resp.get("success"):
                    self.app.call_from_thread(
                        self.notify,
                        f"Added successfully! ID: {resp.get('data', {}).get('id', '?')}"
                    )
                else:
                    err = resp.get("error", "Unknown error")
                    detail = resp.get("detail", "")
                    msg = f"{err}: {detail}" if detail else err
                    self.app.call_from_thread(lambda m=msg: self.notify(f"TorBox error: {m}", severity="error"))
            except Exception as exc:
                self.app.call_from_thread(
                    lambda m=str(exc): self.notify(f"Add failed: {m}", severity="error")
                )
            finally:
                self.app.call_from_thread(self._set_loading, False)

        elif source == "torbox" and kind == "usenet":
            nzb_url = item.get("nzb", "")
            if not nzb_url:
                self.app.call_from_thread(
                    lambda: self.notify("No NZB link available for this item.", severity="error")
                )
                self.app.call_from_thread(self._set_loading, False)
                return
            self.app.call_from_thread(
                self.notify, f"Adding NZB link to TorBox: {title[:50]}..."
            )
            try:
                resp = self.torbox_client.add_usenet_link(nzb_url, name=title)
                if resp.get("success"):
                    self.app.call_from_thread(
                        self.notify,
                        f"Added successfully! ID: {resp.get('data', {}).get('id', '?')}"
                    )
                else:
                    err = resp.get("error", "Unknown error")
                    detail = resp.get("detail", "")
                    msg = f"{err}: {detail}" if detail else err
                    self.app.call_from_thread(lambda m=msg: self.notify(f"TorBox error: {m}", severity="error"))
            except Exception as exc:
                self.app.call_from_thread(
                    lambda m=str(exc): self.notify(f"Add failed: {m}", severity="error")
                )
            finally:
                self.app.call_from_thread(self._set_loading, False)

        elif source == "torbox" and kind == "torrents":
            magnet = item.get("magnet", "")
            if not magnet:
                self.app.call_from_thread(
                    lambda: self.notify("No magnet link available for this item.", severity="error")
                )
                self.app.call_from_thread(self._set_loading, False)
                return
            self.app.call_from_thread(
                self.notify, f"Adding magnet to TorBox: {title[:50]}..."
            )
            try:
                resp = self.torbox_client.add_torrent_magnet(magnet, name=title)
                if resp.get("success"):
                    self.app.call_from_thread(
                        self.notify,
                        f"Added successfully! ID: {resp.get('data', {}).get('id', '?')}"
                    )
                else:
                    err = resp.get("error", "Unknown error")
                    detail = resp.get("detail", "")
                    msg = f"{err}: {detail}" if detail else err
                    self.app.call_from_thread(lambda m=msg: self.notify(f"TorBox error: {m}", severity="error"))
            except Exception as exc:
                self.app.call_from_thread(
                    lambda m=str(exc): self.notify(f"Add failed: {m}", severity="error")
                )
            finally:
                self.app.call_from_thread(self._set_loading, False)

    def _fetch_url(self, url: str) -> bytes:
        """Fetch raw bytes from a URL."""
        import requests
        session = getattr(self, "nzb_client", None)
        if session is not None:
            session = session.session
        else:
            session = requests.Session()
        resp = session.get(url, timeout=60)
        resp.raise_for_status()
        return resp.content


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------
class NZBTuiApp(App):
    """Root Textual application."""

    CSS_PATH = "app.css"
    SCREENS = {}

    def __init__(self) -> None:
        self.config = Config()
        super().__init__()

    def on_mount(self) -> None:
        self.push_screen(SearchScreen(self.config))


def _human_age(item: dict) -> str:
    raw = item.get("date") or item.get("pubDate") or item.get("published")
    if not raw:
        age_days = item.get("age")
        if isinstance(age_days, int) and age_days > 0:
            if age_days < 30:
                return f"{age_days}d ago"
            months = age_days // 30
            if months < 12:
                return f"{months}mo ago"
            years = age_days // 365
            return f"{years}y ago"
        return "?"
    try:
        dt = parsedate_to_datetime(raw)
        now = datetime.datetime.now(datetime.timezone.utc)
        delta = now - dt
        total_seconds = int(delta.total_seconds())
        if total_seconds < 60:
            return f"{total_seconds}s ago"
        minutes = total_seconds // 60
        if minutes < 60:
            return f"{minutes}m ago"
        hours = minutes // 60
        if hours < 24:
            return f"{hours}h ago"
        days = hours // 24
        if days < 30:
            return f"{days}d ago"
        months = days // 30
        if months < 12:
            return f"{months}mo ago"
        years = days // 365
        return f"{years}y ago"
    except Exception:
        return "?"


def _trunc_title(title: str, max_len: int = 30) -> str:
    if len(title) <= max_len:
        return title
    return title[:max_len - 1] + "…"


def _normalize_nzbfinder(item: dict) -> dict:
    """Normalize NZBFinder result to match TorBox result keys for unified sorting."""
    from email.utils import parsedate_to_datetime
    import datetime

    # Compute age in days from pubDate
    age_days = 0
    pub_date = item.get("pubDate") or item.get("date") or item.get("published")
    if pub_date:
        try:
            dt = parsedate_to_datetime(pub_date)
            now = datetime.datetime.now(datetime.timezone.utc)
            age_days = max(0, (now - dt).days)
        except Exception:
            age_days = 0

    return {
        "_source": "nzbfinder",
        "_kind": "usenet",
        "title": item.get("title", "Unnamed"),
        "size": int(item.get("size") or 0),
        "age": age_days,
        "seeders": 0,
        "peers": 0,
        "cached": False,
        "id": item.get("id") or item.get("guid", ""),
        "link": item.get("link", ""),
        "guid": item.get("guid", ""),
        "category": item.get("category", ""),
    }


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------
def main() -> None:
    app = NZBTuiApp()
    app.run()


if __name__ == "__main__":
    main()
