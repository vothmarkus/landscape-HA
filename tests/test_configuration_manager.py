"""Exercise administrator checks, cancellation and native HA validation."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from homeassistant import loader
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import Unauthorized

from custom_components.landscape.configuration import ConfigurationWorkspace
from custom_components.landscape.configuration_api import websocket_configuration
from custom_components.landscape.configuration_yaml import ConfigurationError


def test_preview_ownership_and_expiration(tmp_path):
    async def scenario():
        (tmp_path / "configuration.yaml").write_text("{}\n")
        hass = HomeAssistant(str(tmp_path))
        workspace = ConfigurationWorkspace(hass)
        preview = await workspace.async_preview(
            "admin",
            [
                {
                    "path": "configuration.yaml",
                    "content": "homeassistant:\n  name: Home\n",
                }
            ],
        )
        assert preview["validation"]["home_assistant"] == "pending_apply"
        assert preview["backup"] == "created_on_apply"
        assert (tmp_path / "configuration.yaml").read_text() == "{}\n"
        with pytest.raises(ConfigurationError):
            await workspace.async_apply(preview["preview_id"], "someone-else")
        workspace._previews[preview["preview_id"]]["created"] -= 1801
        with pytest.raises(ConfigurationError):
            workspace.discard(preview["preview_id"], "admin")
        await hass.async_stop(force=True)

    asyncio.run(scenario())


@pytest.mark.parametrize(
    "problem", ["new_warning", "error", "exception", "concurrent", "cancel"]
)
def test_bad_after_state_is_rolled_back(tmp_path, monkeypatch, problem):
    async def scenario():
        (tmp_path / "configuration.yaml").write_text("{}\n")
        hass = HomeAssistant(str(tmp_path))
        workspace = ConfigurationWorkspace(hass)
        calls = 0

        async def validate():
            nonlocal calls
            calls += 1
            if calls == 1:
                return {"errors": [], "warnings": ["existing"]}
            assert (
                tmp_path / "configuration.yaml"
            ).read_text() == "homeassistant:\n  name: New\n"
            if problem == "exception":
                raise RuntimeError("validator failure")
            if problem == "cancel":
                raise asyncio.CancelledError
            if problem == "concurrent":
                (tmp_path / "new.yaml").write_text("{}\n")
            return {
                "errors": ["invalid config"] if problem == "error" else [],
                "warnings": ["existing", "new"]
                if problem == "new_warning"
                else ["existing"],
            }

        monkeypatch.setattr(workspace, "_validate", validate)
        preview = await workspace.async_preview(
            "admin",
            [
                {
                    "path": "configuration.yaml",
                    "content": "homeassistant:\n  name: New\n",
                }
            ],
        )
        if problem == "cancel":
            with pytest.raises(asyncio.CancelledError):
                await workspace.async_apply(preview["preview_id"], "admin")
        else:
            report = await workspace.async_apply(preview["preview_id"], "admin")
            assert report["status"] == "rolled_back"
        assert (tmp_path / "configuration.yaml").read_text() == "{}\n"
        if problem == "concurrent":
            assert (tmp_path / "new.yaml").exists()
        await hass.async_stop(force=True)

    asyncio.run(scenario())


def test_browser_disconnect_does_not_cancel_transaction(tmp_path, monkeypatch):
    async def scenario():
        (tmp_path / "configuration.yaml").write_text("{}\n")
        hass = HomeAssistant(str(tmp_path))
        workspace = ConfigurationWorkspace(hass)
        validating, proceed = asyncio.Event(), asyncio.Event()
        calls = 0

        async def validate():
            nonlocal calls
            calls += 1
            if calls == 2:
                validating.set()
                await proceed.wait()
            return {"errors": [], "warnings": []}

        monkeypatch.setattr(workspace, "_validate", validate)
        preview = await workspace.async_preview(
            "admin",
            [
                {
                    "path": "configuration.yaml",
                    "content": "homeassistant:\n  name: New\n",
                }
            ],
        )
        request = asyncio.create_task(
            workspace.async_apply(preview["preview_id"], "admin")
        )
        await validating.wait()
        request.cancel()
        with pytest.raises(asyncio.CancelledError):
            await request
        proceed.set()
        await workspace.async_wait()
        assert workspace.files.backups()[0]["status"] == "applied"
        assert (
            tmp_path / "configuration.yaml"
        ).read_text() == "homeassistant:\n  name: New\n"
        await hass.async_stop(force=True)

    asyncio.run(scenario())


def test_websocket_requires_admin():
    connection = SimpleNamespace(user=SimpleNamespace(is_admin=False))
    with pytest.raises(Unauthorized):
        websocket_configuration(
            SimpleNamespace(),
            connection,
            {
                "id": 1,
                "action": "list",
                "entry_id": "test",
                "type": "landscape/configuration",
            },
        )


def test_unloaded_entry_exposes_nothing():
    async def scenario():
        connection = SimpleNamespace(
            user=SimpleNamespace(id="admin", is_admin=True),
            send_error=Mock(),
            send_result=Mock(),
        )
        handler = websocket_configuration
        while hasattr(handler, "__wrapped__"):
            handler = handler.__wrapped__
        await handler(
            SimpleNamespace(data={}),
            connection,
            {"id": 1, "action": "list", "entry_id": "missing"},
        )
        connection.send_error.assert_called_once()
        connection.send_result.assert_not_called()

    asyncio.run(scenario())


def test_native_ha_repair_and_invalid_schema_rollback(tmp_path):
    async def scenario():
        (tmp_path / "configuration.yaml").write_text("homeassistant: [\n")
        hass = HomeAssistant(str(tmp_path))
        loader.async_setup(hass)
        workspace = ConfigurationWorkspace(hass)
        await workspace.async_initialize()
        preview = await workspace.async_preview(
            "admin",
            [
                {
                    "path": "configuration.yaml",
                    "content": "homeassistant:\n  name: New name\n",
                }
            ],
        )
        report = await workspace.async_apply(preview["preview_id"], "admin")
        assert report["status"] == "applied", report
        preview = await workspace.async_preview(
            "admin",
            [
                {
                    "path": "configuration.yaml",
                    "content": "homeassistant:\n  latitude: 500\n",
                }
            ],
        )
        report = await workspace.async_apply(preview["preview_id"], "admin")
        assert report["status"] == "rolled_back", report
        assert (
            tmp_path / "configuration.yaml"
        ).read_text() == "homeassistant:\n  name: New name\n"
        await hass.async_stop(force=True)

    asyncio.run(scenario())


@pytest.mark.parametrize(
    "target,content,marker",
    [
        (
            "automations.yaml",
            "- id: broken\n  alias: Broken\n  triggers: []\n"
            "  actions:\n    - action: invalid_service_name\n",
            "automation.broken",
        ),
        (
            "scripts.yaml",
            "broken:\n  sequence:\n    - action: invalid_service_name\n",
            "script.broken",
        ),
    ],
)
def test_native_validators_catch_disabled_entries(tmp_path, target, content, marker):
    async def scenario():
        (tmp_path / "configuration.yaml").write_text(
            "automation: !include automations.yaml\nscript: !include scripts.yaml\n"
        )
        (tmp_path / "automations.yaml").write_text("[]\n")
        (tmp_path / "scripts.yaml").write_text("{}\n")
        original = (tmp_path / target).read_bytes()
        hass = HomeAssistant(str(tmp_path))
        loader.async_setup(hass)
        workspace = ConfigurationWorkspace(hass)
        preview = await workspace.async_preview(
            "admin", [{"path": target, "content": content}]
        )
        report = await workspace.async_apply(preview["preview_id"], "admin")
        assert report["status"] == "rolled_back", report
        assert any(marker in message for message in report["validation"]["warnings"])
        assert (tmp_path / target).read_bytes() == original
        await hass.async_stop(force=True)

    asyncio.run(scenario())
