"""Simple NZB file parser using xml.etree.ElementTree (stdlib)."""

import xml.etree.ElementTree as ET
from typing import Optional


class NZBFile:
    """Minimal NZB file wrapper."""

    def __init__(
        self,
        subject: str = "",
        poster: str = "",
        date: str = "",
        groups: list = None,
        segments: list = None,
    ):
        self.subject = subject
        self.poster = poster
        self.date = date
        self.groups = groups or []
        self.segments = segments or []


def parse_nzb(nzb_bytes: bytes) -> list:
    """Parse NZB bytes into a list of NZBFile objects."""
    root = ET.fromstring(nzb_bytes)
    files = []
    for file_el in root.findall(".//file"):
        files.append(
            NZBFile(
                subject=file_el.get("subject", ""),
                poster=file_el.get("poster", ""),
                date=file_el.get("date", ""),
            )
        )
    return files


def get_subject(nzb_bytes: bytes) -> Optional[str]:
    """Return the subject of the first <file> element in an NZB."""
    files = parse_nzb(nzb_bytes)
    return files[0].subject if files else None
