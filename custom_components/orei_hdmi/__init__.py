"""OREI HDMI Matrix integration."""
from __future__ import annotations

import json
import logging
from pathlib import Path

import voluptuous as vol

from homeassistant.components.frontend import add_extra_js_url
from homeassistant.components.http import StaticPathConfig
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv

from .const import (
    CONF_CEC_PORT,
    CONF_HOST,
    CONF_HTTP_PORT,
    CONF_PORT,
    CONF_SCAN_INTERVAL,
    CONF_TRANSPORT,
    DEFAULT_CEC_PORT,
    DEFAULT_HTTP_PORT,
    DEFAULT_PORT,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    SCALER_MODES,
    SERVICE_CLEAR_PRESET,
    SERVICE_CYCLE_SOURCE,
    SERVICE_RECALL_PRESET,
    SERVICE_REFRESH,
    SERVICE_RENAME_PRESET,
    SERVICE_SAVE_PRESET,
    SERVICE_SET_ARC,
    SERVICE_SET_BEEP,
    SERVICE_SET_CEC,
    SERVICE_SET_EDID,
    SERVICE_SET_PANEL_LOCK,
    SERVICE_SET_ROUTE,
    SERVICE_SET_SCALER,
    TRANSPORT_TELNET,
)
from .coordinator import OreiHdmiCoordinator, build_client

_LOGGER = logging.getLogger(__name__)

PLATFORMS = ["switch", "select", "media_player", "button", "binary_sensor"]

CARD_JS = "orei-hdmi-card.js"
CARD_URL = f"/{DOMAIN}/{CARD_JS}"


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Serve and register the companion Lovelace card automatically."""
    card_path = Path(__file__).parent / CARD_JS
    if not card_path.exists():
        return True

    manifest = json.loads((Path(__file__).parent / "manifest.json").read_text())
    versioned_url = f"{CARD_URL}?v={manifest.get('version', '0')}"

    try:
        await hass.http.async_register_static_paths(
            [StaticPathConfig(CARD_URL, str(card_path), False)]
        )
    except Exception:  # noqa: BLE001
        _LOGGER.debug("Could not register static path for the Lovelace card")

    # Primary: a real Lovelace resource (survives restarts).
    await _register_card_resource(hass, versioned_url)
    # Fallback: inject immediately so the card is usable before a refresh.
    try:
        add_extra_js_url(hass, versioned_url)
    except Exception:  # noqa: BLE001
        pass
    return True


async def _register_card_resource(hass: HomeAssistant, url: str) -> None:
    """Add/refresh the card in Lovelace resources if not already present."""
    try:
        resources = hass.data.get("lovelace", {})
        resources = getattr(resources, "resources", None) or (
            resources.get("resources") if isinstance(resources, dict) else None
        )
        if resources is None:
            return
        if getattr(resources, "loaded", True) is False and hasattr(resources, "async_load"):
            await resources.async_load()

        for item in resources.async_items():
            existing = item.get("url", "")
            if DOMAIN in existing and CARD_JS in existing:
                if existing != url:
                    await resources.async_update_item(item["id"], {"url": url})
                return
        await resources.async_create_item({"res_type": "module", "url": url})
        _LOGGER.info("Registered Lovelace resource: %s", url)
    except Exception:  # noqa: BLE001
        _LOGGER.debug("Could not auto-register Lovelace resource", exc_info=True)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up OREI HDMI Matrix from a config entry."""
    host = entry.data[CONF_HOST]
    telnet_port = entry.data.get(CONF_PORT, DEFAULT_PORT)
    http_port = entry.data.get(CONF_HTTP_PORT, DEFAULT_HTTP_PORT)
    cec_port = entry.options.get(
        CONF_CEC_PORT, entry.data.get(CONF_CEC_PORT, DEFAULT_CEC_PORT)
    )
    transport = entry.data.get(CONF_TRANSPORT, TRANSPORT_TELNET)
    scan_interval = entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)

    num_inputs = entry.data.get("inputs") or 8
    num_outputs = entry.data.get("outputs") or 8

    client = build_client(
        hass, transport, host, telnet_port, http_port, cec_port, num_inputs, num_outputs
    )
    coordinator = OreiHdmiCoordinator(hass, client, scan_interval)
    coordinator.model = entry.data.get("model") or "Unknown"

    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
        "client": client,
        "coordinator": coordinator,
        "num_inputs": num_inputs,
        "num_outputs": num_outputs,
    }

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))

    _async_register_services(hass)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        stored = hass.data[DOMAIN].pop(entry.entry_id, None)
        if stored:
            await stored["client"].disconnect()
        if not hass.data[DOMAIN]:
            _async_unregister_services(hass)
    return unloaded


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload the entry when its options change."""
    await hass.config_entries.async_reload(entry.entry_id)


# --- Services -----------------------------------------------------------------
def _pick_entry(hass: HomeAssistant, host: str | None):
    entries = hass.data.get(DOMAIN, {})
    if not entries:
        raise HomeAssistantError("No OREI HDMI Matrix is configured")
    if host:
        for stored in entries.values():
            if stored["client"].host == host:
                return stored
        raise HomeAssistantError(f"No OREI HDMI Matrix found with host {host}")
    if len(entries) > 1:
        raise HomeAssistantError(
            "Multiple matrices configured; specify 'host' in the service call"
        )
    return next(iter(entries.values()))


def _async_register_services(hass: HomeAssistant) -> None:
    if hass.services.has_service(DOMAIN, SERVICE_REFRESH):
        return

    async def handle_refresh(call: ServiceCall) -> None:
        for stored in hass.data.get(DOMAIN, {}).values():
            await stored["coordinator"].async_request_refresh()

    async def handle_set_route(call: ServiceCall) -> None:
        stored = _pick_entry(hass, call.data.get("host"))
        await stored["client"].set_route(call.data["input"], call.data["output"])
        await stored["coordinator"].async_request_refresh()

    async def handle_set_cec(call: ServiceCall) -> None:
        stored = _pick_entry(hass, call.data.get("host"))
        client = stored["client"]
        if call.data["target"] == "input":
            await client.set_cec_input(call.data["id"], call.data["command"])
        else:
            await client.set_cec_output(call.data["id"], call.data["command"])

    async def handle_cycle_source(call: ServiceCall) -> None:
        stored = _pick_entry(hass, call.data.get("host"))
        client = stored["client"]
        coordinator = stored["coordinator"]
        routing = (coordinator.data or {}).get("routing", {})
        output = call.data["output"]
        num_inputs = int(stored.get("num_inputs") or 8)
        current = routing.get(output, 0)
        nxt = (current % num_inputs) + 1
        await client.set_route(nxt, output)
        await coordinator.async_request_refresh()

    async def handle_recall_preset(call: ServiceCall) -> None:
        stored = _pick_entry(hass, call.data.get("host"))
        await stored["client"].recall_preset(call.data["index"])
        stored["coordinator"].last_preset = call.data["index"]
        await stored["coordinator"].async_request_refresh()

    async def handle_save_preset(call: ServiceCall) -> None:
        stored = _pick_entry(hass, call.data.get("host"))
        await stored["client"].save_preset(call.data["index"], call.data.get("name"))
        await stored["coordinator"].async_request_refresh()

    async def handle_clear_preset(call: ServiceCall) -> None:
        stored = _pick_entry(hass, call.data.get("host"))
        await stored["client"].clear_preset(call.data["index"])
        await stored["coordinator"].async_request_refresh()

    async def handle_rename_preset(call: ServiceCall) -> None:
        stored = _pick_entry(hass, call.data.get("host"))
        await stored["client"].rename_preset(call.data["index"], call.data["name"])
        await stored["coordinator"].async_request_refresh()

    async def handle_set_scaler(call: ServiceCall) -> None:
        stored = _pick_entry(hass, call.data.get("host"))
        mode = call.data["mode"]
        if isinstance(mode, str):
            mode = SCALER_MODES.get(mode.strip().lower())
            if mode is None:
                raise HomeAssistantError(
                    f"Unknown scaler mode; use one of {', '.join(SCALER_MODES)}"
                )
        await stored["client"].set_scaler(call.data["output"], mode)
        await stored["coordinator"].async_request_refresh()

    async def handle_set_edid(call: ServiceCall) -> None:
        stored = _pick_entry(hass, call.data.get("host"))
        await stored["client"].set_edid(call.data["input"], call.data["mode"])
        await stored["coordinator"].async_request_refresh()

    async def handle_set_arc(call: ServiceCall) -> None:
        stored = _pick_entry(hass, call.data.get("host"))
        await stored["client"].set_arc(call.data["output"], call.data["enabled"])
        await stored["coordinator"].async_request_refresh()

    async def handle_set_panel_lock(call: ServiceCall) -> None:
        stored = _pick_entry(hass, call.data.get("host"))
        await stored["client"].set_panel_lock(call.data["locked"])
        await stored["coordinator"].async_request_refresh()

    async def handle_set_beep(call: ServiceCall) -> None:
        stored = _pick_entry(hass, call.data.get("host"))
        await stored["client"].set_beep(call.data["enabled"])
        await stored["coordinator"].async_request_refresh()

    hass.services.async_register(
        DOMAIN, SERVICE_REFRESH, handle_refresh, schema=vol.Schema({})
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_SET_ROUTE,
        handle_set_route,
        schema=vol.Schema(
            {
                vol.Required("input"): cv.positive_int,
                vol.Required("output"): cv.positive_int,
                vol.Optional("host"): cv.string,
            }
        ),
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_SET_CEC,
        handle_set_cec,
        schema=vol.Schema(
            {
                vol.Required("target"): vol.In(["input", "output"]),
                vol.Required("id"): cv.positive_int,
                vol.Required("command"): cv.string,
                vol.Optional("host"): cv.string,
            }
        ),
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_CYCLE_SOURCE,
        handle_cycle_source,
        schema=vol.Schema(
            {
                vol.Required("output"): cv.positive_int,
                vol.Optional("host"): cv.string,
            }
        ),
    )

    _preset_index = vol.All(cv.positive_int, vol.Range(min=1, max=8))
    hass.services.async_register(
        DOMAIN,
        SERVICE_RECALL_PRESET,
        handle_recall_preset,
        schema=vol.Schema(
            {vol.Required("index"): _preset_index, vol.Optional("host"): cv.string}
        ),
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_SAVE_PRESET,
        handle_save_preset,
        schema=vol.Schema(
            {
                vol.Required("index"): _preset_index,
                vol.Optional("name"): cv.string,
                vol.Optional("host"): cv.string,
            }
        ),
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_CLEAR_PRESET,
        handle_clear_preset,
        schema=vol.Schema(
            {vol.Required("index"): _preset_index, vol.Optional("host"): cv.string}
        ),
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_RENAME_PRESET,
        handle_rename_preset,
        schema=vol.Schema(
            {
                vol.Required("index"): _preset_index,
                vol.Required("name"): cv.string,
                vol.Optional("host"): cv.string,
            }
        ),
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_SET_SCALER,
        handle_set_scaler,
        schema=vol.Schema(
            {
                vol.Required("output"): cv.positive_int,
                vol.Required("mode"): vol.Any(cv.positive_int, cv.string),
                vol.Optional("host"): cv.string,
            }
        ),
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_SET_EDID,
        handle_set_edid,
        schema=vol.Schema(
            {
                vol.Required("input"): cv.positive_int,
                vol.Required("mode"): vol.All(cv.positive_int, vol.Range(min=1, max=39)),
                vol.Optional("host"): cv.string,
            }
        ),
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_SET_ARC,
        handle_set_arc,
        schema=vol.Schema(
            {
                vol.Required("output"): cv.positive_int,
                vol.Required("enabled"): cv.boolean,
                vol.Optional("host"): cv.string,
            }
        ),
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_SET_PANEL_LOCK,
        handle_set_panel_lock,
        schema=vol.Schema(
            {vol.Required("locked"): cv.boolean, vol.Optional("host"): cv.string}
        ),
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_SET_BEEP,
        handle_set_beep,
        schema=vol.Schema(
            {vol.Required("enabled"): cv.boolean, vol.Optional("host"): cv.string}
        ),
    )


def _async_unregister_services(hass: HomeAssistant) -> None:
    for service in (
        SERVICE_REFRESH,
        SERVICE_SET_ROUTE,
        SERVICE_SET_CEC,
        SERVICE_CYCLE_SOURCE,
        SERVICE_RECALL_PRESET,
        SERVICE_SAVE_PRESET,
        SERVICE_CLEAR_PRESET,
        SERVICE_RENAME_PRESET,
        SERVICE_SET_SCALER,
        SERVICE_SET_EDID,
        SERVICE_SET_ARC,
        SERVICE_SET_PANEL_LOCK,
        SERVICE_SET_BEEP,
    ):
        hass.services.async_remove(DOMAIN, service)
