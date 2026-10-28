"""File browser transactions share the YAML workspace's lock and HA checks."""

from __future__ import annotations

from typing import ClassVar

from .browser_files import BrowserFiles
from .configuration import ConfigurationWorkspace


class BrowserWorkspace(ConfigurationWorkspace):
    """Use the existing reviewed, recoverable import lifecycle for all files."""

    preview_validation: ClassVar[dict[str, str]] = {
        "files": "passed",
        "home_assistant": "pending_apply",
    }

    def __init__(self, hass, configuration: ConfigurationWorkspace) -> None:
        super().__init__(hass)
        self.files = BrowserFiles(hass.config.config_dir)
        self._lock = configuration._lock
        self._tasks = configuration._tasks
