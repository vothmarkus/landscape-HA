"""Authenticated admin WebSocket commands and the Landscape Assist panel."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import voluptuous as vol
from homeassistant.components import frontend, panel_custom, websocket_api
from homeassistant.components.http import StaticPathConfig
from homeassistant.core import HomeAssistant

from .assist import AssistOptimizer
from .assist_schema import PatchError
from .const import DOMAIN, VERSION

_LOGGER = logging.getLogger(__name__)
PANEL_PATH = "landscape-assist"
STATIC_URL = "/landscape_static/assist-panel.js"
DATA_REGISTERED = "landscape_assist_api_registered"


async def async_setup_panel(hass: HomeAssistant, entry_id: str) -> None:
    """Register public code only; inventory and imports require admin authentication."""
    if not hass.data.get(DATA_REGISTERED):
        await hass.http.async_register_static_paths(
            [
                StaticPathConfig(
                    STATIC_URL,
                    str(Path(__file__).parent / "frontend" / "assist-panel.js"),
                    False,
                )
            ]
        )
        websocket_api.async_register_command(hass, websocket_assist)
        hass.data[DATA_REGISTERED] = True
    await panel_custom.async_register_panel(
        hass,
        frontend_url_path=PANEL_PATH,
        webcomponent_name="landscape-assist-panel",
        sidebar_title="Landscape Assist",
        sidebar_icon="mdi:account-voice",
        module_url=f"{STATIC_URL}?v={VERSION}",
        config={"entry_id": entry_id},
        require_admin=True,
    )


def async_unload_panel(hass: HomeAssistant) -> None:
    """Remove the sidebar; reusable routes resolve the active entry at request time."""
    frontend.async_remove_panel(hass, PANEL_PATH, warn_if_unknown=False)


@websocket_api.websocket_command(
    {
        vol.Required("type"): "landscape/assist",
        vol.Required("entry_id"): str,
        vol.Required("action"): vol.In(
            ["status", "export", "preview", "apply", "discard"]
        ),
        vol.Optional("patch"): str,
        vol.Optional("preview_id"): str,
        vol.Optional("selected"): [str],
    }
)
@websocket_api.require_admin
@websocket_api.async_response
async def websocket_assist(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    """Never accept executable code, arbitrary writes, or client-supplied diff rows."""
    exporter = hass.data.get(DOMAIN, {}).get(msg["entry_id"])
    optimizer: AssistOptimizer | None = getattr(exporter, "assist", None)
    if optimizer is None:
        connection.send_error(
            msg["id"], "not_loaded", "HA Landscape ist nicht geladen."
        )
        return
    user_id = connection.user.id
    action = msg["action"]
    try:
        if action == "status":
            result = optimizer.status()
        elif action == "export":
            result = await optimizer.async_export()
        elif action == "preview":
            if "patch" not in msg:
                raise PatchError("Bitte eine JSON-Importdatei auswählen.")
            result = await optimizer.async_preview(msg["patch"], user_id)
        else:
            if "preview_id" not in msg:
                raise PatchError("Bitte zuerst eine Vorschau erstellen.")
            if action == "apply":
                result = await optimizer.async_apply(
                    msg["preview_id"], msg.get("selected", []), user_id
                )
            else:
                optimizer.discard(msg["preview_id"], user_id)
                result = {"discarded": True}
    except PatchError as err:
        connection.send_error(msg["id"], "invalid_patch", str(err))
        return
    except Exception:
        _LOGGER.exception("Landscape Assist command failed: %s", action)
        connection.send_error(
            msg["id"],
            "assist_error",
            "Die Aktion ist fehlgeschlagen. "
            "Details stehen im Home-Assistant-Protokoll.",
        )
        return
    connection.send_result(msg["id"], result)
