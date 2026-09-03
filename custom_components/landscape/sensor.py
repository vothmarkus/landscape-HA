"""Status sensor for HA Landscape."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
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
    """Set up the HA Landscape status sensor."""
    async_add_entities([LandscapeExportStatusSensor(entry, get_exporter(hass, entry))])


class LandscapeExportStatusSensor(LandscapeEntity, SensorEntity):
    """Show timestamp and details of the latest CSV snapshot."""

    _attr_translation_key = "last_export"
    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_icon = "mdi:file-check"

    def __init__(self, entry: ConfigEntry, exporter: LandscapeExporter) -> None:
        """Initialize the status sensor."""
        super().__init__(entry, exporter)
        self._attr_unique_id = f"{entry.entry_id}_last_export"

    @property
    def native_value(self) -> datetime | None:
        """Return the timestamp of the latest export."""
        return self.exporter.status.exported_at

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return export metadata useful in dashboards and automations."""
        return {
            "file_available": self.exporter.status.file_available,
            "entity_count": self.exporter.status.entity_count,
            "file_size_bytes": self.exporter.status.file_size,
            "file_path": "/config/www/ha_entitaeten.csv",
            "download_url": self.exporter.download_url,
            "versioned_download_url": self.exporter.versioned_download_url,
        }
