"""Entity inventory exporter for HA Landscape."""

from __future__ import annotations

import asyncio
import json
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from homeassistant.components import persistent_notification
from homeassistant.const import STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant, State
from homeassistant.helpers import (
    area_registry,
    device_registry,
    entity_registry,
    floor_registry,
    label_registry,
)
from homeassistant.helpers.dispatcher import async_dispatcher_send

from .const import CSV_FILENAME, SIGNAL_EXPORT_UPDATED
from .csv_writer import delete_csv, write_csv

CSV_FIELDS: tuple[str, ...] = (
    "entity_id",
    "friendly_name",
    "domain",
    "state",
    "available",
    "unit_of_measurement",
    "device_class",
    "state_class",
    "icon",
    "supported_features",
    "entity_category",
    "enabled",
    "disabled_by",
    "hidden_by",
    "entity_registry_id",
    "entity_registry_name",
    "original_name",
    "unique_id",
    "platform",
    "integration_domain",
    "integration_title",
    "config_entry_id",
    "config_subentry_id",
    "device_id",
    "device_config_entry_id",
    "device_config_subentry_id",
    "device_disabled_by",
    "device_name",
    "device_manufacturer",
    "device_model",
    "device_sw_version",
    "device_hw_version",
    "device_serial_number",
    "entity_area_id",
    "device_area_id",
    "effective_area_id",
    "area_name",
    "area_label_ids",
    "area_labels",
    "floor_id",
    "floor_name",
    "entity_label_ids",
    "entity_labels",
    "device_label_ids",
    "device_labels",
    "entity_aliases",
    "device_identifiers_json",
    "device_connections_json",
    "capabilities_json",
    "options_json",
    "last_changed",
    "last_updated",
    "attributes_json",
)

_SENSITIVE_KEYS = {
    "access_token",
    "api_key",
    "apikey",
    "auth_token",
    "authorization",
    "client_secret",
    "code",
    "credential",
    "credentials",
    "passcode",
    "passwd",
    "password",
    "pin",
    "private_key",
    "refresh_token",
    "secret",
    "token",
}
_SENSITIVE_QUERY_VALUE = re.compile(
    r"(?i)([?&](?:access_token|api_key|apikey|authsig|token)=)[^&#]*"
)


@dataclass(slots=True)
class ExportStatus:
    """Runtime status displayed by the status sensor."""

    file_available: bool = False
    exported_at: datetime | None = None
    entity_count: int | None = None
    file_size: int | None = None


class LandscapeExporter:
    """Create and manage the public entity inventory CSV."""

    def __init__(self, hass: HomeAssistant) -> None:
        """Initialize the exporter."""
        self.hass = hass
        self.path = Path(hass.config.path("www", CSV_FILENAME))
        self.status = ExportStatus()
        self._lock = asyncio.Lock()

    async def async_initialize(self) -> None:
        """Restore file availability and modification time after a restart."""
        file_info = await self.hass.async_add_executor_job(_file_info, self.path)
        if file_info is None:
            return

        modified_at, file_size = file_info
        self.status.file_available = True
        self.status.exported_at = modified_at
        self.status.file_size = file_size

    async def async_export(self) -> None:
        """Collect all entity data and publish a fresh CSV snapshot."""
        async with self._lock:
            rows = self._collect_rows()
            file_size = await self.hass.async_add_executor_job(
                write_csv, self.path, CSV_FIELDS, rows
            )

            self.status.file_available = True
            self.status.exported_at = datetime.now(UTC)
            self.status.entity_count = len(rows)
            self.status.file_size = file_size
            async_dispatcher_send(self.hass, SIGNAL_EXPORT_UPDATED)

            persistent_notification.async_create(
                self.hass,
                (
                    f"{len(rows)} Entitäten wurden exportiert. "
                    "[ha_entitaeten.csv herunterladen]"
                    f"({self.versioned_download_url}).\n\n"
                    "Die Datei liegt im öffentlichen `www`-Ordner und ist ohne "
                    "Home-Assistant-Anmeldung erreichbar. Bitte nach dem "
                    "Herunterladen über die Schaltfläche **CSV-Datei löschen** "
                    "entfernen."
                ),
                title="HA Landscape: CSV-Export fertig",
                notification_id="landscape_csv_export",
            )

    async def async_delete(self) -> None:
        """Delete the public CSV snapshot."""
        async with self._lock:
            deleted = await self.hass.async_add_executor_job(delete_csv, self.path)
            self.status.file_available = False
            self.status.file_size = None
            async_dispatcher_send(self.hass, SIGNAL_EXPORT_UPDATED)

            persistent_notification.async_create(
                self.hass,
                (
                    "Die öffentliche CSV-Datei wurde gelöscht."
                    if deleted
                    else "Es war keine öffentliche CSV-Datei vorhanden."
                ),
                title="HA Landscape",
                notification_id="landscape_csv_export",
            )

    def _collect_rows(self) -> list[dict[str, Any]]:
        """Build one deterministic snapshot from state and registry data."""
        entity_reg = entity_registry.async_get(self.hass)
        device_reg = device_registry.async_get(self.hass)
        area_reg = area_registry.async_get(self.hass)
        floor_reg = floor_registry.async_get(self.hass)
        label_reg = label_registry.async_get(self.hass)

        states = {state.entity_id: state for state in self.hass.states.async_all()}
        registry_entries = {
            entry.entity_id: entry for entry in entity_reg.entities.values()
        }
        entity_ids = sorted(states.keys() | registry_entries.keys())

        return [
            self._build_row(
                entity_id=entity_id,
                state=states.get(entity_id),
                entity_entry=registry_entries.get(entity_id),
                device_registry=device_reg,
                area_registry=area_reg,
                floor_registry=floor_reg,
                label_registry=label_reg,
            )
            for entity_id in entity_ids
        ]

    def _build_row(
        self,
        *,
        entity_id: str,
        state: State | None,
        entity_entry: Any | None,
        device_registry: Any,
        area_registry: Any,
        floor_registry: Any,
        label_registry: Any,
    ) -> dict[str, Any]:
        """Create a CSV row for one entity."""
        attributes = dict(state.attributes) if state is not None else {}
        device_id = _attr(entity_entry, "device_id")
        device_entry = device_registry.async_get(device_id) if device_id else None

        entity_area_id = _attr(entity_entry, "area_id")
        device_area_id = _attr(device_entry, "area_id")
        effective_area_id = entity_area_id or device_area_id
        area_entry = (
            area_registry.async_get_area(effective_area_id)
            if effective_area_id
            else None
        )
        floor_id = _attr(area_entry, "floor_id")
        floor_entry = floor_registry.async_get_floor(floor_id) if floor_id else None

        config_entry_id = _attr(entity_entry, "config_entry_id")
        config_entry = (
            self.hass.config_entries.async_get_entry(config_entry_id)
            if config_entry_id
            else None
        )
        platform = _attr(entity_entry, "platform")
        integration_domain = _attr(config_entry, "domain") or platform

        entity_label_ids = _string_set(_attr(entity_entry, "labels", ()))
        device_label_ids = _string_set(_attr(device_entry, "labels", ()))
        area_label_ids = _string_set(_attr(area_entry, "labels", ()))

        friendly_name = attributes.get("friendly_name")
        if friendly_name is None:
            friendly_name = (
                _attr(entity_entry, "name")
                or _attr(entity_entry, "original_name")
                or entity_id
            )

        enabled = entity_entry is None or _attr(entity_entry, "disabled_by") is None

        return {
            "entity_id": entity_id,
            "friendly_name": friendly_name,
            "domain": entity_id.partition(".")[0],
            "state": state.state if state is not None else "",
            "available": state is not None and state.state != STATE_UNAVAILABLE,
            "unit_of_measurement": attributes.get("unit_of_measurement")
            or _attr(entity_entry, "unit_of_measurement", ""),
            "device_class": attributes.get("device_class")
            or _attr(entity_entry, "device_class")
            or _attr(entity_entry, "original_device_class", ""),
            "state_class": attributes.get("state_class", ""),
            "icon": attributes.get("icon")
            or _attr(entity_entry, "icon")
            or _attr(entity_entry, "original_icon", ""),
            "supported_features": attributes.get("supported_features")
            if "supported_features" in attributes
            else _attr(entity_entry, "supported_features", ""),
            "entity_category": _enum_value(_attr(entity_entry, "entity_category")),
            "enabled": enabled,
            "disabled_by": _enum_value(_attr(entity_entry, "disabled_by")),
            "hidden_by": _enum_value(_attr(entity_entry, "hidden_by")),
            "entity_registry_id": _attr(entity_entry, "id", ""),
            "entity_registry_name": _attr(entity_entry, "name", ""),
            "original_name": _attr(entity_entry, "original_name", ""),
            "unique_id": _attr(entity_entry, "unique_id", ""),
            "platform": platform or "",
            "integration_domain": integration_domain or "",
            "integration_title": _attr(config_entry, "title", ""),
            "config_entry_id": config_entry_id or "",
            "config_subentry_id": _attr(entity_entry, "config_subentry_id", ""),
            "device_id": device_id or "",
            "device_config_entry_id": _attr(device_entry, "config_entry_id", ""),
            "device_config_subentry_id": _attr(device_entry, "config_subentry_id", ""),
            "device_disabled_by": _enum_value(_attr(device_entry, "disabled_by")),
            "device_name": _attr(device_entry, "name_by_user")
            or _attr(device_entry, "name", ""),
            "device_manufacturer": _attr(device_entry, "manufacturer", ""),
            "device_model": _attr(device_entry, "model", ""),
            "device_sw_version": _attr(device_entry, "sw_version", ""),
            "device_hw_version": _attr(device_entry, "hw_version", ""),
            "device_serial_number": _attr(device_entry, "serial_number", ""),
            "entity_area_id": entity_area_id or "",
            "device_area_id": device_area_id or "",
            "effective_area_id": effective_area_id or "",
            "area_name": _attr(area_entry, "name", ""),
            "area_label_ids": _join(area_label_ids),
            "area_labels": _join(_label_names(label_registry, area_label_ids)),
            "floor_id": floor_id or "",
            "floor_name": _attr(floor_entry, "name", ""),
            "entity_label_ids": _join(entity_label_ids),
            "entity_labels": _join(_label_names(label_registry, entity_label_ids)),
            "device_label_ids": _join(device_label_ids),
            "device_labels": _join(_label_names(label_registry, device_label_ids)),
            "entity_aliases": _join(_aliases(_attr(entity_entry, "aliases", ()))),
            "device_identifiers_json": _json(_attr(device_entry, "identifiers", ())),
            "device_connections_json": _json(_attr(device_entry, "connections", ())),
            "capabilities_json": _json(_attr(entity_entry, "capabilities", {})),
            "options_json": _json(_attr(entity_entry, "options", {})),
            "last_changed": state.last_changed.isoformat() if state else "",
            "last_updated": state.last_updated.isoformat() if state else "",
            "attributes_json": _json(_redact_sensitive(attributes)),
        }

    @property
    def download_url(self) -> str:
        """Return the relative browser URL of the public export."""
        return f"/local/{CSV_FILENAME}"

    @property
    def versioned_download_url(self) -> str:
        """Return a cache-busting browser URL for the latest export."""
        if self.status.exported_at is None:
            return self.download_url
        version = int(self.status.exported_at.timestamp())
        return f"{self.download_url}?v={version}"


def _attr(obj: Any | None, name: str, default: Any = None) -> Any:
    """Read an optional registry attribute."""
    if obj is None:
        return default
    return getattr(obj, name, default)


def _enum_value(value: Any) -> str:
    """Return a stable string for registry enum values."""
    if value is None:
        return ""
    return str(getattr(value, "value", value))


def _string_set(values: Iterable[Any] | None) -> tuple[str, ...]:
    """Normalize a registry collection to sorted strings."""
    if not values:
        return ()
    return tuple(sorted(str(value) for value in values))


def _aliases(values: Iterable[Any] | None) -> tuple[str, ...]:
    """Return explicit aliases and omit Home Assistant's computed sentinel."""
    if not values:
        return ()
    return tuple(sorted(value for value in values if isinstance(value, str)))


def _join(values: Iterable[str]) -> str:
    """Join a multi-value registry field for human-friendly CSV use."""
    return " | ".join(values)


def _label_names(label_registry: Any, label_ids: Iterable[str]) -> tuple[str, ...]:
    """Resolve label IDs without depending on private registry internals."""
    labels = getattr(label_registry, "labels", {})
    names = []
    for label_id in label_ids:
        entry = labels.get(label_id)
        names.append(str(getattr(entry, "name", label_id)))
    return tuple(sorted(names))


def _redact_sensitive(value: Any, key: str | None = None) -> Any:
    """Redact credentials while preserving automation-relevant attributes."""
    if key is not None and key.casefold() in _SENSITIVE_KEYS:
        return "<redacted>"

    if isinstance(value, Mapping):
        return {
            str(item_key): _redact_sensitive(item_value, str(item_key))
            for item_key, item_value in value.items()
        }
    if isinstance(value, (list, tuple, set, frozenset)):
        return [_redact_sensitive(item) for item in value]
    if isinstance(value, str) and "?" in value:
        return _SENSITIVE_QUERY_VALUE.sub(r"\1<redacted>", value)
    return value


def _json(value: Any) -> str:
    """Serialize Home Assistant values consistently and losslessly enough."""
    return json.dumps(
        _json_safe(value),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _json_safe(value: Any) -> Any:
    """Convert registry values that are not natively JSON serializable."""
    if isinstance(value, Mapping):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (set, frozenset)):
        converted = [_json_safe(item) for item in value]
        try:
            return sorted(converted, key=lambda item: json.dumps(item, sort_keys=True))
        except TypeError:
            return converted
    if isinstance(value, (tuple, list)):
        return [_json_safe(item) for item in value]
    if isinstance(value, datetime):
        return value.isoformat()
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def _file_info(path: Path) -> tuple[datetime, int] | None:
    """Return modification time and size for an existing export."""
    if not path.exists():
        return None
    stat = path.stat()
    return datetime.fromtimestamp(stat.st_mtime, tz=UTC), stat.st_size
