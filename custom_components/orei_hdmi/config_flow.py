"""Config and options flow for the OREI HDMI Matrix."""
from __future__ import annotations

import logging

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import callback

from .const import (
    CONF_ENABLE_BUTTON,
    CONF_ENABLE_LINK_SENSORS,
    CONF_ENABLE_MEDIA_PLAYER,
    CONF_ENABLE_SELECT,
    CONF_HOST,
    CONF_INPUT_NAMES,
    CONF_INPUTS,
    CONF_MODEL,
    CONF_OUTPUT_NAMES,
    CONF_OUTPUTS,
    CONF_PORT,
    CONF_SCAN_INTERVAL,
    DEFAULT_ENABLE_BUTTON,
    DEFAULT_ENABLE_LINK_SENSORS,
    DEFAULT_ENABLE_MEDIA_PLAYER,
    DEFAULT_ENABLE_SELECT,
    DEFAULT_PORT,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
)
from .coordinator import OreiHdmiClient

_LOGGER = logging.getLogger(__name__)

USER_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST): str,
        vol.Optional(CONF_PORT, default=DEFAULT_PORT): int,
    }
)


class OreiConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle the initial setup."""

    VERSION = 1

    async def async_step_user(self, user_input=None):
        errors: dict[str, str] = {}

        if user_input is not None:
            host = user_input[CONF_HOST]
            port = user_input.get(CONF_PORT, DEFAULT_PORT)

            await self.async_set_unique_id(host)
            self._abort_if_unique_id_configured()

            client = OreiHdmiClient(host, port)
            try:
                await client.connect()
                model, num_inputs, num_outputs = await client.probe()
            except Exception:  # noqa: BLE001
                errors["base"] = "cannot_connect"
            else:
                await client.disconnect()
                return self.async_create_entry(
                    title=model if model != "Unknown" else f"OREI Matrix ({host})",
                    data={
                        CONF_HOST: host,
                        CONF_PORT: port,
                        CONF_MODEL: model,
                        CONF_INPUTS: num_inputs,
                        CONF_OUTPUTS: num_outputs,
                    },
                )
            finally:
                await client.disconnect()

        return self.async_show_form(
            step_id="user", data_schema=USER_SCHEMA, errors=errors
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return OreiOptionsFlow(config_entry)


class OreiOptionsFlow(config_entries.OptionsFlow):
    """Let the user name inputs/outputs and toggle features after setup."""

    def __init__(self, config_entry) -> None:
        self.config_entry = config_entry

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
            schema[
                vol.Optional(
                    f"input_{i}",
                    description={"suggested_value": input_names.get(str(i), "")},
                )
            ] = str
        for o in range(1, num_outputs + 1):
            schema[
                vol.Optional(
                    f"output_{o}",
                    description={"suggested_value": output_names.get(str(o), "")},
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
            }
        )
        return self.async_show_form(step_id="settings", data_schema=schema)
