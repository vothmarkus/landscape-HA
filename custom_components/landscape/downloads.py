"""Short-lived, authenticated downloads with filenames for companion apps."""

from __future__ import annotations

import base64
import re
from dataclasses import dataclass
from datetime import timedelta
from time import monotonic
from urllib.parse import quote
from uuid import uuid4

import voluptuous as vol
from aiohttp import web
from homeassistant.components import websocket_api
from homeassistant.components.http import HomeAssistantView
from homeassistant.components.http.auth import async_sign_path
from homeassistant.components.http.const import KEY_HASS_USER
from homeassistant.core import HomeAssistant, callback

DATA_DOWNLOADS = "landscape_downloads"
DOWNLOAD_TTL = 300
MAX_DOWNLOADS = 10
MAX_DOWNLOAD_BYTES = 20_000_000
MIME_TYPES = {
    "yaml": "application/yaml",
    "yml": "application/yaml",
    "zip": "application/zip",
    "json": "application/json",
}


class DownloadError(ValueError):
    """A download cannot be prepared."""


@dataclass
class Download:
    filename: str
    content: bytes
    mime: str
    user_id: str
    expires: float


class DownloadStore:
    """Bound memory use; expire bytes even if no subsequent request arrives."""

    def __init__(self, hass: HomeAssistant) -> None:
        self.hass = hass
        self.items: dict[str, Download] = {}
        self._timers = {}

    def remove(self, download_id: str) -> None:
        self.items.pop(download_id, None)
        if timer := self._timers.pop(download_id, None):
            timer.cancel()

    def add(self, filename: str, content: bytes, mime: str, user_id: str) -> str:
        if (
            not filename
            or len(filename) > 255
            or any(char in filename for char in "/\\")
            or any(ord(char) < 32 or ord(char) == 127 for char in filename)
            or MIME_TYPES.get(filename.rsplit(".", 1)[-1].lower()) != mime
        ):
            raise DownloadError("Ungültiger Download-Dateiname oder Dateityp.")
        if len(content) > MAX_DOWNLOAD_BYTES:
            raise DownloadError("Download darf höchstens 20 MB groß sein.")
        for key, item in list(self.items.items()):
            if item.expires <= monotonic():
                self.remove(key)
        while self.items and (
            len(self.items) >= MAX_DOWNLOADS
            or sum(len(item.content) for item in self.items.values()) + len(content)
            > MAX_DOWNLOAD_BYTES
        ):
            self.remove(next(iter(self.items)))
        download_id = uuid4().hex
        self.items[download_id] = Download(
            filename, content, mime, user_id, monotonic() + DOWNLOAD_TTL
        )
        self._timers[download_id] = self.hass.loop.call_later(
            DOWNLOAD_TTL, self.remove, download_id
        )
        return download_id


@callback
def async_prepare_download(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    filename: str,
    content: bytes,
    mime: str,
) -> dict:
    """Sign only this download for the requesting administrator's session."""
    if not connection.user.is_admin or not connection.refresh_token_id:
        raise DownloadError("Bitte als Administrator neu anmelden.")
    if DATA_DOWNLOADS not in hass.data:
        hass.data[DATA_DOWNLOADS] = DownloadStore(hass)
    store = hass.data[DATA_DOWNLOADS]
    download_id = store.add(filename, content, mime, connection.user.id)
    # HA's signer returns a decoded path. Keep URL delimiters out of that path;
    # Content-Disposition still carries the complete original Unicode filename.
    url_filename = re.sub(r"[^a-zA-Z0-9._-]", "_", filename)
    path = f"/api/landscape/download/{download_id}/{url_filename}"
    return {
        "filename": filename,
        "download_url": async_sign_path(
            hass,
            path,
            timedelta(seconds=DOWNLOAD_TTL),
            refresh_token_id=connection.refresh_token_id,
        ),
    }


@callback
def async_export_download(hass, connection, result: dict, mime: str) -> dict:
    """Keep export metadata; transfer the exact bytes over HTTP instead of a blob."""
    download = async_prepare_download(
        hass,
        connection,
        result["filename"],
        base64.b64decode(result["content"], validate=True),
        mime,
    )
    return {key: value for key, value in result.items() if key != "content"} | download


class LandscapeDownloadView(HomeAssistantView):
    """Serve prepared bytes, never a caller-selected filesystem path."""

    url = "/api/landscape/download/{download_id}/{filename}"
    name = "api:landscape:download"
    requires_auth = True

    def __init__(self, hass: HomeAssistant) -> None:
        self.hass = hass

    @callback
    def get(
        self, request: web.Request, download_id: str, filename: str
    ) -> web.Response:
        user = request.get(KEY_HASS_USER)
        if user is None or not user.is_admin:
            raise web.HTTPForbidden
        store = self.hass.data.get(DATA_DOWNLOADS)
        item = store.items.get(download_id) if store else None
        if item is None:
            raise web.HTTPNotFound
        if item.expires <= monotonic():
            store.remove(download_id)
            raise web.HTTPNotFound
        fallback = re.sub(r"[^a-zA-Z0-9._-]", "_", item.filename)
        if item.user_id != user.id or filename != fallback:
            raise web.HTTPNotFound
        disposition = (
            f'attachment; filename="{fallback}"; '
            f"filename*=UTF-8''{quote(item.filename, safe='')}"
        )
        return web.Response(
            body=item.content,
            content_type=item.mime,
            headers={
                "Content-Disposition": disposition,
                "Cache-Control": "no-store, private",
                "X-Content-Type-Options": "nosniff",
            },
        )

    head = get


@websocket_api.websocket_command(
    {
        vol.Required("type"): "landscape/download_report",
        vol.Required("kind"): vol.In(["assist", "configuration"]),
        vol.Required("report"): vol.All(str, vol.Length(max=2_000_000)),
    }
)
@websocket_api.require_admin
@websocket_api.async_response
async def websocket_download_report(hass, connection, msg) -> None:
    """Download the displayed report, including after its preview has expired."""
    filename = (
        "assist_apply_report.json"
        if msg["kind"] == "assist"
        else "landscape_configuration_report.json"
    )
    try:
        result = async_prepare_download(
            hass,
            connection,
            filename,
            msg["report"].encode("utf-8"),
            "application/json",
        )
    except DownloadError as err:
        connection.send_error(msg["id"], "download_error", str(err))
        return
    connection.send_result(msg["id"], result)
