"""Constants for the OREI HDMI Matrix integration."""
from __future__ import annotations

DOMAIN = "orei_hdmi"
MANUFACTURER = "OREI"

# --- Transports ---------------------------------------------------------------
# The integration can talk to the matrix two ways:
#   * "http"   -> the device's CGI JSON API (structured data, real port/EDID
#                 names, signal detection). Preferred when reachable.
#   * "telnet" -> the raw ASCII/telnet protocol (works on any OREI model and is
#                 the only transport that carries CEC). Used as a fallback, and
#                 as a side-channel for CEC even when HTTP is primary.
TRANSPORT_HTTP = "http"
TRANSPORT_TELNET = "telnet"

# --- Connection ---------------------------------------------------------------
# Telnet: many OREI units listen on 8000; some firmware/models use 23.
DEFAULT_PORT = 8000              # telnet control port
DEFAULT_HTTP_PORT = 80           # CGI JSON API port
DEFAULT_CEC_PORT = 23            # telnet port used for CEC when HTTP is primary
DEFAULT_SCAN_INTERVAL = 30       # seconds

# CGI JSON API path (POST target).
API_PATH = "/cgi-bin/instr"
HTTP_TIMEOUT = 5                 # seconds

# Every OREI telnet command already ends in "!", which the matrix uses as the
# delimiter, so no extra terminator is needed on a persistent socket. Set to
# "\r\n" if a given firmware requires a line ending.
CMD_TERMINATOR = ""

# How long to keep reading a telnet response after the last byte before giving up.
READ_IDLE_TIMEOUT = 0.3

# --- Config entry data keys ---------------------------------------------------
CONF_HOST = "host"
CONF_PORT = "port"                # telnet port
CONF_HTTP_PORT = "http_port"
CONF_CEC_PORT = "cec_port"
CONF_TRANSPORT = "transport"      # "http" or "telnet"
CONF_MODEL = "model"
CONF_INPUTS = "inputs"            # detected input count
CONF_OUTPUTS = "outputs"          # detected output count

# --- Options keys -------------------------------------------------------------
CONF_SCAN_INTERVAL = "scan_interval"
CONF_INPUT_NAMES = "input_names"          # {"1": "Apple TV", "2": "Xbox", ...}
CONF_OUTPUT_NAMES = "output_names"        # {"1": "Living Room", ...}
CONF_ENABLE_MEDIA_PLAYER = "enable_media_player"
CONF_ENABLE_SELECT = "enable_select"
CONF_ENABLE_BUTTON = "enable_button"
CONF_ENABLE_LINK_SENSORS = "enable_link_sensors"

DEFAULT_ENABLE_MEDIA_PLAYER = True
DEFAULT_ENABLE_SELECT = True       # kept on for backward compatibility
DEFAULT_ENABLE_BUTTON = False
DEFAULT_ENABLE_LINK_SENSORS = True

# --- Services -----------------------------------------------------------------
SERVICE_REFRESH = "refresh"
SERVICE_SET_ROUTE = "set_route"
SERVICE_SET_CEC = "set_cec"
SERVICE_CYCLE_SOURCE = "cycle_source"


def _clean(value) -> str:
    return value.strip() if isinstance(value, str) else ""


def input_name(entry, index: int, device_names: dict | None = None) -> str:
    """Friendly name for an input.

    Precedence: user-set option name > name reported by the device > 'Input N'.
    """
    user = entry.options.get(CONF_INPUT_NAMES, {})
    if _clean(user.get(str(index))):
        return user[str(index)].strip()
    if device_names and _clean(device_names.get(index)):
        return device_names[index].strip()
    return f"Input {index}"


def output_name(entry, index: int, device_names: dict | None = None) -> str:
    """Friendly name for an output/zone.

    Precedence: user-set option name > name reported by the device > 'Output N'.
    """
    user = entry.options.get(CONF_OUTPUT_NAMES, {})
    if _clean(user.get(str(index))):
        return user[str(index)].strip()
    if device_names and _clean(device_names.get(index)):
        return device_names[index].strip()
    return f"Output {index}"


def input_names(entry, count: int, device_names: dict | None = None) -> list[str]:
    """Ordered list of input friendly names."""
    return [input_name(entry, i, device_names) for i in range(1, count + 1)]
