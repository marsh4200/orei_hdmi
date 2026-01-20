"""Config flow for OREI HDMI Matrix."""
import asyncio
import re
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_HOST, CONF_PORT

from .const import DOMAIN, DEFAULT_PORT, CONF_INPUTS, CONF_OUTPUTS, CONF_MODEL


DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST): str,
        vol.Optional(CONF_PORT, default=DEFAULT_PORT): int,
    }
)


async def _probe_matrix(host: str, port: int) -> tuple[str | None, int, int]:
    """Probe the matrix to detect model and input/output counts."""
    model: str | None = None
    num_inputs = 8   # sensible defaults
    num_outputs = 8

    try:
        reader, writer = await asyncio.open_connection(host, port)

        # Try to get the model name
        try:
            writer.write(b"r type!")
            await writer.drain()
            await asyncio.sleep(0.05)
            data = await reader.read(512)
            if data:
                text = data.decode(errors="ignore").strip()
                # First non-empty line is usually the model
                for line in text.splitlines():
                    if line.strip():
                        model = line.strip()
                        break
        except Exception:
            # Non-fatal – we can still continue
            pass

        # Now query the AV crosspoint mapping
        try:
            writer.write(b"r av out 0!")
            await writer.drain()
            await asyncio.sleep(0.1)
            data = await reader.read(4096)
        finally:
            writer.close()
            try:
                await writer.wait_closed()
            except Exception:
                pass

        if data:
            text = data.decode(errors="ignore").lower()
            inputs_seen = set()
            outputs_seen = set()

            # Typical lines: "input 1 -> output 1"
            for line in text.splitlines():
                m = re.search(r"input\s*(\d+)\s*->\s*output\s*(\d+)", line)
                if m:
                    inputs_seen.add(int(m.group(1)))
                    outputs_seen.add(int(m.group(2)))

            if inputs_seen:
                num_inputs = max(inputs_seen)
            if outputs_seen:
                num_outputs = max(outputs_seen)

    except Exception:
        # If anything fails, just fall back to defaults
        pass

    # Safety clamp – most OREI units are <= 8x8
    num_inputs = max(1, min(num_inputs, 32))
    num_outputs = max(1, min(num_outputs, 32))

    return model, num_inputs, num_outputs


class OreiConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input=None):
        errors = {}

        if user_input is not None:
            host = user_input[CONF_HOST]
            port = user_input.get(CONF_PORT, DEFAULT_PORT)

            # First just test basic connectivity
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
                # If reachable, probe the matrix for model / IO counts
                model, num_inputs, num_outputs = await _probe_matrix(host, port)

                title = model or f"OREI {host}"

                data = {
                    CONF_HOST: host,
                    CONF_PORT: port,
                    CONF_MODEL: model,
                    CONF_INPUTS: num_inputs,
                    CONF_OUTPUTS: num_outputs,
                }

                return self.async_create_entry(title=title, data=data)

        return self.async_show_form(
            step_id="user",
            data_schema=DATA_SCHEMA,
            errors=errors,
        )
