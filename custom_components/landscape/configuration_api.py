"""Administrator-only Configuration WebSocket API."""

from __future__ import annotations

import logging

import voluptuous as vol
from homeassistant.components import websocket_api
from homeassistant.core import HomeAssistant

from .configuration_yaml import ConfigurationError
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


@websocket_api.websocket_command(
    {
        vol.Required("type"): "landscape/configuration",
        vol.Required("entry_id"): str,
        vol.Required("action"): vol.In(
            [
                "list",
                "view",
                "export",
                "inspect",
                "preview",
                "apply",
                "discard",
                "restore_preview",
            ]
        ),
        vol.Optional("path"): str,
        vol.Optional("paths"): [str],
        vol.Optional("context"): bool,
        vol.Optional("dated"): bool,
        vol.Optional("files"): [dict],
        vol.Optional("archive"): str,
        vol.Optional("preview_id"): str,
        vol.Optional("backup_id"): str,
    }
)
@websocket_api.require_admin
@websocket_api.async_response
async def websocket_configuration(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict
) -> None:
    exporter = hass.data.get(DOMAIN, {}).get(msg["entry_id"])
    workspace = getattr(exporter, "configuration", None)
    if workspace is None:
        connection.send_error(
            msg["id"], "not_loaded", "HA Landscape ist nicht geladen."
        )
        return
    action = msg["action"]
    try:
        if action in {"list", "view", "export", "inspect"}:
            fields = {
                key: value
                for key, value in msg.items()
                if key not in {"id", "type", "entry_id", "action"}
            }
            result = await workspace.async_read(action, **fields)
        elif action == "preview":
            result = await workspace.async_preview(
                connection.user.id, msg.get("files", [])
            )
        elif action == "restore_preview":
            if not msg.get("backup_id"):
                raise ConfigurationError("Bitte ein Backup auswählen.")
            result = await workspace.async_preview(
                connection.user.id, backup_id=msg["backup_id"]
            )
        else:
            if not msg.get("preview_id"):
                raise ConfigurationError("Bitte zuerst eine Vorschau erstellen.")
            if action == "apply":
                result = await workspace.async_apply(
                    msg["preview_id"], connection.user.id
                )
            else:
                workspace.discard(msg["preview_id"], connection.user.id)
                result = {"discarded": True}
    except (ConfigurationError, KeyError) as err:
        connection.send_error(msg["id"], "invalid_configuration", str(err))
        return
    except Exception:
        _LOGGER.exception("Landscape Configuration action failed: %s", action)
        connection.send_error(
            msg["id"],
            "configuration_error",
            "Aktion fehlgeschlagen. Details stehen im Home-Assistant-Protokoll.",
        )
        return
    connection.send_result(msg["id"], result)
