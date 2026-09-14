"""Smoke test using actual Home Assistant registries and exposure APIs."""

from __future__ import annotations

import asyncio
import json

from homeassistant.components.homeassistant.exposed_entities import (
    DATA_EXPOSED_ENTITIES,
    ExposedEntities,
    async_expose_entity,
    async_should_expose,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers import (
    area_registry,
    device_registry,
    entity_registry,
    floor_registry,
)

from custom_components.landscape.assist import AssistOptimizer
from custom_components.landscape.assist_snapshot import collect_snapshot


def test_real_registry_round_trip(tmp_path) -> None:
    async def scenario():
        hass = HomeAssistant(str(tmp_path))
        await floor_registry.async_load(hass)
        await area_registry.async_load(hass)
        await device_registry.async_load(hass)
        await entity_registry.async_load(hass)
        exposure = ExposedEntities(hass)
        await exposure.async_initialize()
        hass.data[DATA_EXPOSED_ENTITIES] = exposure
        registry = entity_registry.async_get(hass)
        floor = floor_registry.async_get(hass).async_create("Obergeschoss", level=1)
        ground = floor_registry.async_get(hass).async_create("Erdgeschoss", level=0)
        area = area_registry.async_get(hass).async_create(
            "Schlafzimmer", floor_id=floor.floor_id
        )
        entry = registry.async_get_or_create(
            "light", "test", "ceiling",
            original_name="Decke", suggested_object_id="ceiling"
        )
        computed = getattr(entity_registry, "COMPUTED_NAME", None)
        aliases = [computed, "Deckenlampe"] if computed is not None else ["Deckenlampe"]
        registry.async_update_entity(entry.entity_id, aliases=aliases, area_id=area.id)
        hass.states.async_set(entry.entity_id, "off", {
            "friendly_name": "Schlafzimmer Decke",
            "supported_color_modes": ["brightness"],
            "access_token": "must-not-be-exported",
        })
        async_expose_entity(hass, "conversation", entry.entity_id, True)
        async_expose_entity(hass, "cloud.alexa", entry.entity_id, True)
        snapshot = collect_snapshot(hass)
        assert snapshot["entities"][0]["floor"] == "Obergeschoss"
        assert "must-not-be-exported" not in json.dumps(snapshot)
        manager = AssistOptimizer(hass, "test-entry")
        manager._data["snapshots"] = [snapshot]
        patch = {
            "schema_version": 1,
            "source_id": snapshot["source_id"],
            "changes": [{
                "entity_id": entry.entity_id,
                "name": {"old": "Decke", "new": "Deckenlicht"},
                "aliases": {"add": ["Licht an der Decke"]},
                "assist": {"exposed": False},
                "reason": "Vom Ambientelicht unterscheiden.",
            }],
            "area_changes": [{
                "area_id": area.id,
                "floor_id": {"old": floor.floor_id, "new": ground.floor_id},
                "reason": "Etage korrigieren.",
            }],
        }
        preview = await manager.async_preview(json.dumps(patch), "admin")
        report = await manager.async_apply(
            preview["preview_id"], [row["id"] for row in preview["operations"]], "admin"
        )
        assert report["status"] == "applied", report
        changed = registry.async_get(entry.entity_id)
        assert changed.id == entry.id
        assert changed.name == "Deckenlicht"
        assert list(changed.aliases) == [*aliases, "Licht an der Decke"]
        assert async_should_expose(hass, "conversation", entry.entity_id) is False
        assert async_should_expose(hass, "cloud.alexa", entry.entity_id) is True
        assert area_registry.async_get(hass).async_get_area(area.id).floor_id == ground.floor_id
        await manager.async_remove()
        await hass.async_stop(force=True)
    asyncio.run(scenario())
