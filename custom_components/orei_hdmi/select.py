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
    CONF_ENABLE_PRESETS,
    CONF_ENABLE_SELECT,
    DEFAULT_ENABLE_PRESETS,
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
    store = hass.data[DOMAIN][entry.entry_id]
    coordinator = store["coordinator"]
    entities = []
    if entry.options.get(CONF_ENABLE_SELECT, DEFAULT_ENABLE_SELECT):
        entities.extend(
            OreiRouteSelect(coordinator, entry, store["client"], out, store["num_inputs"])
            for out in range(1, store["num_outputs"] + 1)
        )
    # Preset recall — only meaningful when the device reports presets (HTTP).
    if entry.options.get(CONF_ENABLE_PRESETS, DEFAULT_ENABLE_PRESETS):
        if (coordinator.data or {}).get("presets"):
            entities.append(OreiPresetSelect(coordinator, entry, store["client"]))
    async_add_entities(entities)


class OreiRouteSelect(OreiBaseEntity, SelectEntity):
    """Selects which input is routed to a given output."""

    _attr_icon = "mdi:video-input-hdmi"

    def __init__(self, coordinator, entry, client, output: int, num_inputs: int) -> None:
        super().__init__(coordinator, entry)
        self._client = client
        self._output = output
        self._num_inputs = num_inputs
        self._attr_unique_id = f"{entry.entry_id}_route_{output}"
        self._attr_name = f"{output_name(entry, output, self._dev_output_names)} source"

    @property
    def options(self) -> list[str]:
        return input_names(self._entry, self._num_inputs, self._dev_input_names)

    @property
    def current_option(self) -> str | None:
        routing = (self.coordinator.data or {}).get("routing", {})
        in_id = routing.get(self._output)
        if in_id is None:
            return None
        return input_name(self._entry, in_id, self._dev_input_names)

    async def async_select_option(self, option: str) -> None:
        try:
            in_id = self.options.index(option) + 1
        except ValueError:
            return
        await self._client.set_route(in_id, self._output)
        await self.coordinator.async_request_refresh()


class OreiPresetSelect(OreiBaseEntity, SelectEntity):
    """Recall a saved routing preset by name."""

    _attr_icon = "mdi:content-save-settings"

    def __init__(self, coordinator, entry, client) -> None:
        super().__init__(coordinator, entry)
        self._client = client
        self._attr_unique_id = f"{entry.entry_id}_preset"
        self._attr_name = "Preset"

    def _presets(self) -> dict:
        return (self.coordinator.data or {}).get("presets", {}) or {}

    @property
    def options(self) -> list[str]:
        return [self._presets()[k] for k in sorted(self._presets())]

    @property
    def current_option(self) -> str | None:
        last = (self.coordinator.data or {}).get("last_preset")
        return self._presets().get(last) if last else None

    async def async_select_option(self, option: str) -> None:
        for idx, name in self._presets().items():
            if name == option:
                await self._client.recall_preset(idx)
                self.coordinator.last_preset = idx
                await self.coordinator.async_request_refresh()
                return
