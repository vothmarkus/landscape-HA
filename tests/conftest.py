"""Shared offline Assist inventory fixtures."""

from __future__ import annotations

import pytest


@pytest.fixture
def source() -> dict:
    """A small installation with a light, an area and two existing floors."""
    return {
        "schema_version": 1,
        "source_id": "source-one",
        "exported_at": "2026-09-14T10:30:00+00:00",
        "entities": [
            {
                "entity_id": "light.ceiling",
                "registry_id": "registry-one",
                "name": "Decke",
                "registry_name": None,
                "friendly_name": "Schlafzimmer Decke",
                "device_id": "device-one",
                "device": {"name": "Schlafzimmer", "area_id": "bedroom"},
                "effective_area_id": "bedroom",
                "area_id": None,
                "area": "Schlafzimmer",
                "floor_id": "upper",
                "floor": "Obergeschoss",
                "aliases": ["Deckenlampe"],
                "exposed_to_assist": True,
                "disabled": False,
                "hidden": False,
                "state": "off",
            }
        ],
        "areas": [{"area_id": "bedroom", "name": "Schlafzimmer", "floor_id": "upper"}],
        "floors": [
            {"floor_id": "upper", "name": "Obergeschoss"},
            {"floor_id": "ground", "name": "Erdgeschoss"},
        ],
    }


@pytest.fixture
def patch() -> dict:
    return {
        "schema_version": 1,
        "source_id": "source-one",
        "changes": [
            {
                "entity_id": "light.ceiling",
                "name": {"old": "Decke", "new": "Deckenlicht"},
                "aliases": {"add": ["Licht an der Decke"], "remove": ["Deckenlampe"]},
                "assist": {"exposed": False},
                "reason": "Vom Ambientelicht unterscheiden.",
            }
        ],
    }
