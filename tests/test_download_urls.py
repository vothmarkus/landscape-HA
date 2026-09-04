"""Tests for the HA Landscape download URLs."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from homeassistant.helpers.network import NoURLAvailableError

import custom_components.landscape.exporter as exporter_module
from custom_components.landscape.exporter import LandscapeExporter


class _FakeConfig:
    """Minimal Home Assistant config used by the exporter constructor."""

    @staticmethod
    def path(*parts: str) -> str:
        """Resolve a path below a fake config directory."""
        return str(Path("/config").joinpath(*parts))


class _FakeHass:
    """Minimal Home Assistant instance used by URL-only tests."""

    config = _FakeConfig()


def test_full_download_url_uses_home_assistant_base_url(monkeypatch: Any) -> None:
    """The device and sensor expose a complete browser URL."""
    monkeypatch.setattr(
        exporter_module,
        "get_url",
        lambda *_args, **_kwargs: "https://ha.home/",
    )
    exporter = LandscapeExporter(_FakeHass())  # type: ignore[arg-type]

    exported_at = datetime(2026, 9, 4, 12, tzinfo=UTC)
    exporter.status.exported_at = exported_at

    assert exporter.full_download_url == "https://ha.home/local/ha_entitaeten.csv"
    assert exporter.full_versioned_download_url == (
        f"https://ha.home/local/ha_entitaeten.csv?v={int(exported_at.timestamp())}"
    )


def test_full_download_url_falls_back_to_relative_url(monkeypatch: Any) -> None:
    """The link remains usable if Home Assistant has no absolute URL."""

    def _raise_no_url(*_args: Any, **_kwargs: Any) -> str:
        raise NoURLAvailableError

    monkeypatch.setattr(exporter_module, "get_url", _raise_no_url)
    exporter = LandscapeExporter(_FakeHass())  # type: ignore[arg-type]

    assert exporter.full_download_url is None
    assert exporter.full_versioned_download_url == "/local/ha_entitaeten.csv"
