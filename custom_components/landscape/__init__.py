"""HA Landscape integration."""

from __future__ import annotations

from pathlib import Path

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers.service import async_register_admin_service

from .const import (
    CSV_FILENAME,
    DOMAIN,
    PLATFORMS,
    SERVICE_DELETE_CSV,
    SERVICE_EXPORT_CSV,
)
from .csv_writer import delete_csv
from .exporter import LandscapeExporter


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up HA Landscape from a config entry."""
    exporter = LandscapeExporter(hass)
    await exporter.async_initialize()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = exporter

    async def async_handle_export(_call: ServiceCall) -> None:
        """Handle a manual CSV export."""
        await exporter.async_export()

    async def async_handle_delete(_call: ServiceCall) -> None:
        """Delete the public CSV export."""
        await exporter.async_delete()

    async_register_admin_service(hass, DOMAIN, SERVICE_EXPORT_CSV, async_handle_export)
    async_register_admin_service(hass, DOMAIN, SERVICE_DELETE_CSV, async_handle_delete)

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_remove_entry(hass: HomeAssistant, _entry: ConfigEntry) -> None:
    """Remove a leftover public export when the integration is deleted."""
    path = Path(hass.config.path("www", CSV_FILENAME))
    await hass.async_add_executor_job(delete_csv, path)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a HA Landscape config entry."""
    if not await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        return False

    hass.services.async_remove(DOMAIN, SERVICE_EXPORT_CSV)
    hass.services.async_remove(DOMAIN, SERVICE_DELETE_CSV)

    domain_data = hass.data.get(DOMAIN, {})
    domain_data.pop(entry.entry_id, None)
    if not domain_data:
        hass.data.pop(DOMAIN, None)

    return True


def get_exporter(hass: HomeAssistant, entry: ConfigEntry) -> LandscapeExporter:
    """Return the exporter belonging to a config entry."""
    return hass.data[DOMAIN][entry.entry_id]
