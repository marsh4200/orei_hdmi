"""Config flow for OREI HDMI Matrix."""
import asyncio
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import CONF_HOST, CONF_PORT
from .const import DOMAIN, DEFAULT_PORT

DATA_SCHEMA = vol.Schema({
    vol.Required(CONF_HOST): str,
    vol.Optional(CONF_PORT, default=DEFAULT_PORT): int,
})

class OreiConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input=None):
        errors = {}
        if user_input is not None:
            host = user_input[CONF_HOST]
            port = user_input.get(CONF_PORT, DEFAULT_PORT)
            try:
                reader, writer = await asyncio.open_connection(host, port)
                writer.close()
                try:
                    await writer.wait_closed()
                except Exception:
                    pass
            except Exception:
                errors["base"] = "cannot_connect"
            else:
                return self.async_create_entry(title=f"OREI {host}", data={CONF_HOST: host, CONF_PORT: port})

        return self.async_show_form(step_id="user", data_schema=DATA_SCHEMA, errors=errors)
