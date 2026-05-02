"""Configuration management for TorBoxFinder."""

import os
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv


# Load .env from project root
PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")


class Config:
    """Simple configuration holder."""

    def __init__(self):
        self.nzb_api_key: Optional[str] = os.environ.get("NZB_API_KEY", "")
        self.torbox_api_key: Optional[str] = os.environ.get("TORBOX_API_KEY", "")
        self.download_dir: Path = Path(os.environ.get("DOWNLOAD_DIR", str(Path.home() / "Downloads")))

    def is_configured(self) -> bool:
        return bool(self.nzb_api_key and self.torbox_api_key)

    def save(self) -> None:
        """Save current config back to .env file."""
        env_path = PROJECT_ROOT / ".env"
        lines = []
        if env_path.exists():
            with env_path.open("r", encoding="utf-8") as f:
                lines = f.readlines()

        # Update or append keys
        def _update_or_append(lines: list, key: str, value: str) -> list:
            found = False
            for i, line in enumerate(lines):
                if line.startswith(f"{key}="):
                    lines[i] = f"{key}={value}\n"
                    found = True
                    break
            if not found:
                lines.append(f"{key}={value}\n")
            return lines

        lines = _update_or_append(lines, "NZB_API_KEY", self.nzb_api_key or "")
        lines = _update_or_append(lines, "TORBOX_API_KEY", self.torbox_api_key or "")
        lines = _update_or_append(lines, "DOWNLOAD_DIR", str(self.download_dir))

        with env_path.open("w", encoding="utf-8") as f:
            f.writelines(lines)

        # Also update environment for current process
        os.environ["NZB_API_KEY"] = self.nzb_api_key or ""
        os.environ["TORBOX_API_KEY"] = self.torbox_api_key or ""
