"""Buttons for HA Landscape."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import get_exporter
from .entity import LandscapeEntity
from .exporter import LandscapeExporter


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up HA Landscape buttons."""
    exporter = get_exporter(hass, entry)
    async_add_entities(
        [LandscapeExportButton(entry, exporter), LandscapeDeleteButton(entry, exporter)]
    )


class LandscapeExportButton(LandscapeEntity, ButtonEntity):
    """Create the complete entity inventory."""

    _attr_translation_key = "export_csv"
    _attr_icon = "mdi:file-delimited"

    def __init__(self, entry: ConfigEntry, exporter: LandscapeExporter) -> None:
        """Initialize the export button."""
        super().__init__(entry, exporter)
        self._attr_unique_id = f"{entry.entry_id}_export_csv"

    async def async_press(self) -> None:
        """Create a fresh CSV snapshot."""
        await self.exporter.async_export()


class LandscapeDeleteButton(LandscapeEntity, ButtonEntity):
    """Delete the public entity inventory."""

    _attr_translation_key = "delete_csv"
    _attr_icon = "mdi:file-remove"

    def __init__(self, entry: ConfigEntry, exporter: LandscapeExporter) -> None:
        """Initialize the delete button."""
        super().__init__(entry, exporter)
        self._attr_unique_id = f"{entry.entry_id}_delete_csv"

    @property
    def available(self) -> bool:
        """Only offer deletion while an export exists."""
        return self.exporter.status.file_available

    async def async_press(self) -> None:
        """Delete the published CSV snapshot."""
        await self.exporter.async_delete()
