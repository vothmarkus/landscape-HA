"""Build field-level diffs with optimistic concurrency checks."""

from __future__ import annotations

from typing import Any

from .assist_schema import PatchError, validate_patch

ENTITY_CONTEXT = (
    "registry_id", "device_id", "device", "original_name", "has_automatic_alias",
    "effective_area_id", "area",
    "floor_id", "floor", "disabled", "hidden",
)


def _index(snapshot: dict, key: str, identifier: str) -> dict[str, dict]:
    return {item[identifier]: item for item in snapshot[key]}


def build_preview(
    patch: dict[str, Any], source: dict[str, Any], current: dict[str, Any]
) -> list[dict[str, Any]]:
    """Reject invalid patches and mark stale or already-applied fields."""
    validate_patch(patch)
    if patch["source_id"] != source["source_id"]:
        raise PatchError("Der Patch gehört nicht zu diesem Export.")
    original = _index(source, "entities", "entity_id")
    live = _index(current, "entities", "entity_id")
    old_areas = _index(source, "areas", "area_id")
    areas = _index(current, "areas", "area_id")
    old_floors = _index(source, "floors", "floor_id")
    floors = _index(current, "floors", "floor_id")
    operations: list[dict[str, Any]] = []

    def append(
        kind: str,
        target: str,
        field: str,
        before: Any,
        after: Any,
        actual: Any,
        reason: str,
        conflict: str | None,
        *,
        label: str,
        suffix: str = "",
        **extra: Any,
    ) -> None:
        status = "ready"
        if conflict:
            status = "conflict"
        elif actual == after:
            status = "unchanged"
        elif actual != before:
            status = "conflict"
            conflict = "Seit dem Export geändert. Bitte neu exportieren."
        operations.append(
            {
                "id": f"{kind}/{target}/{field}{suffix}",
                "kind": kind,
                "target": target,
                "field": field,
                "label": label,
                "before": before,
                "after": after,
                "current": actual,
                "reason": reason,
                "status": status,
                "conflict": conflict,
                **extra,
            }
        )

    for change in patch["changes"]:
        target = change["entity_id"]
        if target not in original:
            raise PatchError(f"Entität war nicht im Export: {target}")
        old = original[target]
        now = live.get(target)
        conflict = None
        if now is None:
            conflict = "Entität existiert nicht mehr."
        elif any(old.get(key) != now.get(key) for key in ENTITY_CONTEXT):
            conflict = "Identität, Gerät oder räumlicher Kontext wurde geändert."
        now = now or old
        if old["registry_id"] is None and set(change) - {"entity_id", "assist", "reason"}:
            raise PatchError(f"{target}: ohne Registry-Eintrag nur Assist-Freigabe änderbar.")
        reason = change["reason"]
        label = old["friendly_name"]

        if "name" in change:
            pair = change["name"]
            if pair["old"] != old["name"]:
                raise PatchError(f"{target}: name.old stimmt nicht mit dem Export überein.")
            append(
                "entity", target, "name", old["registry_name"], pair["new"],
                now["registry_name"], reason, conflict, label=label,
                display_before=old["name"],
            )

        if "aliases" in change:
            old_aliases = old["aliases"]
            current_aliases = now["aliases"]
            for action in ("add", "remove"):
                for index, alias in enumerate(change["aliases"].get(action, [])):
                    if action == "remove" and alias not in old_aliases:
                        raise PatchError(f"{target}: zu entfernender Alias fehlt: {alias}")
                    alias_conflict = conflict
                    if current_aliases != old_aliases:
                        # An already-applied alias operation remains a harmless no-op.
                        desired = action == "add"
                        if (alias in current_aliases) != desired:
                            alias_conflict = "Aliase wurden seit dem Export geändert."
                    append(
                        "entity", target, "aliases", alias in old_aliases,
                        action == "add", alias in current_aliases, reason,
                        alias_conflict, label=label, suffix=f"/{action}/{index}",
                        alias=alias, action=action,
                    )

        if "area_id" in change:
            pair = change["area_id"]
            if pair["old"] != old["area_id"]:
                raise PatchError(f"{target}: area_id.old stimmt nicht mit dem Export überein.")
            new_area = pair["new"]
            if new_area is not None and new_area not in old_areas:
                raise PatchError(f"Unbekannter Zielbereich im Export: {new_area}")
            area_conflict = conflict
            if new_area is not None and areas.get(new_area) != old_areas[new_area]:
                area_conflict = (
                    "Der Zielbereich wurde inzwischen geändert oder gelöscht."
                )
            append(
                "entity", target, "area_id", old["area_id"], new_area, now["area_id"],
                reason, area_conflict, label=label,
                display_before=(old_areas.get(old["area_id"]) or {}).get("name", "Vom Gerät erben"),
                display_after=(old_areas.get(new_area) or {}).get("name", "Vom Gerät erben"),
            )

        if "assist" in change:
            desired = change["assist"]["exposed"]
            exposure_conflict = conflict
            if desired and old["disabled"]:
                exposure_conflict = (
                    "Deaktivierte Entitäten können hier nicht freigegeben werden."
                )
            append(
                "entity", target, "assist", old["exposed_to_assist"], desired,
                now["exposed_to_assist"], reason, exposure_conflict, label=label,
            )

    for change in patch.get("area_changes", []):
        target = change["area_id"]
        if target not in old_areas:
            raise PatchError(f"Bereich war nicht im Export: {target}")
        old = old_areas[target]
        now = areas.get(target)
        pair = change["floor_id"]
        if pair["old"] != old["floor_id"]:
            raise PatchError(f"{target}: floor_id.old stimmt nicht mit dem Export überein.")
        new_floor = pair["new"]
        if new_floor is not None and new_floor not in old_floors:
            raise PatchError(f"Unbekannte Zieletage im Export: {new_floor}")
        conflict = None
        if now is None or now["name"] != old["name"]:
            conflict = "Bereich wurde geändert oder gelöscht."
        elif new_floor is not None and floors.get(new_floor) != old_floors[new_floor]:
            conflict = "Zieletage wurde geändert oder gelöscht."
        affected = sorted(
            item["entity_id"] for item in current["entities"]
            if item["effective_area_id"] == target
        )
        old_affected = sorted(
            item["entity_id"] for item in source["entities"]
            if item["effective_area_id"] == target
        )
        if affected != old_affected:
            conflict = "Die dem Bereich zugeordneten Entitäten wurden geändert."
        append(
            "area", target, "floor_id", old["floor_id"], new_floor,
            now["floor_id"] if now else None, change["reason"], conflict,
            label=old["name"], affected_entity_ids=affected,
            display_before=(old_floors.get(old["floor_id"]) or {}).get("name", "Keine Etage"),
            display_after=(old_floors.get(new_floor) or {}).get("name", "Keine Etage"),
        )
    return operations


def select_operations(operations: list[dict], selected: Any) -> list[dict]:
    """Resolve an explicit selection; a single conflict prevents all writes."""
    if (
        not isinstance(selected, list)
        or not selected
        or any(not isinstance(value, str) for value in selected)
        or len(set(selected)) != len(selected)
    ):
        raise PatchError("Bitte mindestens eine eindeutige Änderung auswählen.")
    by_id = {item["id"]: item for item in operations}
    if set(selected) - by_id.keys():
        raise PatchError("Die Auswahl enthält unbekannte Änderungen.")
    result = [by_id[identifier] for identifier in selected]
    if any(item["status"] == "conflict" for item in result):
        raise PatchError("Die Auswahl enthält Konflikte. Bitte die Vorschau neu laden.")
    return [item for item in result if item["status"] == "ready"]
