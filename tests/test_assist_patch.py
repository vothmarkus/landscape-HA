"""Safety and round-trip tests for offline Assist patches."""

from __future__ import annotations

import copy
import io
import json
import zipfile

import pytest

from custom_components.landscape.assist_patch import build_preview, select_operations
from custom_components.landscape.assist_schema import PatchError, parse_patch
from custom_components.landscape.assist_snapshot import build_archive, safe_state


def test_zip_contains_self_describing_round_trip(source: dict) -> None:
    with zipfile.ZipFile(io.BytesIO(build_archive(source))) as archive:
        assert set(archive.namelist()) == {
            "landscape.json", "optimization_schema.json", "CHATGPT_INSTRUCTIONS.md"
        }
        assert json.loads(archive.read("landscape.json")) == source
        schema = json.loads(archive.read("optimization_schema.json"))
        assert schema["additionalProperties"] is False
        assert schema["properties"]["changes"]["items"]["additionalProperties"] is False
        assert "Keine entity_id" in archive.read("CHATGPT_INSTRUCTIONS.md").decode()


def test_selective_apply_and_state_changes(source: dict, patch: dict) -> None:
    current = copy.deepcopy(source)
    current["entities"][0]["state"] = "on"
    operations = build_preview(patch, source, current)
    assert len(operations) == 4
    assert all(item["status"] == "ready" for item in operations)
    chosen = select_operations(operations, [operations[1]["id"]])
    assert len(chosen) == 1
    assert chosen[0]["field"] == "aliases"
    assert chosen[0]["after"] is True


@pytest.mark.parametrize("raw", [
    '{"schema_version":true,"source_id":"x","changes":[]}',
    '{"schema_version":1,"source_id":"x","source_id":"y","changes":[]}',
    '{"schema_version":1,"source_id":"x","changes":[],"service":"light.turn_on"}',
    '{"schema_version":NaN,"source_id":"x","changes":[]}',
    '[]',
    'not json',
])
def test_invalid_json_is_rejected(raw: str) -> None:
    with pytest.raises(PatchError):
        parse_patch(raw)


@pytest.mark.parametrize("edit", [
    {"new_entity_id": "light.renamed"},
    {"device_id": "other-device"},
    {"name": {"old": "Decke", "new": ""}},
    {"name": {"old": "Decke", "new": " Decke"}},
    {"name": {"old": "Decke", "new": "a\nb"}},
    {"assist": {"exposed": "false"}},
    {"assist": {"exposed": 1}},
    {"aliases": {"add": ["Lampe", "lampe"]}},
    {"aliases": {"add": ["Lampe"], "remove": ["lampe"]}},
    {"aliases": {"add": []}},
    {"aliases": {"add": ["Lamp"] * 101}},
])
def test_unknown_fields_and_invalid_values(patch: dict, edit: dict) -> None:
    patch["changes"][0].update(edit)
    with pytest.raises(PatchError):
        parse_patch(json.dumps(patch))


def test_size_and_nesting_limits() -> None:
    with pytest.raises(PatchError):
        parse_patch(" " * 2_000_001)
    with pytest.raises(PatchError):
        parse_patch("[" * 1500 + "]" * 1500)


def test_foreign_source_and_unknown_entity(source: dict, patch: dict) -> None:
    patch["source_id"] = "other-installation"
    with pytest.raises(PatchError):
        build_preview(patch, source, source)
    patch["source_id"] = source["source_id"]
    patch["changes"][0]["entity_id"] = "switch.unknown"
    with pytest.raises(PatchError):
        build_preview(patch, source, source)


def test_wrong_old_and_duplicate_target(source: dict, patch: dict) -> None:
    patch["changes"][0]["name"]["old"] = "Wrong"
    with pytest.raises(PatchError):
        build_preview(patch, source, source)
    patch["changes"].append(copy.deepcopy(patch["changes"][0]))
    with pytest.raises(PatchError):
        parse_patch(json.dumps(patch))


@pytest.mark.parametrize("key,value", [
    ("registry_id", "replacement-entity"),
    ("device_id", "other-device"),
    ("area", "New room name"),
    ("disabled", True),
])
def test_changed_context_blocks_all_fields(source: dict, patch: dict, key: str, value) -> None:
    current = copy.deepcopy(source)
    current["entities"][0][key] = value
    operations = build_preview(patch, source, current)
    assert all(item["status"] == "conflict" for item in operations)
    with pytest.raises(PatchError):
        select_operations(operations, [item["id"] for item in operations])


def test_stale_name_does_not_block_independent_alias(source: dict, patch: dict) -> None:
    current = copy.deepcopy(source)
    current["entities"][0]["registry_name"] = "User edited name"
    operations = build_preview(patch, source, current)
    assert operations[0]["status"] == "conflict"
    assert operations[1]["status"] == "ready"
    with pytest.raises(PatchError):
        select_operations(operations, [operations[0]["id"], operations[1]["id"]])
    assert select_operations(operations, [operations[1]["id"]])


def test_replay_is_a_noop(source: dict, patch: dict) -> None:
    current = copy.deepcopy(source)
    current["entities"][0].update(
        registry_name="Deckenlicht", aliases=["Licht an der Decke"], exposed_to_assist=False
    )
    operations = build_preview(patch, source, current)
    assert all(item["status"] == "unchanged" for item in operations)
    assert select_operations(operations, [item["id"] for item in operations]) == []


def test_unregistered_entity_allows_only_exposure(source: dict, patch: dict) -> None:
    source["entities"][0]["registry_id"] = None
    with pytest.raises(PatchError):
        build_preview(patch, source, source)
    del patch["changes"][0]["name"]
    del patch["changes"][0]["aliases"]
    assert build_preview(patch, source, source)[0]["field"] == "assist"


def test_area_inheritance_and_floor_scope(source: dict) -> None:
    patch = {
        "schema_version": 1, "source_id": source["source_id"],
        "changes": [{
            "entity_id": "light.ceiling",
            "area_id": {"old": None, "new": "bedroom"},
            "reason": "Explizit zuordnen.",
        }],
        "area_changes": [{
            "area_id": "bedroom", "floor_id": {"old": "upper", "new": "ground"},
            "reason": "Bereich liegt im Erdgeschoss.",
        }],
    }
    operations = build_preview(patch, source, source)
    assert operations[0]["before"] is None
    assert operations[1]["affected_entity_ids"] == ["light.ceiling"]
    assert operations[1]["display_after"] == "Erdgeschoss"
    current = copy.deepcopy(source)
    current["floors"].pop()
    assert build_preview(patch, source, current)[1]["status"] == "conflict"
    patch["changes"][0]["area_id"]["new"] = "invented-area"
    with pytest.raises(PatchError):
        build_preview(patch, source, source)


def test_selection_must_be_explicit_and_known(source: dict, patch: dict) -> None:
    operations = build_preview(patch, source, source)
    for selected in ([], ["invented"], [operations[0]["id"]] * 2, [123]):
        with pytest.raises(PatchError):
            select_operations(operations, selected)


@pytest.mark.parametrize("value,expected", [
    ("off", "off"), ("21.5", "21.5"), (None, None), ("nan", None),
    ("https://example.org?token=secret", None), ("private-message", None),
])
def test_reduced_states(value, expected) -> None:
    assert safe_state(value) == expected
