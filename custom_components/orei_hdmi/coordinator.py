"""Transports and data coordinator for the OREI HDMI Matrix.

Two transports implement the same control surface and both expose an async
``poll()`` returning the same dict shape, so entities are transport-agnostic:

* ``OreiHdmiClient`` (telnet) — raw ASCII protocol; works on any OREI model and
  carries CEC as words. Rich data (scaler/hdcp/edid/presets) is HTTP-only, so
  those methods no-op / raise on telnet.
* ``OreiHttpClient`` — the CGI JSON API (``/cgi-bin/instr``). Structured status,
  real port + preset names, native CEC (``cec command``), and all the rich
  per-port data.
"""
from __future__ import annotations

import asyncio
import logging
import re
from datetime import timedelta

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    API_PATH,
    CEC_INPUT_INDEX,
    CEC_OUTPUT_INDEX,
    CMD_TERMINATOR,
    DEFAULT_CEC_PORT,
    DOMAIN,
    HTTP_TIMEOUT,
    READ_IDLE_TIMEOUT,
    SCALER_MODES,
    TRANSPORT_HTTP,
    TRANSPORT_TELNET,
    normalize_cec,
)

_LOGGER = logging.getLogger(__name__)

_HTTP_ONLY = "This action is only supported on the HTTP (JSON API) transport."


def _empty_rich() -> dict:
    """Rich-data keys, defaulted empty (telnet leaves them like this)."""
    return {
        "input_names": {},
        "output_names": {},
        "presets": {},
        "scaler": {},
        "hdr": {},
        "hdcp": {},
        "arc": {},
        "audio_mute": {},
        "out_enable": {},
        "edid": {},
        "input_power": {},
        "firmware": None,
        "panel_lock": None,
        "beep": None,
    }


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
                result = [ln.strip(" \t\r\n>") for ln in text.splitlines() if ln.strip(" \t\r\n>")]
                _LOGGER.debug("OREI <- %s", result)
                return result
            except Exception as err:  # noqa: BLE001
                _LOGGER.warning("Command '%s' failed (%s); reconnecting next time", cmd, err)
                await self.disconnect()
                raise

    async def command(self, cmd: str) -> str:
        lines = await self.command_lines(cmd)
        return lines[-1] if lines else ""

    @staticmethod
    def _echo(cmd: str, line: str) -> bool:
        return line.lower().replace(" ", "") == cmd.lower().replace(" ", "").rstrip("!")

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

    async def set_cec_input(self, input_id: int, command: str) -> None:
        await self.command(f"s cec in {input_id} {normalize_cec(command)}!")

    async def set_cec_output(self, output_id: int, command: str) -> None:
        await self.command(f"s cec hdmi out {output_id} {normalize_cec(command)}!")

    async def get_routing(self) -> dict[int, int]:
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

    # Rich data / rich commands are not available over telnet.
    async def recall_preset(self, index: int) -> None:
        raise HomeAssistantError(_HTTP_ONLY)

    async def save_preset(self, index: int, name: str | None = None) -> None:
        raise HomeAssistantError(_HTTP_ONLY)

    async def clear_preset(self, index: int) -> None:
        raise HomeAssistantError(_HTTP_ONLY)

    async def rename_preset(self, index: int, name: str) -> None:
        raise HomeAssistantError(_HTTP_ONLY)

    async def set_scaler(self, output_id: int, mode: int) -> None:
        raise HomeAssistantError(_HTTP_ONLY)

    async def set_edid(self, input_id: int, mode: int) -> None:
        raise HomeAssistantError(_HTTP_ONLY)

    async def set_arc(self, output_id: int, enabled: bool) -> None:
        raise HomeAssistantError(_HTTP_ONLY)

    async def set_panel_lock(self, locked: bool) -> None:
        raise HomeAssistantError(_HTTP_ONLY)

    async def set_beep(self, enabled: bool) -> None:
        raise HomeAssistantError(_HTTP_ONLY)

    async def probe(self) -> tuple[str, int, int]:
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
        return model, max(1, min(num_in, 32)), max(1, min(num_out, 32))

    async def poll(self) -> dict:
        data = _empty_rich()
        data.update(
            {
                "power": await self.get_power(),
                "model": (await self.get_type()) or None,
                "routing": await self.get_routing(),
                "in_links": await self.get_input_links(),
                "out_links": await self.get_output_links(),
            }
        )
        if data["model"] == "Unknown":
            data["model"] = None
        return data


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
        num_inputs: int = 8,
        num_outputs: int = 8,
    ) -> None:
        self._hass = hass
        self._host = host
        self._port = port
        self._cec_port = cec_port
        self._num_in = num_inputs
        self._num_out = num_outputs
        self._base_url = f"http://{host}:{port}{API_PATH}"

    @property
    def host(self) -> str:
        return self._host

    def set_counts(self, num_inputs: int, num_outputs: int) -> None:
        self._num_in = num_inputs
        self._num_out = num_outputs

    async def connect(self) -> None:
        return None

    async def disconnect(self) -> None:
        return None

    # -- low level -------------------------------------------------------------
    async def _request(self, comhead: str, **extra) -> dict:
        import aiohttp

        payload = {"comhead": comhead, "language": 0, **extra}
        session = async_get_clientsession(self._hass)
        timeout = aiohttp.ClientTimeout(total=HTTP_TIMEOUT)
        async with session.post(self._base_url, json=payload, timeout=timeout) as resp:
            resp.raise_for_status()
            data = await resp.json(content_type=None)
            _LOGGER.debug("OREI HTTP %s -> %s", comhead, data)
            return data or {}

    # -- status reads ----------------------------------------------------------
    async def get_system_status(self) -> dict:
        return await self._request("get system status")

    async def get_video_status(self) -> dict:
        return await self._request("get video status")

    async def get_output_status(self) -> dict:
        return await self._request("get output status")

    async def get_input_status(self) -> dict:
        return await self._request("get input status")

    async def get_type(self) -> str:
        # The JSON API exposes no model string, so synthesise one from I/O counts.
        return f"OREI {self._num_in}x{self._num_out} Matrix"

    # -- commands --------------------------------------------------------------
    async def set_power(self, state: bool) -> None:
        await self._request("set poweronoff", power=1 if state else 0)

    async def set_route(self, input_id: int, output_id: int) -> None:
        # API expects source = [output, input].
        await self._request("video switch", source=[output_id, input_id])

    def _cec_port_array(self, port_id: int, count: int) -> list[int]:
        length = max(count, port_id, 1)
        arr = [0] * length
        arr[port_id - 1] = 1
        return arr

    async def _cec(self, obj: int, port_id: int, command: str, table: dict, count: int) -> None:
        name = normalize_cec(command)
        if name not in table:
            raise HomeAssistantError(
                f"Unsupported CEC command '{command}' for "
                f"{'output' if obj else 'input'}. Valid: {', '.join(table)}"
            )
        await self._request(
            "cec command",
            object=obj,
            port=self._cec_port_array(port_id, count),
            index=table[name],
        )

    async def set_cec_output(self, output_id: int, command: str) -> None:
        await self._cec(1, output_id, command, CEC_OUTPUT_INDEX, self._num_out)

    async def set_cec_input(self, input_id: int, command: str) -> None:
        await self._cec(0, input_id, command, CEC_INPUT_INDEX, self._num_in)

    async def recall_preset(self, index: int) -> None:
        await self._request("preset set", index=index)

    async def save_preset(self, index: int, name: str | None = None) -> None:
        await self._request("preset save", index=index)
        if name:
            await self.rename_preset(index, name)

    async def clear_preset(self, index: int) -> None:
        await self._request("preset clear", index=index)

    async def rename_preset(self, index: int, name: str) -> None:
        await self._request("preset name", index=index, name=name)

    async def set_scaler(self, output_id: int, mode: int) -> None:
        await self._request("video scaler", scaler=[output_id, mode])

    async def set_edid(self, input_id: int, mode: int) -> None:
        await self._request("set edid", edid=[input_id, mode])

    async def set_arc(self, output_id: int, enabled: bool) -> None:
        await self._request("set arc", arc=[output_id, 1 if enabled else 0])

    async def set_panel_lock(self, locked: bool) -> None:
        await self._request("set panel lock", lock=1 if locked else 0)

    async def set_beep(self, enabled: bool) -> None:
        await self._request("set beep", beep=1 if enabled else 0)

    # -- parsing helpers -------------------------------------------------------
    @staticmethod
    def _names(arr, skip_prefixes: tuple[str, ...] = ()) -> dict[int, str]:
        names: dict[int, str] = {}
        for idx, name in enumerate(arr or []):
            if not isinstance(name, str) or not name.strip():
                continue
            low = name.strip().lower()
            if any(low.startswith(p) for p in skip_prefixes):
                continue
            names[idx + 1] = name.strip()
        return names

    @staticmethod
    def _by_index(arr, count: int, cast=int) -> dict[int, object]:
        out: dict[int, object] = {}
        for idx in range(count):
            if idx < len(arr or []):
                out[idx + 1] = cast(arr[idx])
        return out

    async def probe(self) -> tuple[str, int, int]:
        video = await self.get_video_status()
        num_in = len(video.get("allinputname", [])) or 4
        num_out = len(video.get("alloutputname", [])) or 4
        self.set_counts(max(1, min(num_in, 32)), max(1, min(num_out, 32)))
        return await self.get_type(), self._num_in, self._num_out

    async def poll(self) -> dict:
        system = await self.get_system_status()
        video = await self.get_video_status()
        output = await self.get_output_status()
        input_st = await self.get_input_status()

        n_in = self._num_in
        n_out = self._num_out

        # Routing: allsource[i] = input feeding output i+1 (trailing 0 = padding).
        routing: dict[int, int] = {}
        allsource = video.get("allsource", [])
        for idx in range(min(n_out, len(allsource))):
            src = allsource[idx]
            if src:
                routing[idx + 1] = int(src)

        input_names = self._names(video.get("allinputname", [])) or self._names(
            input_st.get("inname", [])
        )
        output_names = self._names(
            video.get("alloutputname", []), skip_prefixes=("hdmi output", "output")
        ) or self._names(output.get("name", []), skip_prefixes=("hdmi output", "output"))
        presets = self._names(video.get("allname", []))

        # Input signal: inactive[i] == 0 -> signal present.
        in_links: dict[int, bool] = {}
        for idx, val in enumerate(input_st.get("inactive", [])[:n_in]):
            in_links[idx + 1] = val == 0

        # Output connection: allconnect (OR allhdbtconnect where the model has it).
        hdmi = output.get("allconnect", [])
        hdbt = output.get("allhdbtconnect", [])
        out_links: dict[int, bool] = {}
        for idx in range(n_out):
            h = hdmi[idx] if idx < len(hdmi) else 0
            b = hdbt[idx] if idx < len(hdbt) else 0
            out_links[idx + 1] = bool(h or b)

        data = {
            "power": bool(system.get("power", video.get("power", 0))),
            "model": None,
            "routing": routing,
            "in_links": in_links,
            "out_links": out_links,
            "input_names": input_names,
            "output_names": output_names,
            "presets": presets,
            "scaler": self._by_index(output.get("allscaler", []), n_out),
            "hdr": {k: bool(v) for k, v in self._by_index(output.get("allhdr", []), n_out).items()},
            "hdcp": self._by_index(output.get("allhdcp", []), n_out),
            "arc": {k: bool(v) for k, v in self._by_index(output.get("allarc", []), n_out).items()},
            "audio_mute": {
                k: bool(v) for k, v in self._by_index(output.get("allaudiomute", []), n_out).items()
            },
            "out_enable": {
                k: bool(v) for k, v in self._by_index(output.get("allout", []), n_out).items()
            },
            "edid": self._by_index(input_st.get("edid", []), n_in),
            "input_power": {
                k: bool(v) for k, v in self._by_index(input_st.get("power", []), n_in).items()
            },
            "firmware": system.get("version"),
            "panel_lock": bool(system["lock"]) if "lock" in system else None,
            "beep": bool(system["beep"]) if "beep" in system else None,
        }
        return data


# =============================================================================
# Transport detection / factory
# =============================================================================
async def async_probe_transport(
    hass: HomeAssistant, host: str, http_port: int, telnet_port: int
) -> tuple[str, str, int, int]:
    """Detect the best transport. Tries HTTP first, then telnet."""
    try:
        http = OreiHttpClient(hass, host, http_port)
        model, num_in, num_out = await http.probe()
        _LOGGER.debug("HTTP transport detected for %s", host)
        return TRANSPORT_HTTP, model, num_in, num_out
    except Exception as err:  # noqa: BLE001
        _LOGGER.debug("HTTP probe failed for %s (%s); trying telnet", host, err)

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
    num_inputs: int = 8,
    num_outputs: int = 8,
):
    """Instantiate the client for a stored transport."""
    if transport == TRANSPORT_HTTP:
        return OreiHttpClient(hass, host, http_port, cec_port, num_inputs, num_outputs)
    return OreiHdmiClient(host, telnet_port)


# =============================================================================
# Coordinator
# =============================================================================
class OreiHdmiCoordinator(DataUpdateCoordinator):
    """Polls the matrix and exposes the latest state to all platforms."""

    def __init__(self, hass: HomeAssistant, client, scan_interval: int) -> None:
        super().__init__(
            hass, _LOGGER, name=DOMAIN, update_interval=timedelta(seconds=scan_interval)
        )
        self.client = client
        self.model: str = "Unknown"
        self.last_preset: int | None = None

    async def _async_update_data(self) -> dict:
        try:
            data = await self.client.poll()
        except Exception as err:  # noqa: BLE001
            raise UpdateFailed(err) from err

        if data.get("model"):
            self.model = data["model"]
        elif self.model == "Unknown":
            try:
                self.model = await self.client.get_type()
            except Exception:  # noqa: BLE001
                pass
        data["model"] = self.model
        data["last_preset"] = self.last_preset
        return data
