"""Device inheritance and semantic context in Assist exports."""

from types import SimpleNamespace

from homeassistant.helpers.device_registry import ChildDeviceEntry, DeviceEntry

import custom_components.landscape.assist_snapshot as snapshot_module


def test_child_device_inherits_parent_area_and_hardware(monkeypatch) -> None:
    parent = DeviceEntry(
        config_entry_id="config",
        id="parent",
        area_id="bedroom",
        manufacturer="Example",
        model="Six-channel actuator",
    )
    child = ChildDeviceEntry(
        config_entry_id="config",
        id="child",
        parent_device_id="parent",
        name="Channel 1",
    )
    devices = {parent.id: parent, child.id: child}
    entry = SimpleNamespace(
        entity_id="light.ceiling",
        id="entry",
        device_id="child",
        area_id=None,
        name=None,
        original_name="Decke",
        config_entry_id=None,
        platform="test",
        aliases=[],
        disabled_by=None,
        hidden_by=None,
        entity_category=None,
    )
    entities = {entry.entity_id: entry}
    area = SimpleNamespace(id="bedroom", name="Schlafzimmer", floor_id="upper")
    floor = SimpleNamespace(floor_id="upper", name="Obergeschoss")
    monkeypatch.setattr(
        snapshot_module.entity_registry,
        "async_get",
        lambda _: SimpleNamespace(entities=entities, async_get=entities.get),
    )
    monkeypatch.setattr(
        snapshot_module.device_registry,
        "async_get",
        lambda _: SimpleNamespace(async_get=devices.get),
    )
    monkeypatch.setattr(
        snapshot_module.area_registry,
        "async_get",
        lambda _: SimpleNamespace(
            async_get_area=lambda _: area, async_list_areas=lambda: [area]
        ),
    )
    monkeypatch.setattr(
        snapshot_module.floor_registry,
        "async_get",
        lambda _: SimpleNamespace(
            async_get_floor=lambda _: floor, async_list_floors=lambda: [floor]
        ),
    )
    monkeypatch.setattr(
        snapshot_module.exposed_entities, "async_should_expose", lambda *_: True
    )
    hass = SimpleNamespace(states=SimpleNamespace(async_all=lambda: []))
    result = snapshot_module.collect_snapshot(hass)["entities"][0]
    assert result["area_id"] is None
    assert result["effective_area_id"] == "bedroom"
    assert result["floor"] == "Obergeschoss"
    assert result["device"]["name"] == "Channel 1"
    assert result["device"]["manufacturer"] == "Example"
    assert result["device"]["model"] == "Six-channel actuator"
    assert result["device"]["parent_device_id"] == "parent"
