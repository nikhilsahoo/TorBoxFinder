"""Shared helpers for the NZB TUI."""

from typing import Optional


def _human_size(size_bytes: int) -> str:
    if size_bytes == 0:
        return "0 B"
    units = ["B", "KB", "MB", "GB", "TB"]
    idx = 0
    size = float(size_bytes)
    while size >= 1024 and idx < len(units) - 1:
        size /= 1024
        idx += 1
    return f"{size:.2f} {units[idx]}"


def _extract_filename(cd_header: str) -> Optional[str]:
    """Extract filename from a Content-Disposition header value."""
    if not cd_header:
        return None
    for part in cd_header.split(";"):
        part = part.strip()
        if part.lower().startswith("filename="):
            value = part[9:]
            if value.startswith('"') and value.endswith('"'):
                return value[1:-1]
            return value
    return None
