"""Persistent async client and data coordinator for the OREI HDMI Matrix.

The client keeps a single TCP/telnet connection open (with a lock and automatic
reconnect) instead of opening a fresh socket for every command, which is faster
and easier on the matrix's small connection pool.
"""
from __future__ import annotations

import asyncio
import logging
import re
from datetime import timedelta

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import CMD_TERMINATOR, DOMAIN, READ_IDLE_TIMEOUT

_LOGGER = logging.getLogger(__name__)


class OreiHdmiClient:
    """Async client for controlling an OREI HDMI matrix over TCP."""

    def __init__(self, host: str, port: int) -> None:
        self._host = host
        self._port = port
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._lock = asyncio.Lock()

    @property
    def host(self) -> str:
        return self._host

    # -- connection management -------------------------------------------------
    async def connect(self) -> None:
        self._reader, self._writer = await asyncio.open_connection(self._host, self._port)
        _LOGGER.debug("Connected to OREI matrix at %s:%s", self._host, self._port)

    async def disconnect(self) -> None:
        if self._writer is not None:
            try:
                self._writer.close()
                await self._writer.wait_closed()
            except Exception:  # noqa: BLE001
                pass
        self._reader = None
        self._writer = None

    async def _ensure_connected(self) -> None:
        if self._writer is None or self._writer.is_closing():
            await self.connect()

    # -- core command handling -------------------------------------------------
    async def command_lines(self, cmd: str) -> list[str]:
        """Send a command and return the raw response as a list of text lines.

        No banner/echo filtering happens here: the higher-level getters use
        regular expressions to pick out only the lines they care about, so
        prompts, echoes and welcome banners are simply ignored by not matching.
        """
        async with self._lock:
            await self._ensure_connected()
            try:
                assert self._writer is not None and self._reader is not None
                _LOGGER.debug("OREI -> %s", cmd)
                self._writer.write((cmd + CMD_TERMINATOR).encode("ascii"))
                await self._writer.drain()

                buffer = bytearray()
                while True:
                    try:
                        part = await asyncio.wait_for(
                            self._reader.read(1024), timeout=READ_IDLE_TIMEOUT
                        )
                    except asyncio.TimeoutError:
                        break
                    if not part:
                        break
                    buffer += part

                if not buffer:
                    return []

                text = buffer.decode("ascii", errors="ignore")
                lines = [ln.strip(" \t\r\n>") for ln in text.splitlines()]
                result = [ln for ln in lines if ln]
                _LOGGER.debug("OREI <- %s", result)
                return result
            except Exception as err:  # noqa: BLE001
                _LOGGER.warning(
                    "Command '%s' failed (%s); reconnecting next time", cmd, err
                )
                await self.disconnect()
                raise

    async def command(self, cmd: str) -> str:
        """Send a command and return the last non-empty response line."""
        lines = await self.command_lines(cmd)
        return lines[-1] if lines else ""

    @staticmethod
    def _echo(cmd: str, line: str) -> bool:
        """True if a response line is just the device echoing the command back."""
        return line.lower().replace(" ", "") == cmd.lower().replace(" ", "").rstrip("!")

    # -- high level API --------------------------------------------------------
    # Every getter below extracts what it needs with a regular expression, so
    # any echo/banner lines that don't match are ignored automatically.
    _RE_ROUTE = re.compile(r"in(?:put)?\s*(\d+).*?out(?:put)?\s*(\d+)", re.I)
    _RE_ROUTE_REV = re.compile(r"out(?:put)?\s*(\d+).*?in(?:put)?\s*(\d+)", re.I)
    _RE_IN = re.compile(r"in(?:put)?\s*(\d+)", re.I)
    _RE_OUT = re.compile(r"out(?:put)?\s*(\d+)", re.I)
    _RE_POWER = re.compile(r"power\s*(on|off)", re.I)

    async def get_type(self) -> str:
        cmd = "r type!"
        lines = [ln for ln in await self.command_lines(cmd) if not self._echo(cmd, ln)]
        return lines[-1] if lines else "Unknown"

    async def get_power(self) -> bool:
        for line in await self.command_lines("r power!"):
            m = self._RE_POWER.search(line)
            if m:
                return m.group(1).lower() == "on"
        return False

    async def set_power(self, state: bool) -> None:
        await self.command(f"s power {1 if state else 0}!")

    async def set_route(self, input_id: int, output_id: int) -> None:
        await self.command(f"s in {input_id} av out {output_id}!")

    async def set_cec_input(self, input_id: int, cec_command: str) -> None:
        await self.command(f"s cec in {input_id} {cec_command}!")

    async def set_cec_output(self, output_id: int, cec_command: str) -> None:
        await self.command(f"s cec hdmi out {output_id} {cec_command}!")

    async def get_routing(self) -> dict[int, int]:
        """Return {output_id: input_id} for every output.

        The matrix may print either "input N -> output M" or "output M : input N",
        so both orderings are matched.
        """
        routing: dict[int, int] = {}
        for line in await self.command_lines("r av out 0!"):
            m = self._RE_ROUTE.search(line)
            if m:
                routing[int(m.group(2))] = int(m.group(1))
                continue
            m = self._RE_ROUTE_REV.search(line)
            if m:
                routing[int(m.group(1))] = int(m.group(2))
        return routing

    async def _links(self, cmd: str, regex: re.Pattern) -> dict[int, bool]:
        links: dict[int, bool] = {}
        for line in await self.command_lines(cmd):
            m = regex.search(line)
            if m:
                links[int(m.group(1))] = "disconnect" not in line.lower()
        return links

    async def get_input_links(self) -> dict[int, bool]:
        return await self._links("r link in 0!", self._RE_IN)

    async def get_output_links(self) -> dict[int, bool]:
        return await self._links("r link out 0!", self._RE_OUT)

    async def probe(self) -> tuple[str, int, int]:
        """Detect (model, input_count, output_count)."""
        model = await self.get_type()
        routing = await self.get_routing()
        num_out = max(routing.keys(), default=8)
        num_in = max(routing.values(), default=8)
        try:
            in_links = await self.get_input_links()
            if in_links:
                num_in = max(num_in, max(in_links))
        except Exception:  # noqa: BLE001
            pass
        try:
            out_links = await self.get_output_links()
            if out_links:
                num_out = max(num_out, max(out_links))
        except Exception:  # noqa: BLE001
            pass
        num_in = max(1, min(num_in, 32))
        num_out = max(1, min(num_out, 32))
        return model, num_in, num_out


class OreiHdmiCoordinator(DataUpdateCoordinator):
    """Polls the matrix and exposes the latest state to all platforms."""

    def __init__(
        self, hass: HomeAssistant, client: OreiHdmiClient, scan_interval: int
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=scan_interval),
        )
        self.client = client
        self.model: str = "Unknown"

    async def _async_update_data(self) -> dict:
        try:
            if self.model == "Unknown":
                self.model = await self.client.get_type()
            power = await self.client.get_power()
            routing = await self.client.get_routing()
            in_links = await self.client.get_input_links()
            out_links = await self.client.get_output_links()
            return {
                "power": power,
                "model": self.model,
                "routing": routing,
                "in_links": in_links,
                "out_links": out_links,
            }
        except Exception as err:  # noqa: BLE001
            raise UpdateFailed(err) from err
