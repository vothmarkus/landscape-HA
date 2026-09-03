"""Tests for serialization and credential redaction."""

from __future__ import annotations

import json

from custom_components.landscape.exporter import _json, _redact_sensitive


def test_redact_sensitive_values_recursively() -> None:
    """Credentials are removed while useful values stay intact."""
    attributes = {
        "brightness": 200,
        "access_token": "secret-value",
        "nested": {
            "password": "another-secret",
            "code": "1234",
            "mode": "heat",
        },
        "entity_picture": "/api/camera_proxy/camera.test?token=abc&size=small",
    }

    redacted = _redact_sensitive(attributes)

    assert redacted == {
        "brightness": 200,
        "access_token": "<redacted>",
        "nested": {
            "password": "<redacted>",
            "code": "<redacted>",
            "mode": "heat",
        },
        "entity_picture": ("/api/camera_proxy/camera.test?token=<redacted>&size=small"),
    }


def test_json_serializes_registry_sets_deterministically() -> None:
    """Sets and identifier tuples produce deterministic valid JSON."""
    result = _json({("zha", "second"), ("esphome", "first")})

    assert json.loads(result) == [["esphome", "first"], ["zha", "second"]]
