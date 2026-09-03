"""Tests for the pure HA Landscape CSV helpers."""

from __future__ import annotations

import csv
from pathlib import Path

from custom_components.landscape.const import CSV_DELIMITER, CSV_ENCODING
from custom_components.landscape.csv_writer import delete_csv, write_csv


def test_write_csv_replaces_previous_snapshot(tmp_path: Path) -> None:
    """A new export fully replaces the previous file."""
    target = tmp_path / "www" / "ha_entitaeten.csv"
    target.parent.mkdir()
    target.write_text("old data", encoding="utf-8")

    size = write_csv(
        target,
        ("entity_id", "friendly_name", "attributes_json"),
        [
            {
                "entity_id": "light.kuche",
                "friendly_name": "Küche; Decke",
                "attributes_json": '{"brightness":255}',
            }
        ],
    )

    assert size == target.stat().st_size
    assert not target.with_suffix(".csv.tmp").exists()
    with target.open(encoding=CSV_ENCODING, newline="") as csv_file:
        rows = list(csv.DictReader(csv_file, delimiter=CSV_DELIMITER))
    assert rows == [
        {
            "entity_id": "light.kuche",
            "friendly_name": "Küche; Decke",
            "attributes_json": '{"brightness":255}',
        }
    ]


def test_delete_csv_reports_if_file_existed(tmp_path: Path) -> None:
    """Deletion is idempotent."""
    target = tmp_path / "ha_entitaeten.csv"
    target.write_text("test", encoding="utf-8")

    assert delete_csv(target) is True
    assert delete_csv(target) is False
