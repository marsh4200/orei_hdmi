"""Config and options flow for the OREI HDMI Matrix."""
from __future__ import annotations

import logging

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import callback

from .const import (
    CONF_CEC_PORT,
    CONF_ENABLE_BUTTON,
    CONF_ENABLE_LINK_SENSORS,
    CONF_ENABLE_MEDIA_PLAYER,
    CONF_ENABLE_PRESETS,
    CONF_ENABLE_SELECT,
    CONF_HOST,
    CONF_HTTP_PORT,
    CONF_INPUT_NAMES,
    CONF_INPUTS,
    CONF_MODEL,
    CONF_OUTPUT_NAMES,
    CONF_OUTPUTS,
    CONF_PORT,
    CONF_SCAN_INTERVAL,
    CONF_TRANSPORT,
    DEFAULT_CEC_PORT,
    DEFAULT_ENABLE_BUTTON,
    DEFAULT_ENABLE_LINK_SENSORS,
    DEFAULT_ENABLE_MEDIA_PLAYER,
    DEFAULT_ENABLE_PRESETS,
    DEFAULT_ENABLE_SELECT,
    DEFAULT_HTTP_PORT,
    DEFAULT_PORT,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    TRANSPORT_HTTP,
)
from .coordinator import async_probe_transport

_LOGGER = logging.getLogger(__name__)

USER_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST): str,
        vol.Optional(CONF_PORT, default=DEFAULT_PORT): int,
        vol.Optional(CONF_HTTP_PORT, default=DEFAULT_HTTP_PORT): int,
    }
)


class OreiConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle the initial setup."""

    VERSION = 1

    async def async_step_user(self, user_input=None):
        errors: dict[str, str] = {}

        if user_input is not None:
            host = user_input[CONF_HOST].strip()
            telnet_port = user_input.get(CONF_PORT, DEFAULT_PORT)
            http_port = user_input.get(CONF_HTTP_PORT, DEFAULT_HTTP_PORT)

            await self.async_set_unique_id(host)
            self._abort_if_unique_id_configured()

            try:
                transport, model, num_inputs, num_outputs, telnet_port = (
                    await async_probe_transport(
                        self.hass, host, http_port, telnet_port
                    )
                )
            except Exception:  # noqa: BLE001
                errors["base"] = "cannot_connect"
            else:
                return self.async_create_entry(
                    title=model if model != "Unknown" else f"OREI Matrix ({host})",
                    data={
                        CONF_HOST: host,
                        CONF_PORT: telnet_port,
                        CONF_HTTP_PORT: http_port,
                        CONF_CEC_PORT: DEFAULT_CEC_PORT,
                        CONF_TRANSPORT: transport,
                        CONF_MODEL: model,
                        CONF_INPUTS: num_inputs,
                        CONF_OUTPUTS: num_outputs,
                    },
                )

        return self.async_show_form(
            step_id="user", data_schema=USER_SCHEMA, errors=errors
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return OreiOptionsFlow()


class OreiOptionsFlow(config_entries.OptionsFlow):
    """Let the user name inputs/outputs and toggle features after setup.

    ``config_entry`` is provided automatically by the base class in modern Home
    Assistant — assigning it here (as older code did) raises on current HA and
    surfaces as a 500 when opening the options dialog, so we don't.
    """

    def _device_names(self, key: str) -> dict[int, str]:
        """Names the device itself reported (used to prefill the naming form)."""
        store = self.hass.data.get(DOMAIN, {}).get(self.config_entry.entry_id)
        if not store:
            return {}
        data = store["coordinator"].data or {}
        return data.get(key, {}) or {}

    async def async_step_init(self, user_input=None):
        return self.async_show_menu(
            step_id="init",
            menu_options=["names", "settings"],
        )

    async def async_step_names(self, user_input=None):
        data = self.config_entry.data
        options = self.config_entry.options
        num_inputs = data.get(CONF_INPUTS, 8)
        num_outputs = data.get(CONF_OUTPUTS, 8)
        input_names = options.get(CONF_INPUT_NAMES, {})
        output_names = options.get(CONF_OUTPUT_NAMES, {})
        dev_in = self._device_names("input_names")
        dev_out = self._device_names("output_names")

        if user_input is not None:
            new_inputs = {}
            new_outputs = {}
            for i in range(1, num_inputs + 1):
                val = user_input.get(f"input_{i}", "").strip()
                if val:
                    new_inputs[str(i)] = val
            for o in range(1, num_outputs + 1):
                val = user_input.get(f"output_{o}", "").strip()
                if val:
                    new_outputs[str(o)] = val
            new_options = dict(options)
            new_options[CONF_INPUT_NAMES] = new_inputs
            new_options[CONF_OUTPUT_NAMES] = new_outputs
            return self.async_create_entry(title="", data=new_options)

        schema: dict = {}
        for i in range(1, num_inputs + 1):
            suggested = input_names.get(str(i)) or dev_in.get(i, "")
            schema[
                vol.Optional(
                    f"input_{i}",
                    description={"suggested_value": suggested},
                )
            ] = str
        for o in range(1, num_outputs + 1):
            suggested = output_names.get(str(o)) or dev_out.get(o, "")
            schema[
                vol.Optional(
                    f"output_{o}",
                    description={"suggested_value": suggested},
                )
            ] = str

        return self.async_show_form(step_id="names", data_schema=vol.Schema(schema))

    async def async_step_settings(self, user_input=None):
        options = self.config_entry.options

        if user_input is not None:
            new_options = dict(options)
            new_options.update(user_input)
            return self.async_create_entry(title="", data=new_options)

        schema = vol.Schema(
            {
                vol.Optional(
                    CONF_SCAN_INTERVAL,
                    default=options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
                ): vol.All(int, vol.Range(min=5, max=600)),
                vol.Optional(
                    CONF_CEC_PORT,
                    default=options.get(
                        CONF_CEC_PORT, self.config_entry.data.get(CONF_CEC_PORT, DEFAULT_CEC_PORT)
                    ),
                ): vol.All(int, vol.Range(min=1, max=65535)),
                vol.Optional(
                    CONF_ENABLE_MEDIA_PLAYER,
                    default=options.get(
                        CONF_ENABLE_MEDIA_PLAYER, DEFAULT_ENABLE_MEDIA_PLAYER
                    ),
                ): bool,
                vol.Optional(
                    CONF_ENABLE_SELECT,
                    default=options.get(CONF_ENABLE_SELECT, DEFAULT_ENABLE_SELECT),
                ): bool,
                vol.Optional(
                    CONF_ENABLE_BUTTON,
                    default=options.get(CONF_ENABLE_BUTTON, DEFAULT_ENABLE_BUTTON),
                ): bool,
                vol.Optional(
                    CONF_ENABLE_LINK_SENSORS,
                    default=options.get(
                        CONF_ENABLE_LINK_SENSORS, DEFAULT_ENABLE_LINK_SENSORS
                    ),
                ): bool,
                vol.Optional(
                    CONF_ENABLE_PRESETS,
                    default=options.get(CONF_ENABLE_PRESETS, DEFAULT_ENABLE_PRESETS),
                ): bool,
            }
        )
        return self.async_show_form(step_id="settings", data_schema=schema)
