"""Per-output 'cycle source' buttons for the OREI HDMI Matrix (optional)."""
from __future__ import annotations

import logging

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    CONF_ENABLE_BUTTON,
    DEFAULT_ENABLE_BUTTON,
    DOMAIN,
    output_name,
)
from .entity import OreiBaseEntity

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    if not entry.options.get(CONF_ENABLE_BUTTON, DEFAULT_ENABLE_BUTTON):
        return
    store = hass.data[DOMAIN][entry.entry_id]
    coordinator = store["coordinator"]
    async_add_entities(
        OreiCycleButton(coordinator, entry, store["client"], out, store["num_inputs"])
        for out in range(1, store["num_outputs"] + 1)
    )


class OreiCycleButton(OreiBaseEntity, ButtonEntity):
    """Cycles a given output to the next input."""

    _attr_icon = "mdi:skip-next"

    def __init__(self, coordinator, entry, client, output: int, num_inputs: int) -> None:
        super().__init__(coordinator, entry)
        self._client = client
        self._output = output
        self._num_inputs = num_inputs
        self._attr_unique_id = f"{entry.entry_id}_cycle_{output}"
        self._attr_name = f"{output_name(entry, output, self._dev_output_names)} next source"

    async def async_press(self) -> None:
        routing = (self.coordinator.data or {}).get("routing", {})
        current = routing.get(self._output, 0)
        nxt = (current % self._num_inputs) + 1
        await self._client.set_route(nxt, self._output)
        await self.coordinator.async_request_refresh()
