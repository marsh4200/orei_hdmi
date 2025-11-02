"""Switch platform for OREI: Power control."""
from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
import asyncio
from .const import DOMAIN, DEFAULT_PORT

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback):
    host = entry.data.get("host")
    port = entry.data.get("port", DEFAULT_PORT)
    async_add_entities([OreiPowerSwitch(entry.entry_id, host, port)])

class OreiPowerSwitch(SwitchEntity):
    _attr_has_entity_name = True

    def __init__(self, entry_id, host, port):
        self._entry_id = entry_id
        self._host = host
        self._port = port
        self._is_on = None
        self._attr_name = "Power"

    @property
    def is_on(self):
        return self._is_on

    async def async_turn_on(self, **kwargs):
        await self._send_command("s power 1!")
        self._is_on = True
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs):
        await self._send_command("s power 0!")
        self._is_on = False
        self.async_write_ha_state()

    async def async_update(self):
        try:
            resp = await self._send_command("r power!")
            if resp and "power on" in resp.lower():
                self._is_on = True
            elif resp and "power off" in resp.lower():
                self._is_on = False
        except Exception:
            pass

    async def _send_command(self, cmd: str):
        try:
            reader, writer = await asyncio.open_connection(self._host, self._port)
            writer.write(cmd.encode())
            await writer.drain()
            await asyncio.sleep(0.1)
            data = await reader.read(1024)
            writer.close()
            try:
                await writer.wait_closed()
            except Exception:
                pass
            return data.decode(errors='ignore') if data else ""
        except Exception:
            return ""
