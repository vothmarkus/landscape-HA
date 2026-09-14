"""Exercise authorization boundaries, persistence and failed registry writes."""

from __future__ import annotations

import asyncio
import copy
import json
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from homeassistant.exceptions import Unauthorized

import custom_components.landscape.assist as assist_module
from custom_components.landscape.assist import AssistOptimizer
from custom_components.landscape.assist_api import websocket_assist
from custom_components.landscape.assist_schema import PatchError


class MemoryStore:
    """An async store that can simulate a concurrent edit during disk I/O."""

    def __init__(self) -> None:
        self.value = None
        self.on_save = None
        self.fail = False

    async def async_load(self):
        return copy.deepcopy(self.value)

    async def async_save(self, value):
        if self.fail:
            raise OSError("disk full")
        self.value = copy.deepcopy(value)
        if self.on_save:
            callback = self.on_save
            self.on_save = None
            callback()

    async def async_remove(self):
        self.value = None


@pytest.fixture
def runtime(source: dict, monkeypatch):
    current = copy.deepcopy(source)
    sentinel = object()
    entry = SimpleNamespace(aliases=[sentinel, "Deckenlampe"])
    store = MemoryStore()
    calls = []
    fail_exposure = [False]

    def update_entity(entity_id, **kwargs):
        assert entity_id == "light.ceiling"
        assert not set(kwargs) - {"aliases", "name", "area_id"}
        calls.append((entity_id, kwargs))
        for key, value in kwargs.items():
            if key == "aliases":
                entry.aliases = value
                current["entities"][0]["aliases"] = sorted(
                    alias for alias in value if isinstance(alias, str)
                )
            elif key == "name":
                current["entities"][0]["registry_name"] = value
            else:
                current["entities"][0][key] = value

    def expose(_hass, assistant, entity_id, value):
        assert assistant == "conversation"
        calls.append((entity_id, {"assist": value}))
        if fail_exposure[0] and value is False:
            raise ValueError("simulated registry failure")
        current["entities"][0]["exposed_to_assist"] = value

    registry = SimpleNamespace(async_get=lambda _: entry, async_update_entity=update_entity)
    monkeypatch.setattr(assist_module, "Store", lambda *args, **kwargs: store)
    monkeypatch.setattr(assist_module, "collect_snapshot", lambda _: copy.deepcopy(current))
    monkeypatch.setattr(assist_module.entity_registry, "async_get", lambda _: registry)
    monkeypatch.setattr(assist_module.exposed_entities, "async_expose_entity", expose)
    manager = AssistOptimizer(SimpleNamespace(), "config-entry")
    manager._data["snapshots"] = [copy.deepcopy(source)]
    return SimpleNamespace(
        manager=manager, current=current, entry=entry, sentinel=sentinel,
        store=store, calls=calls, fail_exposure=fail_exposure,
    )


def test_preview_is_read_only_and_belongs_to_admin(runtime, patch: dict) -> None:
    async def scenario():
        preview = await runtime.manager.async_preview(json.dumps(patch), "admin-one")
        assert not runtime.calls
        selection = [preview["operations"][0]["id"]]
        with pytest.raises(PatchError):
            await runtime.manager.async_apply(preview["preview_id"], selection, "admin-two")
        assert not runtime.calls
        runtime.manager.discard(preview["preview_id"], "admin-one")
        with pytest.raises(PatchError):
            await runtime.manager.async_apply(preview["preview_id"], selection, "admin-one")
    asyncio.run(scenario())


def test_only_selected_field_changes_and_sentinel_is_preserved(runtime, patch: dict) -> None:
    async def scenario():
        preview = await runtime.manager.async_preview(json.dumps(patch), "admin")
        addition = next(
            item for item in preview["operations"]
            if item["field"] == "aliases" and item["after"] is True
        )
        report = await runtime.manager.async_apply(
            preview["preview_id"], [addition["id"]], "admin"
        )
        assert report["status"] == "applied"
        assert report["applied_count"] == 1
        assert runtime.entry.aliases == [
            runtime.sentinel, "Deckenlampe", "Licht an der Decke"
        ]
        assert runtime.current["entities"][0]["registry_name"] is None
        assert runtime.current["entities"][0]["exposed_to_assist"] is True
        with pytest.raises(PatchError):
            await runtime.manager.async_apply(preview["preview_id"], [addition["id"]], "admin")
    asyncio.run(scenario())


def test_concurrent_edit_after_preview_prevents_all_writes(runtime, patch: dict) -> None:
    async def scenario():
        preview = await runtime.manager.async_preview(json.dumps(patch), "admin")
        runtime.current["entities"][0]["registry_name"] = "Manually edited"
        with pytest.raises(PatchError):
            await runtime.manager.async_apply(
                preview["preview_id"], [item["id"] for item in preview["operations"]], "admin"
            )
        assert not runtime.calls
    asyncio.run(scenario())


def test_concurrent_edit_during_journal_save_is_rechecked(runtime, patch: dict) -> None:
    async def scenario():
        preview = await runtime.manager.async_preview(json.dumps(patch), "admin")
        runtime.store.on_save = lambda: runtime.current["entities"][0].update(
            registry_name="Edited while saving"
        )
        report = await runtime.manager.async_apply(
            preview["preview_id"], [item["id"] for item in preview["operations"]], "admin"
        )
        assert report["status"] == "rolled_back"
        assert not runtime.calls
    asyncio.run(scenario())


def test_journal_failure_prevents_writes(runtime, patch: dict) -> None:
    async def scenario():
        preview = await runtime.manager.async_preview(json.dumps(patch), "admin")
        runtime.store.fail = True
        with pytest.raises(OSError):
            await runtime.manager.async_apply(
                preview["preview_id"], [item["id"] for item in preview["operations"]], "admin"
            )
        assert not runtime.calls
    asyncio.run(scenario())


def test_failed_write_restores_names_alias_order_and_exposure(runtime, patch: dict) -> None:
    async def scenario():
        runtime.entry.aliases = ["Deckenlampe", runtime.sentinel]
        before = list(runtime.entry.aliases)
        preview = await runtime.manager.async_preview(json.dumps(patch), "admin")
        runtime.fail_exposure[0] = True
        report = await runtime.manager.async_apply(
            preview["preview_id"], [item["id"] for item in preview["operations"]], "admin"
        )
        assert report["status"] == "rolled_back"
        assert report["applied_count"] == 0
        assert runtime.entry.aliases == before
        assert runtime.current["entities"][0]["registry_name"] is None
        assert runtime.current["entities"][0]["exposed_to_assist"] is True
        assert runtime.store.value["report"]["status"] == "rolled_back"
    asyncio.run(scenario())


def test_baselines_survive_restart_and_unknown_sources_fail(runtime, patch: dict) -> None:
    async def scenario():
        await runtime.store.async_save(runtime.manager._data)
        restored = AssistOptimizer(SimpleNamespace(), "config-entry")
        await restored.async_initialize()
        assert await restored.async_preview(json.dumps(patch), "admin")
        patch["source_id"] = "foreign-source"
        with pytest.raises(PatchError):
            await restored.async_preview(json.dumps(patch), "admin")
    asyncio.run(scenario())


def test_websocket_rejects_non_admin_before_scheduling() -> None:
    connection = SimpleNamespace(user=SimpleNamespace(is_admin=False))
    hass = SimpleNamespace(async_create_background_task=Mock())
    with pytest.raises(Unauthorized):
        websocket_assist(hass, connection, {"id": 1, "action": "apply"})
    hass.async_create_background_task.assert_not_called()
