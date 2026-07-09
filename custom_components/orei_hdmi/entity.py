"""Shared base entity for the OREI HDMI Matrix integration."""
from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_HOST, DOMAIN, MANUFACTURER
from .coordinator import OreiHdmiCoordinator


class OreiBaseEntity(CoordinatorEntity[OreiHdmiCoordinator]):
    """Base class that groups every entity under one device."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: OreiHdmiCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._entry = entry

    @property
    def _model(self) -> str:
        data = self.coordinator.data or {}
        return data.get("model", "Unknown")

    @property
    def _dev_input_names(self) -> dict:
        """Input names reported by the device (empty on telnet)."""
        return (self.coordinator.data or {}).get("input_names", {}) or {}

    @property
    def _dev_output_names(self) -> dict:
        """Output names reported by the device (empty on telnet)."""
        return (self.coordinator.data or {}).get("output_names", {}) or {}

    @property
    def device_info(self) -> dict:
        return {
            "identifiers": {(DOMAIN, self._entry.entry_id)},
            "name": self._entry.title or "OREI HDMI Matrix",
            "manufacturer": MANUFACTURER,
            "model": self._model,
            "sw_version": self._model,
            "configuration_url": f"http://{self._entry.data.get(CONF_HOST)}",
        }
