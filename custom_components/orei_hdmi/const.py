"""Constants for the OREI HDMI Matrix integration."""
from __future__ import annotations

DOMAIN = "orei_hdmi"
MANUFACTURER = "OREI"

# --- Connection ---------------------------------------------------------------
# Many OREI units listen on 8000; some firmware/models use the telnet default 23.
DEFAULT_PORT = 8000
DEFAULT_SCAN_INTERVAL = 30  # seconds

# Every OREI command already ends in "!", which the matrix uses as the delimiter,
# so no extra terminator is needed on a persistent socket. Set to "\r\n" if a
# given firmware requires a line ending.
CMD_TERMINATOR = ""

# How long to keep reading a response after the last byte before giving up.
READ_IDLE_TIMEOUT = 0.3

# --- Config entry data keys ---------------------------------------------------
CONF_HOST = "host"
CONF_PORT = "port"
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


def input_name(entry, index: int) -> str:
    """Friendly name for an input, falling back to 'Input N'."""
    names = entry.options.get(CONF_INPUT_NAMES, {})
    return names.get(str(index)) or f"Input {index}"


def output_name(entry, index: int) -> str:
    """Friendly name for an output/zone, falling back to 'Output N'."""
    names = entry.options.get(CONF_OUTPUT_NAMES, {})
    return names.get(str(index)) or f"Output {index}"


def input_names(entry, count: int) -> list[str]:
    """Ordered list of input friendly names."""
    return [input_name(entry, i) for i in range(1, count + 1)]
