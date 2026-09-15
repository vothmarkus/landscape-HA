"""Review and apply YAML imports with native HA checks and rollback."""

from __future__ import annotations

import asyncio
import logging
from collections import Counter
from pathlib import Path
from time import monotonic
from uuid import uuid4

from homeassistant.core import HomeAssistant

from .configuration_files import ConfigurationFiles
from .configuration_yaml import ConfigurationError

_LOGGER = logging.getLogger(__name__)
PREVIEW_TTL = 1800


class ConfigurationWorkspace:
    """Serialize file access and bind each review to its administrator."""

    def __init__(self, hass: HomeAssistant) -> None:
        self.hass = hass
        self.files = ConfigurationFiles(hass.config.config_dir)
        self._lock = asyncio.Lock()
        self._previews = {}
        self._tasks: set[asyncio.Task] = set()

    async def async_initialize(self) -> None:
        await self.hass.async_add_executor_job(self.files.recover)

    async def async_wait(self) -> None:
        if self._tasks:
            await asyncio.gather(*(asyncio.shield(task) for task in self._tasks))

    async def async_read(self, action: str, **fields) -> dict:
        async with self._lock:
            if action == "list":
                return await self.hass.async_add_executor_job(self.files.inventory)
            if action == "view":
                return await self.hass.async_add_executor_job(
                    self.files.view, fields["path"]
                )
            if action == "inspect":
                return await self.hass.async_add_executor_job(
                    self.files.inspect, fields.get("files", []), fields.get("archive")
                )
            if action == "export":
                return await self.hass.async_add_executor_job(
                    self.files.export,
                    fields.get("paths"),
                    fields.get("context", False),
                    fields.get("dated", False),
                )
        raise ConfigurationError("Unbekannte Aktion.")

    async def async_preview(
        self,
        user_id: str,
        imports: list[dict] | None = None,
        backup_id: str | None = None,
    ) -> dict:
        async with self._lock:
            plan = (
                await self.hass.async_add_executor_job(
                    self.files.restore_plan, backup_id
                )
                if backup_id
                else await self.hass.async_add_executor_job(
                    self.files.prepare, imports or []
                )
            )
            self._previews = {
                key: value
                for key, value in self._previews.items()
                if value["user_id"] != user_id
                and monotonic() - value["created"] < PREVIEW_TTL
            }
            if len(self._previews) >= 5:
                self._previews.pop(next(iter(self._previews)))
            preview_id = uuid4().hex
            self._previews[preview_id] = {
                "user_id": user_id,
                "created": monotonic(),
                "plan": plan,
            }
            return {
                "preview_id": preview_id,
                "files": [
                    {
                        key: value
                        for key, value in change.items()
                        if key not in {"before", "after"}
                    }
                    for change in plan["changes"]
                ],
                "validation": {
                    "yaml": "passed",
                    "context": "passed",
                    "home_assistant": "pending_apply",
                },
                "backup": "created_on_apply",
                "skipped": plan["skipped"],
            }

    def _preview(self, preview_id: str, user_id: str) -> dict:
        preview = self._previews.get(preview_id)
        if (
            preview is None
            or preview["user_id"] != user_id
            or monotonic() - preview["created"] >= PREVIEW_TTL
        ):
            raise ConfigurationError(
                "Die Vorschau ist abgelaufen. Bitte erneut prüfen."
            )
        return preview["plan"]

    def discard(self, preview_id: str, user_id: str) -> None:
        self._preview(preview_id, user_id)
        self._previews.pop(preview_id)

    async def _validate(self) -> dict:
        from homeassistant.helpers.check_config import (
            async_check_ha_config_file,
        )

        async with asyncio.timeout(120):
            result = await async_check_ha_config_file(self.hass)
            strict_errors = (
                await self._validate_automation_scripts() if not result.errors else []
            )
        return {
            "errors": [item.message for item in result.errors],
            "warnings": [item.message for item in result.warnings] + strict_errors,
        }

    async def _validate_automation_scripts(self) -> list[str]:
        """The general checker can otherwise accept disabled invalid entries."""
        from annotatedyaml.loader import Secrets
        from homeassistant.components.automation.config import (
            async_validate_config_item as validate_automation,
        )
        from homeassistant.components.script.config import (
            async_validate_config_item as validate_script,
        )
        from homeassistant.config import (
            config_per_platform,
            load_yaml_config_file,
            merge_packages_config,
        )

        config = await self.hass.async_add_executor_job(
            load_yaml_config_file,
            self.hass.config.path("configuration.yaml"),
            Secrets(Path(self.hass.config.config_dir)),
        )
        await merge_packages_config(
            self.hass, config, (config.get("homeassistant") or {}).get("packages", {})
        )
        messages = []
        for domain, validator in (
            ("automation", validate_automation),
            ("script", validate_script),
        ):
            seen = set()
            for _, section in config_per_platform(config, domain):
                if not isinstance(section, dict):
                    messages.append(f"{domain}: Zuordnung erwartet.")
                    continue
                items = (
                    section.items()
                    if domain == "script"
                    else [
                        (
                            str(section.get("id", section.get("alias", "ohne ID"))),
                            section,
                        )
                    ]
                )
                for key, item in items:
                    if (domain == "script" or "id" in item) and key in seen:
                        messages.append(
                            f"{domain}.{key}: Doppelte ID / doppelter Schlüssel."
                        )
                    seen.add(key)
                    try:
                        await validator(self.hass, key, item)
                    except Exception as err:
                        messages.append(f"{domain}.{key}: {err}")
        return messages

    async def _write_job(self, function, *args):
        """Await executor completion before cancellation can start a rollback."""
        future = self.hass.async_add_executor_job(function, *args)
        try:
            return await asyncio.shield(future)
        except asyncio.CancelledError:
            await asyncio.shield(future)
            raise

    async def async_apply(self, preview_id: str, user_id: str) -> dict:
        task = self.hass.async_create_task(
            self._apply(preview_id, user_id), "Landscape configuration import"
        )
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return await asyncio.shield(task)

    async def _apply(self, preview_id: str, user_id: str) -> dict:
        async with self._lock:
            plan = self._preview(preview_id, user_id)
            if not plan["changes"]:
                self._previews.pop(preview_id)
                return {"status": "unchanged", "files": [], "rollback_errors": []}
            await self.hass.async_add_executor_job(self.files.check_snapshot, plan)
            baseline = await self._validate()
            report = await self.hass.async_add_executor_job(
                self.files.begin, plan, user_id
            )
            self._previews.pop(preview_id)
            try:
                await self._write_job(self.files.write, plan, report)
                validation = await self._validate()
                report["validation"] = validation
                new_warnings = list(
                    (
                        Counter(validation["warnings"]) - Counter(baseline["warnings"])
                    ).elements()
                )
                if validation["errors"] or new_warnings:
                    raise ConfigurationError(
                        "HA-Prüfung hat neue Probleme gemeldet:\n"
                        + "\n".join(validation["errors"] + new_warnings)
                    )
                await self.hass.async_add_executor_job(self.files.check_written, plan)
                await self._write_job(self.files.finish, report)
            except BaseException as err:
                report["error"] = (
                    str(err)
                    if isinstance(err, ConfigurationError)
                    else "Übernahme oder HA-Prüfung fehlgeschlagen."
                )
                try:
                    report = await asyncio.shield(
                        self.hass.async_add_executor_job(self.files.rollback, report)
                    )
                except Exception:
                    _LOGGER.exception(
                        "Configuration rollback needs recovery; backup %s", report["id"]
                    )
                    report["status"] = "recovery_required"
                    report["rollback_errors"] = [
                        item["path"] for item in report["files"]
                    ]
                if isinstance(err, asyncio.CancelledError):
                    raise
                if not isinstance(err, ConfigurationError):
                    _LOGGER.exception(
                        "Configuration import failed; backup %s", report["id"]
                    )
            return report
