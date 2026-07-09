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


# =============================================================================
# CEC (native HTTP `cec command`) — index numbering differs by object type.
# object 1 = output/display, object 0 = input/source.
# =============================================================================
CEC_OUTPUT_INDEX = {
    "on": 0,
    "off": 1,
    "mute": 2,
    "volume_down": 3,
    "volume_up": 4,
    "source": 5,
}
CEC_INPUT_INDEX = {
    "on": 1,
    "off": 2,
    "enter": 5,
    "play": 11,
    "pause": 14,
    "stop": 16,
    "mute": 17,
    "volume_down": 18,
    "volume_up": 19,
}

# Friendly aliases people (and the card) may send.
_CEC_ALIASES = {
    "power_on": "on",
    "poweron": "on",
    "power_off": "off",
    "poweroff": "off",
    "vol+": "volume_up",
    "vol-": "volume_down",
    "volume+": "volume_up",
    "volume-": "volume_down",
    "vol_up": "volume_up",
    "vol_down": "volume_down",
    "volup": "volume_up",
    "voldown": "volume_down",
    "mute_toggle": "mute",
}


def normalize_cec(command: str) -> str:
    """Fold aliases/case/spaces into a canonical CEC command name."""
    key = str(command).strip().lower().replace(" ", "_").replace("-", "_")
    # keep the +/- forms working before underscoring stripped them
    raw = str(command).strip().lower().replace(" ", "")
    if raw in _CEC_ALIASES:
        return _CEC_ALIASES[raw]
    if key in _CEC_ALIASES:
        return _CEC_ALIASES[key]
    return key


# --- Scaler / EDID selector values -------------------------------------------
SCALER_MODES = {"bypass": 0, "scale_4k_1080p": 1, "auto": 3}
SCALER_MODE_NAMES = {0: "bypass", 1: "scale_4k_1080p", 3: "auto"}

# --- Presets ------------------------------------------------------------------
MAX_PRESETS = 8

# --- Additional services ------------------------------------------------------
SERVICE_RECALL_PRESET = "recall_preset"
SERVICE_SAVE_PRESET = "save_preset"
SERVICE_CLEAR_PRESET = "clear_preset"
SERVICE_RENAME_PRESET = "rename_preset"
SERVICE_SET_SCALER = "set_scaler"
SERVICE_SET_EDID = "set_edid"
SERVICE_SET_ARC = "set_arc"
SERVICE_SET_PANEL_LOCK = "set_panel_lock"
SERVICE_SET_BEEP = "set_beep"

# --- Options: preset select ---------------------------------------------------
CONF_ENABLE_PRESETS = "enable_presets"
DEFAULT_ENABLE_PRESETS = True
