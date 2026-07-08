"""Per-output routing selects for the OREI HDMI Matrix.

Kept for automation-friendliness and backward compatibility: each output gets a
`select` whose options are the input names and whose value is the current route.
"""
from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    CONF_ENABLE_SELECT,
    DEFAULT_ENABLE_SELECT,
    DOMAIN,
    input_name,
    input_names,
    output_name,
)
from .entity import OreiBaseEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    if not entry.options.get(CONF_ENABLE_SELECT, DEFAULT_ENABLE_SELECT):
        return
    store = hass.data[DOMAIN][entry.entry_id]
    coordinator = store["coordinator"]
    async_add_entities(
        OreiRouteSelect(coordinator, entry, store["client"], out, store["num_inputs"])
        for out in range(1, store["num_outputs"] + 1)
    )


class OreiRouteSelect(OreiBaseEntity, SelectEntity):
    """Selects which input is routed to a given output."""

    _attr_icon = "mdi:video-input-hdmi"

    def __init__(self, coordinator, entry, client, output: int, num_inputs: int) -> None:
        super().__init__(coordinator, entry)
        self._client = client
        self._output = output
        self._num_inputs = num_inputs
        self._attr_unique_id = f"{entry.entry_id}_route_{output}"
        self._attr_name = f"{output_name(entry, output)} source"

    @property
    def options(self) -> list[str]:
        return input_names(self._entry, self._num_inputs)

    @property
    def current_option(self) -> str | None:
        routing = (self.coordinator.data or {}).get("routing", {})
        in_id = routing.get(self._output)
        if in_id is None:
            return None
        return input_name(self._entry, in_id)

    async def async_select_option(self, option: str) -> None:
        try:
            in_id = self.options.index(option) + 1
        except ValueError:
            return
        await self._client.set_route(in_id, self._output)
        await self.coordinator.async_request_refresh()
