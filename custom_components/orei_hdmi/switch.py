"""Power switch for the OREI HDMI Matrix."""
from __future__ import annotations

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .entity import OreiBaseEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    store = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([OreiPowerSwitch(store["coordinator"], entry, store["client"])])


class OreiPowerSwitch(OreiBaseEntity, SwitchEntity):
    """Master power for the matrix."""

    _attr_name = "Power"
    _attr_icon = "mdi:power"

    def __init__(self, coordinator, entry, client) -> None:
        super().__init__(coordinator, entry)
        self._client = client
        self._attr_unique_id = f"{entry.entry_id}_power"

    @property
    def is_on(self) -> bool | None:
        data = self.coordinator.data or {}
        return data.get("power")

    async def async_turn_on(self, **kwargs) -> None:
        await self._client.set_power(True)
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs) -> None:
        await self._client.set_power(False)
        await self.coordinator.async_request_refresh()
