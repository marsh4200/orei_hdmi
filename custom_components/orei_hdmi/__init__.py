"""OREI HDMI Matrix integration."""
from __future__ import annotations

import logging

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv

from .const import (
    CONF_HOST,
    CONF_PORT,
    CONF_SCAN_INTERVAL,
    DEFAULT_PORT,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    SERVICE_CYCLE_SOURCE,
    SERVICE_REFRESH,
    SERVICE_SET_CEC,
    SERVICE_SET_ROUTE,
)
from .coordinator import OreiHdmiClient, OreiHdmiCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS = ["switch", "select", "media_player", "button", "binary_sensor"]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up OREI HDMI Matrix from a config entry."""
    host = entry.data[CONF_HOST]
    port = entry.data.get(CONF_PORT, DEFAULT_PORT)
    scan_interval = entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)

    client = OreiHdmiClient(host, port)
    coordinator = OreiHdmiCoordinator(hass, client, scan_interval)
    coordinator.model = entry.data.get("model") or "Unknown"

    await coordinator.async_config_entry_first_refresh()

    num_inputs = entry.data.get("inputs") or 8
    num_outputs = entry.data.get("outputs") or 8

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
    """Return a stored entry dict, disambiguating by host if given."""
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

    hass.services.async_register(
        DOMAIN,
        SERVICE_REFRESH,
        handle_refresh,
        schema=vol.Schema({}),
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


def _async_unregister_services(hass: HomeAssistant) -> None:
    for service in (
        SERVICE_REFRESH,
        SERVICE_SET_ROUTE,
        SERVICE_SET_CEC,
        SERVICE_CYCLE_SOURCE,
    ):
        hass.services.async_remove(DOMAIN, service)
