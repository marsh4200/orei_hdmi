"""Select platform for OREI: auto-detect inputs/outputs and manage input switching."""
from __future__ import annotations

import asyncio
import re
from typing import Optional

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    DOMAIN,
    DEFAULT_PORT,
    CONF_INPUTS,
    CONF_OUTPUTS,
)


async def _probe_io(host: str, port: int) -> tuple[int, int]:
    """Probe the matrix for number of inputs and outputs.

    Uses 'r av out 0!' and parses lines like 'input 1 -> output 3'.
    """
    num_inputs = 8
    num_outputs = 8

    try:
        reader, writer = await asyncio.open_connection(host, port)
        writer.write(b"r av out 0!")
        await writer.drain()
        await asyncio.sleep(0.1)
        data = await reader.read(4096)
        writer.close()
        try:
            await writer.wait_closed()
        except Exception:
            pass

        if data:
            text = data.decode(errors="ignore").lower()
            inputs_seen = set()
            outputs_seen = set()

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
        pass

    # Clamp to something sane; OREI matrices are generally <= 8x8
    num_inputs = max(1, min(num_inputs, 32))
    num_outputs = max(1, min(num_outputs, 32))

    return num_inputs, num_outputs


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up select entities for each output."""
    host = entry.data.get("host")
    port = entry.data.get("port", DEFAULT_PORT)

    # Try to use stored IO counts from config flow
    inputs = entry.data.get(CONF_INPUTS)
    outputs = entry.data.get(CONF_OUTPUTS)

    # Fallback: probe again if missing (old entries created before upgrade)
    if not inputs or not outputs:
        inputs, outputs = await _probe_io(host, port)

    entities: list[OreiOutputSelect] = [
        OreiOutputSelect(entry.entry_id, host, port, out, inputs)
        for out in range(1, outputs + 1)
    ]

    async_add_entities(entities, update_before_add=True)


class OreiOutputSelect(SelectEntity):
    """Entity that represents the selected input for a given output."""

    _attr_has_entity_name = True

    def __init__(
        self,
        entry_id: str,
        host: str,
        port: int,
        output: int,
        input_count: int,
    ) -> None:
        self._entry_id = entry_id
        self._host = host
        self._port = port
        self._output = output
        self._input_count = input_count
        self._current: Optional[str] = None
        self._attr_name = f"Output {output} Input"

    @property
    def options(self) -> list[str]:
        # Dynamic – based on detected input count
        return [f"Input {i}" for i in range(1, self._input_count + 1)]

    @property
    def current_option(self) -> Optional[str]:
        return self._current

    async def async_select_option(self, option: str) -> None:
        """Set matrix routing when the user selects an option."""
        try:
            input_num = int(option.split()[1])
        except Exception:
            return

        cmd = f"s in {input_num} av out {self._output}!"
        await self._send_command(cmd)
        self._current = option
        self.async_write_ha_state()

    async def async_update(self) -> None:
        """Refresh current input for this output from the matrix."""
        try:
            resp = await self._send_command("r av out 0!")
            if not resp:
                return

            # Expect lines like: "input 1 -> output 3"
            for line in resp.splitlines():
                line_lower = line.lower()
                m = re.search(r"input\s*(\d+)\s*->\s*output\s*(\d+)", line_lower)
                if not m:
                    continue

                in_num = int(m.group(1))
                out_num = int(m.group(2))

                if out_num == self._output:
                    self._current = f"Input {in_num}"
                    break

        except Exception:
            # Don’t crash HA if matrix is offline
            pass

    async def _send_command(self, cmd: str) -> str:
        """Send a single ASCII command and return the raw response (if any)."""
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
            return data.decode(errors="ignore") if data else ""
        except Exception:
            return ""
