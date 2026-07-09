"""Transports and data coordinator for the OREI HDMI Matrix.

Two transports implement the same control surface:

* ``OreiHdmiClient`` (telnet) keeps a single TCP connection open (with a lock
  and automatic reconnect) and parses the ASCII protocol with regexes. It works
  on any OREI model and is the only transport that carries CEC.
* ``OreiHttpClient`` uses the device's CGI JSON API. It returns structured data
  including the real input/output names, model, and signal detection, and is
  preferred when reachable. CEC is delegated to a lazily-opened telnet
  side-channel because the JSON API has no CEC command.

Both expose an async ``poll()`` that returns the same dict shape, so the
coordinator and every entity are transport-agnostic.
"""
from __future__ import annotations

import asyncio
import logging
import re
from datetime import timedelta

from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    API_PATH,
    CMD_TERMINATOR,
    DEFAULT_CEC_PORT,
    DOMAIN,
    HTTP_TIMEOUT,
    READ_IDLE_TIMEOUT,
    TRANSPORT_HTTP,
    TRANSPORT_TELNET,
)

_LOGGER = logging.getLogger(__name__)


# =============================================================================
# Telnet transport
# =============================================================================
class OreiHdmiClient:
    """Async client for controlling an OREI HDMI matrix over TCP/telnet."""

    transport = TRANSPORT_TELNET

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
        """Send a command and return the raw response as a list of text lines."""
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
        """Return {output_id: input_id} for every output."""
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

    # Telnet cannot read friendly names off the device.
    async def get_input_names(self) -> dict[int, str]:
        return {}

    async def get_output_names(self) -> dict[int, str]:
        return {}

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

    async def poll(self) -> dict:
        """One full state read for the coordinator."""
        model = await self.get_type()
        power = await self.get_power()
        routing = await self.get_routing()
        in_links = await self.get_input_links()
        out_links = await self.get_output_links()
        return {
            "power": power,
            "model": model if model != "Unknown" else None,
            "routing": routing,
            "in_links": in_links,
            "out_links": out_links,
            "input_names": {},
            "output_names": {},
        }


# =============================================================================
# HTTP (CGI JSON) transport
# =============================================================================
class OreiHttpClient:
    """Async client for the OREI matrix CGI JSON API (``/cgi-bin/instr``)."""

    transport = TRANSPORT_HTTP

    def __init__(
        self,
        hass: HomeAssistant,
        host: str,
        port: int = 80,
        cec_port: int = DEFAULT_CEC_PORT,
    ) -> None:
        self._hass = hass
        self._host = host
        self._port = port
        self._cec_port = cec_port
        self._base_url = f"http://{host}:{port}{API_PATH}"
        self._cec: OreiHdmiClient | None = None  # lazy telnet side-channel for CEC
        self._cec_warned = False

    @property
    def host(self) -> str:
        return self._host

    async def connect(self) -> None:  # parity with telnet client
        return None

    async def disconnect(self) -> None:
        if self._cec is not None:
            await self._cec.disconnect()
            self._cec = None

    # -- low level -------------------------------------------------------------
    async def _request(self, comhead: str, **extra) -> dict:
        import aiohttp  # local: only needed on the HTTP path

        payload = {"comhead": comhead, "language": 0, **extra}
        session = async_get_clientsession(self._hass)
        timeout = aiohttp.ClientTimeout(total=HTTP_TIMEOUT)
        async with session.post(self._base_url, json=payload, timeout=timeout) as resp:
            resp.raise_for_status()
            data = await resp.json(content_type=None)
            _LOGGER.debug("OREI HTTP %s -> %s", comhead, data)
            return data or {}

    # -- status reads ----------------------------------------------------------
    async def get_status(self) -> dict:
        return await self._request("get status")

    async def get_video_status(self) -> dict:
        return await self._request("get video status")

    async def get_output_status(self) -> dict:
        return await self._request("get output status")

    async def get_input_status(self) -> dict:
        return await self._request("get input status")

    async def get_type(self) -> str:
        status = await self.get_status()
        return status.get("model") or status.get("type") or "Unknown"

    # -- commands --------------------------------------------------------------
    async def set_power(self, state: bool) -> None:
        await self._request("set poweronoff", power=1 if state else 0)

    async def set_route(self, input_id: int, output_id: int) -> None:
        await self._request("video switch", source=[input_id, output_id])

    # CEC has no JSON equivalent -> best-effort telnet side-channel.
    async def _cec_client(self) -> OreiHdmiClient:
        if self._cec is None:
            self._cec = OreiHdmiClient(self._host, self._cec_port)
        return self._cec

    async def set_cec_input(self, input_id: int, cec_command: str) -> None:
        try:
            await (await self._cec_client()).set_cec_input(input_id, cec_command)
        except Exception as err:  # noqa: BLE001
            self._warn_cec(err)

    async def set_cec_output(self, output_id: int, cec_command: str) -> None:
        try:
            await (await self._cec_client()).set_cec_output(output_id, cec_command)
        except Exception as err:  # noqa: BLE001
            self._warn_cec(err)

    def _warn_cec(self, err: Exception) -> None:
        if not self._cec_warned:
            _LOGGER.warning(
                "CEC over telnet side-channel (%s:%s) failed: %s. CEC needs the "
                "matrix telnet port reachable; adjust it in the integration options.",
                self._host,
                self._cec_port,
                err,
            )
            self._cec_warned = True

    # -- parsing helpers -------------------------------------------------------
    @staticmethod
    def _routing_from_video(video: dict) -> dict[int, int]:
        # "allsource" = [1, 2, 2, 1, 0] -> input per output, trailing 0 sentinel.
        routing: dict[int, int] = {}
        for idx, src in enumerate(video.get("allsource", [])):
            if src == 0:
                break
            routing[idx + 1] = int(src)
        return routing

    @staticmethod
    def _names(arr: list, skip_prefixes: tuple[str, ...] = ()) -> dict[int, str]:
        names: dict[int, str] = {}
        for idx, name in enumerate(arr or []):
            if not isinstance(name, str) or not name.strip():
                continue
            low = name.strip().lower()
            if any(low.startswith(p) for p in skip_prefixes):
                continue
            names[idx + 1] = name.strip()
        return names

    async def probe(self) -> tuple[str, int, int]:
        model = await self.get_type()
        video = await self.get_video_status()
        num_in = len(video.get("allinputname", [])) or 4
        # allsource carries a trailing sentinel; trim it for the count.
        allsource = [s for s in video.get("allsource", []) if s != 0]
        num_out = len(video.get("alloutputname", [])) or len(allsource) or 4
        num_in = max(1, min(num_in, 32))
        num_out = max(1, min(num_out, 32))
        return model, num_in, num_out

    async def poll(self) -> dict:
        video = await self.get_video_status()
        output = await self.get_output_status()
        input_st = await self.get_input_status()

        routing = self._routing_from_video(video)
        input_names = self._names(video.get("allinputname", []))
        output_names = self._names(
            video.get("alloutputname", []), skip_prefixes=("hdmi output",)
        )

        # Input signal: "inactive" = [1, 0, 0, 0] -> 0 means a signal is present.
        in_links: dict[int, bool] = {}
        for idx, val in enumerate(input_st.get("inactive", [])):
            in_links[idx + 1] = val == 0

        # Output connection: connected if either HDMI or HDBaseT reports a link.
        out_links: dict[int, bool] = {}
        hdmi = output.get("allconnect", [])
        hdbt = output.get("allhdbtconnect", [])
        for idx in range(max(len(hdmi), len(hdbt))):
            h = hdmi[idx] if idx < len(hdmi) else 0
            b = hdbt[idx] if idx < len(hdbt) else 0
            out_links[idx + 1] = bool(h or b)

        return {
            "power": bool(video.get("power", 0)),
            "model": None,  # filled once from probe; keeps polls to 3 requests
            "routing": routing,
            "in_links": in_links,
            "out_links": out_links,
            "input_names": input_names,
            "output_names": output_names,
        }


# =============================================================================
# Transport detection / factory
# =============================================================================
async def async_probe_transport(
    hass: HomeAssistant,
    host: str,
    http_port: int,
    telnet_port: int,
) -> tuple[str, str, int, int]:
    """Detect the best transport for a host.

    Tries HTTP (structured, richer) first, then telnet.
    Returns (transport, model, num_inputs, num_outputs). Raises on total failure.
    """
    # 1) HTTP
    try:
        http = OreiHttpClient(hass, host, http_port)
        model, num_in, num_out = await http.probe()
        _LOGGER.debug("HTTP transport detected for %s", host)
        return TRANSPORT_HTTP, model, num_in, num_out
    except Exception as err:  # noqa: BLE001
        _LOGGER.debug("HTTP probe failed for %s (%s); trying telnet", host, err)

    # 2) Telnet
    telnet = OreiHdmiClient(host, telnet_port)
    try:
        await telnet.connect()
        model, num_in, num_out = await telnet.probe()
        return TRANSPORT_TELNET, model, num_in, num_out
    finally:
        await telnet.disconnect()


def build_client(
    hass: HomeAssistant,
    transport: str,
    host: str,
    telnet_port: int,
    http_port: int,
    cec_port: int,
):
    """Instantiate the client for a stored transport."""
    if transport == TRANSPORT_HTTP:
        return OreiHttpClient(hass, host, http_port, cec_port)
    return OreiHdmiClient(host, telnet_port)


# =============================================================================
# Coordinator
# =============================================================================
class OreiHdmiCoordinator(DataUpdateCoordinator):
    """Polls the matrix and exposes the latest state to all platforms."""

    def __init__(self, hass: HomeAssistant, client, scan_interval: int) -> None:
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
            data = await self.client.poll()
        except Exception as err:  # noqa: BLE001
            raise UpdateFailed(err) from err

        # Model is read once (telnet reports it every poll; HTTP leaves it None).
        if data.get("model"):
            self.model = data["model"]
        elif self.model == "Unknown":
            try:
                self.model = await self.client.get_type()
            except Exception:  # noqa: BLE001
                pass
        data["model"] = self.model
        return data
