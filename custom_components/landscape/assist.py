"""Persist export baselines and apply reviewed Assist changes."""

from __future__ import annotations

import asyncio
import base64
import logging
from datetime import UTC, datetime
from time import monotonic
from typing import Any
from uuid import uuid4

from homeassistant.components.homeassistant import exposed_entities
from homeassistant.core import HomeAssistant
from homeassistant.helpers import area_registry, entity_registry
from homeassistant.helpers.storage import Store

from .assist_patch import build_preview, select_operations
from .assist_schema import PatchError, parse_patch
from .assist_snapshot import build_archive, collect_snapshot

_LOGGER = logging.getLogger(__name__)
MAX_SNAPSHOTS = 3
PREVIEW_TTL = 3600


class AssistOptimizer:
    """Keep import data separate from the existing public CSV exporter."""

    def __init__(self, hass: HomeAssistant, entry_id: str) -> None:
        self.hass = hass
        self._store: Store = Store(
            hass, 1, f"landscape.assist.{entry_id}", private=True, atomic_writes=True
        )
        self._data: dict[str, Any] = {"snapshots": [], "report": None}
        self._previews: dict[str, dict[str, Any]] = {}
        self._lock = asyncio.Lock()

    async def async_initialize(self) -> None:
        """Restore baselines so ZIP imports survive Home Assistant restarts."""
        if data := await self._store.async_load():
            self._data = data

    def status(self) -> dict[str, Any]:
        """Return a small summary for the panel."""
        return {
            "exports": [
                {"source_id": item["source_id"], "exported_at": item["exported_at"]}
                for item in self._data["snapshots"]
            ],
            "report": self._data["report"],
        }

    async def async_export(self) -> dict[str, Any]:
        """Save a baseline and return an authenticated ZIP download."""
        async with self._lock:
            snapshot = collect_snapshot(self.hass)
            archive = await self.hass.async_add_executor_job(build_archive, snapshot)
            data = self._data | {
                "snapshots": [snapshot, *self._data["snapshots"]][:MAX_SNAPSHOTS]
            }
            await self._store.async_save(data)
            self._data = data
            return {
                "filename": (
                    f"assist_landscape_{snapshot['exported_at'][:10]}_"
                    f"{snapshot['source_id'][:8]}.zip"
                ),
                "content": base64.b64encode(archive).decode("ascii"),
                "source_id": snapshot["source_id"],
                "entity_count": len(snapshot["entities"]),
            }

    def _source(self, source_id: str) -> dict[str, Any]:
        for snapshot in self._data["snapshots"]:
            if snapshot["source_id"] == source_id:
                return snapshot
        raise PatchError(
            "Export unbekannt oder nicht mehr gespeichert. "
            "Bitte einen der letzten drei Exporte dieser Installation verwenden."
        )

    async def async_preview(self, raw: str, user_id: str) -> dict[str, Any]:
        """Validate without changing names, aliases, locations or exposure choices."""
        patch = parse_patch(raw)
        async with self._lock:
            source = self._source(patch["source_id"])
            operations = build_preview(patch, source, collect_snapshot(self.hass))
            # One active preview per admin; expire abandoned imports.
            self._previews = {
                key: item for key, item in self._previews.items()
                if item["user_id"] != user_id and monotonic() - item["created"] < PREVIEW_TTL
            }
            if len(self._previews) >= 10:
                self._previews.pop(next(iter(self._previews)))
            preview_id = uuid4().hex
            self._previews[preview_id] = {
                "patch": patch, "user_id": user_id, "created": monotonic()
            }
            return {
                "preview_id": preview_id,
                "source_id": source["source_id"],
                "exported_at": source["exported_at"],
                "operations": operations,
            }

    def _preview(self, preview_id: str, user_id: str) -> dict:
        preview = self._previews.get(preview_id)
        if (
            preview is None
            or preview["user_id"] != user_id
            or monotonic() - preview["created"] >= PREVIEW_TTL
        ):
            raise PatchError("Die Vorschau ist abgelaufen. Bitte die Datei erneut prüfen.")
        return preview

    def discard(self, preview_id: str, user_id: str) -> None:
        """Discard an admin's pending patch without writes to HA registries."""
        self._preview(preview_id, user_id)
        self._previews.pop(preview_id)

    async def async_apply(
        self, preview_id: str, selected: list[str], user_id: str
    ) -> dict[str, Any]:
        """Preflight all selected fields, journal, then apply without yielding."""
        async with self._lock:
            preview = self._preview(preview_id, user_id)
            patch = preview["patch"]
            source = self._source(patch["source_id"])

            def preflight() -> list[dict]:
                return select_operations(
                    build_preview(patch, source, collect_snapshot(self.hass)), selected
                )

            operations = preflight()
            report: dict[str, Any] = {
                "source_id": patch["source_id"],
                "started_at": datetime.now(UTC).isoformat(),
                "status": "pending",
                "applied_count": 0,
                "operations": operations,
                "rollback_errors": [],
            }
            # Persist the before/after journal before the first mutation.
            await self._store.async_save(self._data | {"report": report})
            self._data["report"] = report
            attempted: list[tuple[dict, Any]] = []
            try:
                # Saving yielded to the event loop: check again before any writes.
                operations = preflight()
                report["operations"] = operations
                self._previews.pop(preview_id)
                for operation in operations:
                    previous = operation["before"]
                    if operation["field"] == "aliases":
                        registry = entity_registry.async_get(self.hass)
                        previous = list(registry.async_get(operation["target"]).aliases)
                    attempted.append((operation, previous))
                    self._write(operation, operation["after"])
                report["status"] = "applied" if operations else "unchanged"
                report["applied_count"] = len(operations)
            except Exception as err:
                _LOGGER.exception("Assist patch application failed; restoring attempted fields")
                for operation, previous in reversed(attempted):
                    try:
                        if operation["field"] == "aliases":
                            entity_registry.async_get(self.hass).async_update_entity(
                                operation["target"], aliases=previous
                            )
                        else:
                            self._write(operation, previous)
                    except Exception:
                        _LOGGER.exception("Failed to restore Assist operation %s", operation["id"])
                        report["rollback_errors"].append(operation["id"])
                report["status"] = "partial" if report["rollback_errors"] else "rolled_back"
                report["error"] = str(err)
            report["finished_at"] = datetime.now(UTC).isoformat()
            try:
                await self._store.async_save(self._data)
            except Exception:
                _LOGGER.exception("Could not persist the completed Assist journal")
                report["persistence_error"] = (
                    "Das Ergebnisprotokoll konnte nicht gespeichert werden. "
                    "Bitte jetzt herunterladen."
                )
            return report

    def _write(self, operation: dict, value: Any) -> None:
        """Use supported registry APIs, touching only the selected field."""
        target = operation["target"]
        field = operation["field"]
        if operation["kind"] == "area":
            area_registry.async_get(self.hass).async_update(target, floor_id=value)
        elif field == "assist":
            exposed_entities.async_expose_entity(self.hass, "conversation", target, value)
        else:
            registry = entity_registry.async_get(self.hass)
            if field == "aliases":
                entry = registry.async_get(target)
                alias = operation["alias"]
                # Preserve HA's computed sentinel and its original position.
                aliases = list(entry.aliases)
                if value and alias not in aliases:
                    aliases.append(alias)
                elif not value:
                    aliases = [item for item in aliases if item != alias]
                registry.async_update_entity(target, aliases=aliases)
            elif field in {"name", "area_id"}:
                registry.async_update_entity(target, **{field: value})
            else:
                raise PatchError("Unzulässiges Änderungsfeld.")

    async def async_remove(self) -> None:
        """Remove stored Assist data when the integration is deleted."""
        await self._store.async_remove()
