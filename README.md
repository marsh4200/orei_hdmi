# 🖥️ OREI HDMI Matrix for Home Assistant

A custom [Home Assistant](https://www.home-assistant.io/) integration by **@marsh4200** for controlling and monitoring **OREI HDMI Matrix Switches** via **TCP/IP**.

This integration allows you to manage HDMI inputs, outputs, and power directly from Home Assistant — completely **local**, with **no cloud dependency**.

---

[![Add to HACS](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=marsh4200&repository=orei_hdmi&category=integration)
<a href="https://my.home-assistant.io/redirect/config_flow_start/?domain=orei_hdmi" target="_blank">
  <img src="https://my.home-assistant.io/badges/config_flow_start.svg" alt="Configure" />
</a>

---

## ⚙️ Features

| Feature | Description |
|----------|--------------|
| 🎛️ **Input Switching** | Change HDMI input routing for each output. |
| 🔌 **Power Control** | Turn matrix ON/OFF directly from Home Assistant. |
| 🧠 **Auto Detection** | Automatically detects number of outputs (up to 4). |
| 🖲️ **Config Flow UI** | Configure IP & Port directly in the HA UI. |
| 🌐 **Local TCP Control** | No cloud — full LAN communication using Telnet-like commands. |

---

## 🧩 Installation

### 🔹 Option 1 — Install via HACS 🧠

Simply click the **blue “Open My HACS Repository”** button above.  
This will automatically open HACS and add the **OREI HDMI Matrix (Local)** integration to your Home Assistant — no manual steps needed. 🧠

Once added, install it from HACS, **restart Home Assistant**, and click the **Integrate OREI HDMI Matrix** button to finish setup.

**Enter your Matrix details:**  
- **IP Address:** Enter the local IP address of your OREI HDMI Matrix (for example `192.168.88.150`)  
- **TCP Port:** Default is `23` unless you’ve configured it differently  
- Click **Submit** to complete setup  

---

> 💡 **Tip:** You can confirm your Matrix’s IP address from your router’s **DHCP client list** or on the **device’s front panel / web menu** under **Network Settings**.
