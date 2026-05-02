# TorBoxFinder

A terminal UI application for searching Usenet and Torrent content across multiple providers and managing downloads on [TorBox](https://torbox.app).

## Features

- **Dual Source Search**: Search both NZBFinder (Usenet) and TorBox's own search index (Torrents + Usenet)
- **Eager Fetch + Local Pagination**: All results fetched up front, paginated locally (no API calls on `n`/`N`)
- **Sorting & Filtering**: Sort by seeders, size, or age; filter cached-only results
- **Detail Pane**: Full title and metadata preview shown below the results table
- **Add to TorBox**: Add NZBs by upload, NZB links, or magnet links directly from search results
- **Download Management**: View all TorBox downloads (Usenet, Torrents, Web) with unified status
- **Local Downloads**: Download completed files directly to disk via `urllib`
- **Vim-style Keybindings**: `j`/`k` to navigate, `n`/`N` for pages, `gg`/`G` for top/bottom

## Providers

| Provider | Content | Add Method |
|----------|---------|------------|
| NZBFinder | Usenet (NZBs) | Fetch NZB bytes → upload to TorBox |
| TorBox Search | Torrents + Usenet | Magnet link / NZB link → direct add |

## Setup

```bash
# Clone and enter directory
git clone https://github.com/nikhilsahoo/TorBoxFinder.git
cd TorBoxFinder

# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Configure API keys
export NZB_API_KEY="your_nzbfinder_key"
export TORBOX_API_KEY="your_torbox_key"

# Run
python -m nzb_tui
```

## Configuration

Press `c` on the search screen to open the configuration panel, or create a `.env` file:

```bash
NZB_API_KEY=your_nzbfinder_api_key
TORBOX_API_KEY=your_torbox_api_key
DOWNLOAD_DIR=/home/user/Downloads
```

## Search Screen Controls

| Key | Action |
|-----|--------|
| `s` | Focus search input |
| `Enter` | Submit search |
| `j` / `k` | Move cursor down / up |
| `ctrl+d` / `ctrl+u` | Page down / up |
| `gg` / `G` | Jump to top / bottom |
| `n` / `N` | Next / previous page |
| `a` | Add selected result to TorBox |
| `c` | Open configuration |
| `t` | Show TorBox downloads |
| `q` / `Escape` | Quit / go back |

## Download Screen Controls

| Key | Action |
|-----|--------|
| `r` | Refresh download list |
| `d` | Download selected completed item |
| `x` / `Delete` | Delete selected download |
| `j` / `k` | Move cursor |
| `Escape` | Back to search |

## Architecture

```
nzb_tui/
├── app.py              # Main TUI app (SearchScreen, ConfigScreen, NZBTuiApp)
├── download_screen.py  # TorBox downloads monitor
├── torbox_client.py    # SDK wrapper for TorBox API
├── torbox_search.py    # TorBox search API client
├── nzbfinder.py        # NZBFinder Newznab XML client
├── nzb_parser.py       # Custom NZB XML parser
├── helpers.py           # Shared utilities
└── config.py           # .env-based config
```

## License

MIT
