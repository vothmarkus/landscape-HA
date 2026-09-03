"""Pure CSV writing helpers for HA Landscape."""

from __future__ import annotations

import csv
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any

from .const import CSV_DELIMITER, CSV_ENCODING


def write_csv(
    target: Path,
    fieldnames: Sequence[str],
    rows: Iterable[Mapping[str, Any]],
) -> int:
    """Write a complete CSV snapshot and return its size in bytes.

    The previous public export is removed only after the new temporary file has
    been written successfully. This avoids leaving a half-written CSV behind.
    """
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(f"{target.suffix}.tmp")

    try:
        with temporary.open("w", encoding=CSV_ENCODING, newline="") as csv_file:
            writer = csv.DictWriter(
                csv_file,
                fieldnames=fieldnames,
                delimiter=CSV_DELIMITER,
                extrasaction="ignore",
                quoting=csv.QUOTE_MINIMAL,
            )
            writer.writeheader()
            writer.writerows(rows)

        if target.exists():
            target.unlink()
        temporary.replace(target)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise

    return target.stat().st_size


def delete_csv(target: Path) -> bool:
    """Delete an existing CSV export."""
    if not target.exists():
        return False
    target.unlink()
    return True
