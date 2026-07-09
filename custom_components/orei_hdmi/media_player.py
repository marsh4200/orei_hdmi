"""Per-zone media players for the OREI HDMI Matrix.

Each output is exposed as a media_player whose source list is the matrix's
inputs. Turn on/off issues a CEC power command to the display on that output.
Rich per-output data (HDCP/HDR/scaler/ARC/mute/EDID) rides along as attributes.
"""
from __future__ import annotations

import logging

from homeassistant.components.media_player import (
    MediaPlayerEntity,
    MediaPlayerEntityFeature,
    MediaPlayerState,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    CONF_ENABLE_MEDIA_PLAYER,
    CONF_HOST,
    DEFAULT_ENABLE_MEDIA_PLAYER,
    DOMAIN,
    SCALER_MODE_NAMES,
    input_name,
    input_names,
    output_name,
)
from .entity import OreiBaseEntity

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    if not entry.options.get(CONF_ENABLE_MEDIA_PLAYER, DEFAULT_ENABLE_MEDIA_PLAYER):
        return
    store = hass.data[DOMAIN][entry.entry_id]
    coordinator = store["coordinator"]
    async_add_entities(
        OreiZoneMediaPlayer(coordinator, entry, store["client"], out, store["num_inputs"])
        for out in range(1, store["num_outputs"] + 1)
    )


class OreiZoneMediaPlayer(OreiBaseEntity, MediaPlayerEntity):
    """One HDMI output presented as a source-selecting media player."""

    _attr_icon = "mdi:television"
    _attr_supported_features = (
        MediaPlayerEntityFeature.SELECT_SOURCE
        | MediaPlayerEntityFeature.TURN_ON
        | MediaPlayerEntityFeature.TURN_OFF
    )

    def __init__(self, coordinator, entry, client, output: int, num_inputs: int) -> None:
        super().__init__(coordinator, entry)
        self._client = client
        self._output = output
        self._num_inputs = num_inputs
        self._attr_unique_id = f"{entry.entry_id}_zone_{output}"
        self._attr_name = output_name(entry, output, self._dev_output_names)

    @property
    def source_list(self) -> list[str]:
        return input_names(self._entry, self._num_inputs, self._dev_input_names)

    @property
    def _routed_input(self) -> int | None:
        routing = (self.coordinator.data or {}).get("routing", {})
        return routing.get(self._output)

    @property
    def source(self) -> str | None:
        in_id = self._routed_input
        return input_name(self._entry, in_id, self._dev_input_names) if in_id else None

    @property
    def state(self) -> MediaPlayerState:
        data = self.coordinator.data or {}
        return MediaPlayerState.ON if data.get("power") else MediaPlayerState.OFF

    @property
    def extra_state_attributes(self) -> dict:
        # Lets the companion Lovelace card auto-discover matrix zones and read
        # the rich per-output data exposed by the HTTP transport.
        data = self.coordinator.data or {}
        o = self._output
        in_id = self._routed_input
        attrs = {
            "orei_hdmi": True,
            "output": o,
            "host": self._entry.data.get(CONF_HOST),
            "display_connected": (data.get("out_links", {}) or {}).get(o),
        }

        def _put(key, src):
            val = (data.get(src, {}) or {}).get(o)
            if val is not None:
                attrs[key] = val

        _put("hdr", "hdr")
        _put("hdcp", "hdcp")
        _put("scaler", "scaler")
        _put("arc", "arc")
        _put("audio_muted", "audio_mute")
        _put("output_enabled", "out_enable")
        # EDID belongs to the routed input.
        if in_id is not None:
            edid = (data.get("edid", {}) or {}).get(in_id)
            if edid is not None:
                attrs["input_edid"] = edid
        # Translate scaler code to a label for readability.
        scaler = attrs.get("scaler")
        if scaler is not None:
            attrs["scaler_mode"] = SCALER_MODE_NAMES.get(scaler, str(scaler))
        return attrs

    async def async_select_source(self, source: str) -> None:
        try:
            in_id = self.source_list.index(source) + 1
        except ValueError:
            _LOGGER.warning("Unknown source %s for %s", source, self.name)
            return
        await self._client.set_route(in_id, self._output)
        await self.coordinator.async_request_refresh()

    async def async_turn_on(self) -> None:
        # Power the display on this output via CEC.
        await self._client.set_cec_output(self._output, "on")

    async def async_turn_off(self) -> None:
        await self._client.set_cec_output(self._output, "off")

    @callback
    def _handle_coordinator_update(self) -> None:
        self.async_write_ha_state()
