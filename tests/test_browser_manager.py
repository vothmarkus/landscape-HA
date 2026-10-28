"""Verify browser authorization, native checks and serialization with YAML."""

from __future__ import annotations

import asyncio
import base64
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from homeassistant import loader
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import Unauthorized

from custom_components.landscape.browser import BrowserWorkspace
from custom_components.landscape.configuration import ConfigurationWorkspace
from custom_components.landscape.configuration_api import websocket_configuration
from custom_components.landscape.configuration_yaml import ConfigurationError
from custom_components.landscape.downloads import DATA_DOWNLOADS


def test_browser_scope_requires_admin():
    with pytest.raises(Unauthorized):
        websocket_configuration(
            SimpleNamespace(),
            SimpleNamespace(user=SimpleNamespace(is_admin=False)),
            {"scope": "browser", "action": "list"},
        )


def test_browser_native_ha_check_rolls_back_mixed_files(tmp_path):
    async def scenario():
        (tmp_path / "configuration.yaml").write_text("homeassistant:\n  name: Home\n")
        (tmp_path / "note.txt").write_bytes(b"\x00original\xff")
        hass = HomeAssistant(str(tmp_path))
        loader.async_setup(hass)
        configuration = ConfigurationWorkspace(hass)
        browser = BrowserWorkspace(hass, configuration)
        assert browser._lock is configuration._lock
        assert browser._tasks is configuration._tasks
        await browser.async_initialize()
        preview = await browser.async_preview(
            "admin",
            [
                {
                    "path": "configuration.yaml",
                    "content": "homeassistant:\n  latitude: 500\n",
                },
                {"path": "note.txt", "content": "changed"},
            ],
        )
        assert "yaml" not in preview["validation"]
        assert "before" not in preview["files"][0]
        with pytest.raises(ConfigurationError):
            await browser.async_apply(preview["preview_id"], "other-admin")
        report = await browser.async_apply(preview["preview_id"], "admin")
        assert report["status"] == "rolled_back", report
        assert (tmp_path / "note.txt").read_bytes() == b"\x00original\xff"
        assert "latitude" not in (tmp_path / "configuration.yaml").read_text()
        await hass.async_stop(force=True)

    asyncio.run(scenario())


def test_websocket_routes_browser_exports_and_separates_previews(tmp_path):
    async def scenario():
        (tmp_path / "configuration.yaml").write_text("{}\n")
        (tmp_path / "picture.png").write_bytes(b"\x00\xffpicture")
        hass = HomeAssistant(str(tmp_path))
        configuration = ConfigurationWorkspace(hass)
        browser = BrowserWorkspace(hass, configuration)
        hass.data["landscape"] = {
            "entry": SimpleNamespace(configuration=configuration, browser=browser)
        }
        connection = SimpleNamespace(
            user=SimpleNamespace(id="admin", is_admin=True),
            refresh_token_id="session",
            send_error=Mock(),
            send_result=Mock(),
        )
        handler = websocket_configuration
        while hasattr(handler, "__wrapped__"):
            handler = handler.__wrapped__
        await handler(
            hass,
            connection,
            {
                "id": 1,
                "entry_id": "entry",
                "scope": "browser",
                "action": "export",
                "paths": ["picture.png"],
                "download": True,
            },
        )
        connection.send_error.assert_not_called()
        download = connection.send_result.call_args.args[1]
        assert download["filename"] == "picture.png"
        assert "content" not in download
        item = next(iter(hass.data[DATA_DOWNLOADS].items.values()))
        assert item.content == b"\x00\xffpicture"
        assert item.mime == "application/octet-stream"
        preview = await browser.async_preview(
            "admin",
            [
                {
                    "path": "picture.png",
                    "content": base64.b64encode(b"\x00new").decode(),
                    "encoding": "base64",
                }
            ],
        )
        with pytest.raises(ConfigurationError):
            configuration._preview(preview["preview_id"], "admin")
        async with configuration._lock:
            pending = asyncio.create_task(browser.async_read("list"))
            await asyncio.sleep(0)
            assert not pending.done()
        assert (await pending)["files"]
        await hass.async_stop(force=True)

    asyncio.run(scenario())
