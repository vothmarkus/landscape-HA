"""Constants for the HA Landscape integration."""

from __future__ import annotations

from homeassistant.const import Platform

DOMAIN = "landscape"
NAME = "HA Landscape"
VERSION = "0.1.1"

CSV_FILENAME = "ha_entitaeten.csv"
CSV_DELIMITER = ";"
CSV_ENCODING = "utf-8-sig"

SERVICE_EXPORT_CSV = "export_csv"
SERVICE_DELETE_CSV = "delete_csv"

PLATFORMS = [Platform.BUTTON, Platform.SENSOR]

SIGNAL_EXPORT_UPDATED = f"{DOMAIN}_export_updated"
