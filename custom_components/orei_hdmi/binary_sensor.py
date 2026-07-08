"""HDMI link (cable-present) sensors for the OREI HDMI Matrix.

Surfaces the matrix's own connection detection: which input sources and output
displays currently have a live HDMI link.
"""
from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    CONF_ENABLE_LINK_SENSORS,
    DEFAULT_ENABLE_LINK_SENSORS,
    DOMAIN,
    input_name,
    output_name,
)
from .entity import OreiBaseEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    if not entry.options.get(CONF_ENABLE_LINK_SENSORS, DEFAULT_ENABLE_LINK_SENSORS):
        return
    store = hass.data[DOMAIN][entry.entry_id]
    coordinator = store["coordinator"]

    entities: list[OreiLinkSensor] = []
    for i in range(1, store["num_inputs"] + 1):
        entities.append(OreiLinkSensor(coordinator, entry, "in", i))
    for o in range(1, store["num_outputs"] + 1):
        entities.append(OreiLinkSensor(coordinator, entry, "out", o))
    async_add_entities(entities)


class OreiLinkSensor(OreiBaseEntity, BinarySensorEntity):
    """Connectivity sensor for one input source or output display."""

    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY

    def __init__(self, coordinator, entry, side: str, index: int) -> None:
        super().__init__(coordinator, entry)
        self._side = side  # "in" or "out"
        self._index = index
        self._attr_unique_id = f"{entry.entry_id}_link_{side}_{index}"
        if side == "in":
            self._attr_name = f"{input_name(entry, index)} link"
            self._attr_icon = "mdi:import"
        else:
            self._attr_name = f"{output_name(entry, index)} link"
            self._attr_icon = "mdi:export"

    @property
    def is_on(self) -> bool | None:
        data = self.coordinator.data or {}
        key = "in_links" if self._side == "in" else "out_links"
        return data.get(key, {}).get(self._index)
