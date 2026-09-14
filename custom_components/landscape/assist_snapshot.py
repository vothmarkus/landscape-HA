"""Collect minimal semantic context without exporting arbitrary state attributes."""

from __future__ import annotations

import io
import json
import math
import zipfile
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from homeassistant.components.homeassistant import exposed_entities
from homeassistant.core import HomeAssistant
from homeassistant.helpers import (
    area_registry,
    device_registry,
    entity_registry,
    floor_registry,
)

from .assist_schema import CHATGPT_INSTRUCTIONS, SCHEMA_VERSION, optimization_schema

ATTRIBUTE_KEYS = (
    "device_class",
    "unit_of_measurement",
    "state_class",
    "supported_features",
    "supported_color_modes",
    "min_temp",
    "max_temp",
    "min",
    "max",
    "step",
)
SAFE_STATES = {
    "on", "off", "unknown", "unavailable", "open", "closed", "opening", "closing",
    "locked", "unlocked", "locking", "unlocking", "idle", "playing", "paused",
    "heat", "cool", "auto", "heat_cool", "dry", "fan_only", "cleaning", "docked",
}


def safe_state(value: str | None) -> str | None:
    """Include basic control states and numbers, omitting arbitrary text."""
    if value is None or value in SAFE_STATES:
        return value
    try:
        if len(value) <= 32 and math.isfinite(float(value)):
            return value
    except ValueError:
        pass
    return None


def explicit_aliases(entry: Any) -> list[str]:
    """Exclude the computed-name sentinel from the exchange format."""
    return sorted(value for value in entry.aliases if isinstance(value, str))


def collect_snapshot(hass: HomeAssistant) -> dict[str, Any]:
    """Capture HA registries synchronously on the event loop."""
    entities = entity_registry.async_get(hass)
    devices = device_registry.async_get(hass)
    areas = area_registry.async_get(hass)
    floors = floor_registry.async_get(hass)
    states = {state.entity_id: state for state in hass.states.async_all()}
    siblings: dict[str, list[str]] = {}
    for entry in entities.entities.values():
        if entry.device_id:
            siblings.setdefault(entry.device_id, []).append(entry.entity_id)

    result = []
    for entity_id in sorted(states.keys() | entities.entities.keys()):
        # This public HA helper also initializes HA's default exposure preference.
        exposed = exposed_entities.async_should_expose(hass, "conversation", entity_id)
        entry = entities.async_get(entity_id)
        state = states.get(entity_id)
        attributes = state.attributes if state else {}
        device_id = entry.device_id if entry else None
        device = devices.async_get(device_id) if device_id else None
        area_id = entry.area_id if entry else None
        effective_area_id = area_id or (device.area_id if device else None)
        area = areas.async_get_area(effective_area_id) if effective_area_id else None
        floor = floors.async_get_floor(area.floor_id) if area and area.floor_id else None
        registry_name = entry.name if entry else None
        original_name = entry.original_name if entry else None
        name = registry_name
        if name is None:
            name = (
                getattr(entry, "original_name_unprefixed", None)
                or original_name
                or attributes.get("friendly_name")
                or entity_id
            )
        config = (
            hass.config_entries.async_get_entry(entry.config_entry_id)
            if entry and entry.config_entry_id
            else None
        )
        result.append(
            {
                "entity_id": entity_id,
                "registry_id": entry.id if entry else None,
                "name": name,
                "registry_name": registry_name,
                "friendly_name": attributes.get("friendly_name", name),
                "original_name": original_name,
                "domain": entity_id.partition(".")[0],
                "device_id": device_id,
                "device": {
                    "name": (device.name_by_user or device.name) if device else None,
                    "manufacturer": device.manufacturer if device else None,
                    "model": device.model if device else None,
                    "area_id": device.area_id if device else None,
                },
                "integration": config.domain if config else (entry.platform if entry else None),
                "area_id": area_id,
                "effective_area_id": effective_area_id,
                "area": area.name if area else None,
                "floor_id": floor.floor_id if floor else None,
                "floor": floor.name if floor else None,
                "aliases": explicit_aliases(entry) if entry else [],
                "has_automatic_alias": bool(
                    entry and any(not isinstance(alias, str) for alias in entry.aliases)
                ),
                "exposed_to_assist": exposed,
                "disabled": bool(entry and entry.disabled_by is not None),
                "hidden": bool(entry and entry.hidden_by is not None),
                "entity_category": str(entry.entity_category) if entry and entry.entity_category else None,
                "state": safe_state(state.state if state else None),
                "attributes": {key: attributes[key] for key in ATTRIBUTE_KEYS if key in attributes},
                "related_entity_ids": sorted(
                    item for item in siblings.get(device_id, []) if item != entity_id
                ),
            }
        )

    return {
        "schema_version": SCHEMA_VERSION,
        "source_id": uuid4().hex,
        "exported_at": datetime.now(UTC).isoformat(),
        "language": "de",
        "entities": result,
        "areas": [
            {"area_id": area.id, "name": area.name, "floor_id": area.floor_id}
            for area in sorted(areas.async_list_areas(), key=lambda item: item.id)
        ],
        "floors": [
            {"floor_id": floor.floor_id, "name": floor.name}
            for floor in sorted(floors.async_list_floors(), key=lambda item: item.floor_id)
        ],
    }


def build_archive(snapshot: dict[str, Any]) -> bytes:
    """Create the ZIP in an executor, never exposing a www download."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for filename, data in (
            ("landscape.json", snapshot),
            ("optimization_schema.json", optimization_schema()),
        ):
            archive.writestr(filename, json.dumps(data, ensure_ascii=False, indent=2))
        archive.writestr("CHATGPT_INSTRUCTIONS.md", CHATGPT_INSTRUCTIONS)
    return buffer.getvalue()
