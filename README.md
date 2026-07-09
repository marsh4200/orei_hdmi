# 🖥️ OREI HDMI Matrix for Home Assistant

A local, cloud-free [Home Assistant](https://www.home-assistant.io/) integration by **@marsh4200** for controlling and monitoring **OREI HDMI Matrix switches**. It talks to the matrix over its **HTTP JSON API** when available (richer status and real port names) and **falls back to telnet** automatically — telnet also carries CEC.

Route inputs to outputs, control power, send CEC commands, and see live HDMI link status — all from Home Assistant, with a matching Lovelace card.

[![Add to HACS](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=marsh4200&repository=orei_hdmi&category=integration)

---

## ✨ Features

- 🔀 **Dual transport** — prefers the device's HTTP JSON API, falls back to telnet; CEC uses telnet either way
- 🧠 **Auto-detection** of the model and input/output counts — no manual counting
- 🏷 **Real port names** pulled from the device (HTTP transport) — pre-filled in the naming form
- 🔌 **Power control** (master on/off) as a `switch`
- 🎛 **Per-zone media players** with source selection and CEC on/off
- 🎚 **Per-output routing `select`** entities (automation-friendly, kept for backwards compatibility)
- 🔗 **HDMI link sensors** — see which inputs/outputs actually have a cable connected
- ⏭ **Optional "next source" buttons** per zone
- 🧩 **One device** grouping every entity, with stable unique IDs (rename freely in the UI)
- 🏷 **Friendly naming** of inputs and outputs via the options flow
- 🔄 **Services**: `refresh`, `set_route`, `set_cec`, `cycle_source`
- ⚡ **Persistent connection** with automatic reconnect (no socket churn)
- 🃏 **Companion Lovelace card** with zone auto-discovery

---

## 🧩 Installation

### Via HACS (recommended)

1. Click the **Add to HACS** button above (or add `https://github.com/marsh4200/orei_hdmi` as a custom repository of type *Integration*).
2. Install, then **restart Home Assistant**.
3. Go to **Settings → Devices & Services → Add Integration**, search **OREI HDMI Matrix**.
4. Enter the **IP address**. Ports are optional — **HTTP** defaults to `80` (tried first) and **telnet** to `8000` (some OREI models use `23`). The transport, model and I/O counts are detected automatically.

### Manual

Copy `custom_components/orei_hdmi` into `<config>/custom_components/` and restart.

> 💡 Find the matrix IP from your router's DHCP list or the unit's front panel / web UI.

---

## ⚙️ Options

After setup, open the integration's **Configure** button:

- **Name inputs & outputs** — give friendly names like *Apple TV* or *Living Room*. Blank falls back to `Input N` / `Output N`.
- **Polling & entities** — set the poll interval and toggle which entity types are created (media players, routing selects, buttons, link sensors).

---

## 🧱 Entities

| Type | Example | Description |
|------|---------|-------------|
| `switch` | Power | Master matrix power |
| `media_player` | Living Room | Zone with source dropdown + CEC on/off |
| `select` | Living Room source | Input routed to this output |
| `binary_sensor` | Apple TV link | HDMI cable/link present (connectivity) |
| `button` | Living Room next source | Cycles to the next input (optional) |

---

## 🃏 Companion card

The card is **bundled and auto-registered** as a Lovelace resource when the integration
loads — no manual resource step needed. Just add it to a dashboard:

```yaml
type: custom:orei-hdmi-card
# everything below is optional:
# title: Cinema Matrix
# host: 192.168.10.150      # only if you run more than one matrix
# show_links: true
# columns: 2
```

The card auto-discovers zones from the integration, so no entity list is needed. (A copy
also lives at `card/orei-hdmi-card.js` if you prefer to register it manually.)

---

## 🔧 Services

```yaml
# Route input 2 to output 1
service: orei_hdmi.set_route
data:
  input: 2
  output: 1

# CEC: turn on the display on output 1
service: orei_hdmi.set_cec
data:
  target: output
  id: 1
  command: "on"

# Cycle output 1 to the next input
service: orei_hdmi.cycle_source
data:
  output: 1

# Force an immediate state refresh
service: orei_hdmi.refresh
```

> If you have multiple matrices, add `host: <ip>` to target a specific one.

---

## 📝 Notes

- Adding stable unique IDs means entities from very early builds (which had none) may reappear with new IDs — the old ones can be safely removed.
- On the **HTTP transport**, routing/power/status use the CGI JSON API (`video switch`, `set poweronoff`, `get video/output/input status`); **CEC** falls back to telnet on the CEC port (default `23`, configurable in options).
- On the **telnet transport**, everything uses OREI's ASCII protocol (`s in X av out Y!`, `s power 1!`, `r av out 0!`, `s cec ...!`, `r link ...!`).

---

© 2025 marsh4200 — MIT licensed (see `LICENSE`).
