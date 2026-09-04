"""Shared entity model for HA Landscape."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import Entity

from .const import DOMAIN, NAME, SIGNAL_EXPORT_UPDATED, VERSION
from .exporter import LandscapeExporter


class LandscapeEntity(Entity):
    """Base class for HA Landscape entities."""

    _attr_has_entity_name = True

    def __init__(self, entry: ConfigEntry, exporter: LandscapeExporter) -> None:
        """Initialize a HA Landscape entity."""
        self._entry = entry
        self.exporter = exporter
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=NAME,
            manufacturer="HA Landscape",
            model="Entity CSV Exporter",
            sw_version=VERSION,
            configuration_url=exporter.full_download_url,
        )

    async def async_added_to_hass(self) -> None:
        """Subscribe to export status changes."""
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass, SIGNAL_EXPORT_UPDATED, self.async_write_ha_state
            )
        )
