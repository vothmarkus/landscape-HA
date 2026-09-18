"""HTTP downloads keep exact bytes and names without exposing configuration."""

from __future__ import annotations

import asyncio
import base64
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer
from homeassistant.auth import auth_manager_from_config
from homeassistant.auth.const import GROUP_ID_ADMIN, GROUP_ID_USER
from homeassistant.components.http.auth import async_setup_auth
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import Unauthorized
from homeassistant.helpers import device_registry
from homeassistant.helpers.http import KEY_HASS

from custom_components.landscape import downloads
from custom_components.landscape.assist_api import websocket_assist
from custom_components.landscape.configuration_api import websocket_configuration


def connection(user=None):
    return SimpleNamespace(
        user=user or SimpleNamespace(id="admin", is_admin=True),
        refresh_token_id="session",
        send_result=Mock(),
        send_error=Mock(),
    )


async def call_handler(handler, hass, client, message):
    while hasattr(handler, "__wrapped__"):
        handler = handler.__wrapped__
    await handler(hass, client, message)


def test_real_ha_signed_downloads(tmp_path):
    """Exercise HA authentication, response filenames and session revocation."""

    async def scenario():
        hass = HomeAssistant(str(tmp_path))
        device_registry.async_setup(hass)
        await device_registry.async_load(hass)
        hass.auth = await auth_manager_from_config(hass, [], [])
        owner = await hass.auth.async_create_user("Owner", group_ids=[GROUP_ID_ADMIN])
        other = await hass.auth.async_create_user("Other", group_ids=[GROUP_ID_ADMIN])
        regular = await hass.auth.async_create_user("User", group_ids=[GROUP_ID_USER])
        token = await hass.auth.async_create_refresh_token(owner, client_id="test")
        client = connection(owner)
        client.refresh_token_id = token.id
        app = web.Application()
        app[KEY_HASS] = hass
        await async_setup_auth(hass, app)
        downloads.LandscapeDownloadView(hass).register(hass, app, app.router)
        try:
            async with TestClient(TestServer(app)) as http:
                for filename, mime, payload in [
                    (
                        "configuration.yaml",
                        "application/yaml",
                        b"\xef\xbb\xbf# HA\r\ndefault_config:\r\n",
                    ),
                    (
                        "gaszähler #1?100%_2026-09-17.yml",
                        "application/yaml",
                        "# Grüße\n{}\n".encode(),
                    ),
                    ("configuration.zip", "application/zip", b"PK\x03\x04\x00\xff"),
                    (
                        "assist_apply_report.json",
                        "application/json",
                        b'{"status":"applied"}',
                    ),
                ]:
                    result = downloads.async_export_download(
                        hass,
                        client,
                        {
                            "filename": filename,
                            "content": base64.b64encode(payload).decode(),
                            "file_count": 1,
                        },
                        mime,
                    )
                    assert "content" not in result
                    assert result["file_count"] == 1
                    url = result["download_url"]
                    response = await http.get(url)
                    assert response.status == 200
                    assert await response.read() == payload
                    assert response.content_type == mime
                    assert response.content_disposition.filename == filename
                    assert response.content_disposition.type == "attachment"
                    assert response.headers["Cache-Control"] == "no-store, private"
                    assert response.headers["X-Content-Type-Options"] == "nosniff"
                    assert (await http.head(url)).status == 200
                    # A HEAD request must not consume the subsequent download.
                    assert await (await http.get(url)).read() == payload
                path = url.split("?", 1)[0]
                assert (await http.get(path)).status == 401
                assert (await http.get(url.replace(".json?", ".yaml?"))).status == 401
                for user, expected in [(other, 404), (regular, 403)]:
                    user_token = await hass.auth.async_create_refresh_token(
                        user, client_id="test"
                    )
                    bearer = hass.auth.async_create_access_token(user_token)
                    assert (
                        await http.get(
                            url, headers={"Authorization": f"Bearer {bearer}"}
                        )
                    ).status == expected
                store = hass.data[downloads.DATA_DOWNLOADS]
                last_id = next(reversed(store.items))
                store.items[last_id].expires = 0
                assert (await http.get(url)).status == 404
                assert last_id not in store.items
                renewed = downloads.async_prepare_download(
                    hass, client, "configuration.yaml", b"{}", "application/yaml"
                )
                hass.auth.async_remove_refresh_token(token)
                assert (await http.get(renewed["download_url"])).status == 401
        finally:
            await hass.async_stop(force=True)

    asyncio.run(scenario())


def test_download_memory_and_timer_limits(tmp_path, monkeypatch):
    async def scenario():
        hass = HomeAssistant(str(tmp_path))
        store = downloads.DownloadStore(hass)
        monkeypatch.setattr(downloads, "MAX_DOWNLOADS", 2)
        monkeypatch.setattr(downloads, "MAX_DOWNLOAD_BYTES", 8)
        first = store.add("one.yaml", b"1234", "application/yaml", "admin")
        first_timer = store._timers[first]
        store.add("two.yaml", b"1234", "application/yaml", "admin")
        third = store.add("three.yaml", b"1234", "application/yaml", "admin")
        assert first not in store.items
        assert first_timer.cancelled()
        assert len(store.items) == 2
        store.items[third].expires = 0
        store.add("four.yaml", b"12345678", "application/yaml", "admin")
        assert len(store.items) == 1
        with pytest.raises(downloads.DownloadError):
            store.add("large.yaml", b"123456789", "application/yaml", "admin")
        # Timers remove abandoned bytes without requiring another HTTP request.
        monkeypatch.setattr(downloads, "DOWNLOAD_TTL", 0.01)
        short = store.add("short.yaml", b"1234", "application/yaml", "admin")
        await asyncio.sleep(0.02)
        assert short not in store.items
        await hass.async_stop(force=True)

    asyncio.run(scenario())


@pytest.mark.parametrize(
    "filename",
    [
        "../configuration.yaml",
        "dir/test.yaml",
        "dir\\test.yaml",
        "bad\r\n.yaml",
        "config.txt",
    ],
)
def test_download_names_cannot_inject_paths_or_headers(tmp_path, filename):
    async def scenario():
        hass = HomeAssistant(str(tmp_path))
        with pytest.raises(downloads.DownloadError):
            downloads.async_prepare_download(
                hass, connection(), filename, b"{}", "application/yaml"
            )
        assert not hass.data[downloads.DATA_DOWNLOADS].items
        await hass.async_stop(force=True)

    asyncio.run(scenario())


def test_downloads_require_admin_session(tmp_path):
    async def scenario():
        hass = HomeAssistant(str(tmp_path))
        for is_admin, session in [(False, "session"), (True, None)]:
            client = connection(SimpleNamespace(id="user", is_admin=is_admin))
            client.refresh_token_id = session
            with pytest.raises(downloads.DownloadError):
                downloads.async_prepare_download(
                    hass, client, "test.yaml", b"{}", "application/yaml"
                )
        with pytest.raises(Unauthorized):
            downloads.websocket_download_report(
                hass, connection(SimpleNamespace(is_admin=False)), {}
            )
        await hass.async_stop(force=True)

    asyncio.run(scenario())


def test_export_apis_and_reports_use_named_downloads(tmp_path):
    async def scenario():
        hass = HomeAssistant(str(tmp_path))
        client = connection()
        for api, attribute, handler, filename in [
            (
                "configuration",
                "configuration",
                websocket_configuration,
                "configuration.yaml",
            ),
            ("assist", "assist", websocket_assist, "assist_landscape.zip"),
        ]:
            result = {
                "filename": filename,
                "content": base64.b64encode(b"{}\r\n").decode(),
                "mime": downloads.MIME_TYPES[filename.rsplit(".", 1)[-1]],
            }
            workspace = SimpleNamespace(
                async_read=AsyncMock(return_value=result),
                async_export=AsyncMock(return_value=result),
            )
            hass.data["landscape"] = {
                "entry": SimpleNamespace(**{attribute: workspace})
            }
            message = {
                "id": 1,
                "entry_id": "entry",
                "action": "export",
                "download": True,
            }
            await call_handler(handler, hass, client, message)
            download = client.send_result.call_args.args[1]
            assert download["filename"] == filename
            assert download["download_url"].startswith("/api/landscape/download/")
            assert "content" not in download
            # A cached older frontend can still use the original export response.
            message.pop("download")
            await call_handler(handler, hass, client, message)
            assert client.send_result.call_args.args[1] == result
            await call_handler(
                downloads.websocket_download_report,
                hass,
                client,
                {"id": 2, "kind": api, "report": '{"status":"applied"}'},
            )
            report = client.send_result.call_args.args[1]
            assert report["filename"].endswith("report.json")
            assert report["download_url"].startswith("/api/landscape/download/")
            assert client.send_error.call_count == 0
        await hass.async_stop(force=True)

    asyncio.run(scenario())
