"""Select platform for OREI: auto-detect outputs and manage input switching."""
from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
import asyncio, re
from .const import DOMAIN, DEFAULT_PORT

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback):
    host = entry.data.get("host")
    port = entry.data.get("port", DEFAULT_PORT)
    outputs = 4
    try:
        reader, writer = await asyncio.open_connection(host, port)
        writer.write("r av out 0!".encode())
        await writer.drain()
        await asyncio.sleep(0.1)
        data = await reader.read(2048)
        writer.close()
        try:
            await writer.wait_closed()
        except Exception:
            pass
        if data:
            text = data.decode(errors='ignore').lower()
            matches = re.findall(r"output\s*(\d+)", text)
            if matches:
                outputs = max(int(x) for x in matches)
    except Exception:
        pass

    entities = [OreiOutputSelect(entry.entry_id, host, port, out) for out in range(1, outputs + 1)]
    async_add_entities(entities, update_before_add=True)

class OreiOutputSelect(SelectEntity):
    _attr_has_entity_name = True

    def __init__(self, entry_id, host, port, output):
        self._entry_id = entry_id
        self._host = host
        self._port = port
        self._output = output
        self._options = [f"Input {i}" for i in range(1,9)]
        self._current = None
        self._attr_name = f"Output {output} Input"

    @property
    def options(self):
        return self._options

    @property
    def current_option(self):
        return self._current

    async def async_select_option(self, option: str):
        try:
            input_num = int(option.split()[1])
        except Exception:
            return
        cmd = f"s in {input_num} av out {self._output}!"
        await self._send_command(cmd)
        self._current = option
        self.async_write_ha_state()

    async def async_update(self):
        try:
            resp = await self._send_command("r av out 0!")
            if resp:
                for line in resp.splitlines():
                    if f"output {self._output}" in line.lower() and "input" in line.lower():
                        m = re.search(r"input\s*(\d+)", line.lower())
                        if m:
                            n = int(m.group(1))
                            self._current = f"Input {n}"
        except Exception:
            pass

    async def _send_command(self, cmd: str):
        try:
            reader, writer = await asyncio.open_connection(self._host, self._port)
            writer.write(cmd.encode())
            await writer.drain()
            await asyncio.sleep(0.05)
            data = await reader.read(2048)
            writer.close()
            try:
                await writer.wait_closed()
            except Exception:
                pass
            return data.decode(errors='ignore') if data else ""
        except Exception:
            return ""
