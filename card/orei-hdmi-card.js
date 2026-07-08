/**
 * OREI HDMI Matrix Card
 * A companion Lovelace card for the orei_hdmi integration.
 *
 * It auto-discovers matrix zones (media_player entities exposing the
 * `orei_hdmi` attribute) so no manual entity list is required, and renders a
 * matrix-style grid of zones, each with a source dropdown, plus a master power
 * toggle and (optionally) input link status.
 *
 * Minimal config:
 *   type: custom:orei-hdmi-card
 *
 * Optional config:
 *   title: Cinema Matrix        # header title
 *   host: 192.168.10.150        # filter to one matrix if you have several
 *   power: switch.orei...power  # override auto-detected power switch
 *   show_links: true            # show input link dots (default true)
 *   columns: 2                  # grid columns (default auto)
 */
class OreiHdmiCard extends HTMLElement {
  setConfig(config) {
    this._config = config || {};
  }

  set hass(hass) {
    this._hass = hass;
    this._render();
  }

  getCardSize() {
    return 3;
  }

  static getStubConfig() {
    return { type: "custom:orei-hdmi-card" };
  }

  _zones() {
    const hass = this._hass;
    const host = this._config.host;
    return Object.values(hass.states)
      .filter(
        (s) =>
          s.entity_id.startsWith("media_player.") &&
          s.attributes &&
          s.attributes.orei_hdmi === true &&
          (!host || s.attributes.host === host)
      )
      .sort((a, b) => (a.attributes.output || 0) - (b.attributes.output || 0));
  }

  _powerEntity() {
    if (this._config.power) return this._hass.states[this._config.power];
    // First OREI power switch. For multi-matrix setups, set `power:` explicitly.
    return Object.values(this._hass.states).find(
      (s) =>
        s.entity_id.startsWith("switch.") &&
        /orei/i.test(s.entity_id) &&
        /power/i.test(s.entity_id)
    );
  }

  _linkSensors(host) {
    return Object.values(this._hass.states).filter(
      (s) =>
        s.entity_id.startsWith("binary_sensor.") &&
        /orei/i.test(s.entity_id) &&
        /link/i.test(s.entity_id)
    );
  }

  _callSelect(entityId, source) {
    this._hass.callService("media_player", "select_source", {
      entity_id: entityId,
      source,
    });
  }

  _togglePower(entityId) {
    this._hass.callService("switch", "toggle", { entity_id: entityId });
  }

  _render() {
    if (!this._hass) return;
    const zones = this._zones();
    const power = this._powerEntity();
    const isOn = power ? power.state === "on" : true;
    const model =
      zones.length && zones[0].attributes
        ? this._deviceName(zones[0])
        : "OREI HDMI Matrix";
    const title = this._config.title || model;
    const showLinks = this._config.show_links !== false;
    const cols =
      this._config.columns ||
      Math.min(zones.length > 3 ? 2 : 1, 2) ||
      1;

    if (!this._root) {
      this.attachShadow({ mode: "open" });
      this._root = this.shadowRoot;
    }

    const linkDots = showLinks ? this._renderLinks(zones) : "";

    this._root.innerHTML = `
      <style>
        ha-card { padding: 16px; }
        .head {
          display: flex; align-items: center; justify-content: space-between;
          margin-bottom: 12px;
        }
        .title { font-size: 1.2rem; font-weight: 600; color: var(--primary-text-color); }
        .power {
          border: none; cursor: pointer; border-radius: 18px; padding: 6px 14px;
          font-weight: 600; font-size: .85rem;
          background: ${isOn ? "var(--primary-color)" : "var(--disabled-color, #888)"};
          color: var(--text-primary-color, #fff);
        }
        .grid {
          display: grid; gap: 10px;
          grid-template-columns: repeat(${cols}, minmax(0, 1fr));
        }
        .zone {
          background: var(--secondary-background-color);
          border-radius: 12px; padding: 12px;
          opacity: ${isOn ? "1" : "0.5"};
        }
        .zone-name { font-weight: 600; color: var(--primary-text-color); margin-bottom: 8px; }
        select {
          width: 100%; padding: 8px; border-radius: 8px;
          background: var(--card-background-color); color: var(--primary-text-color);
          border: 1px solid var(--divider-color);
        }
        .links { margin-top: 14px; display: flex; flex-wrap: wrap; gap: 6px; }
        .dot {
          display: inline-flex; align-items: center; gap: 4px;
          font-size: .72rem; color: var(--secondary-text-color);
          background: var(--secondary-background-color);
          padding: 3px 8px; border-radius: 10px;
        }
        .dot i { width: 8px; height: 8px; border-radius: 50%; display: inline-block; }
        .on { background: var(--success-color, #4caf50); }
        .off { background: var(--error-color, #f44336); }
        .empty { color: var(--secondary-text-color); padding: 8px 0; }
      </style>
      <ha-card>
        <div class="head">
          <div class="title">${title}</div>
          ${
            power
              ? `<button class="power" id="pwr">${isOn ? "ON" : "OFF"}</button>`
              : ""
          }
        </div>
        ${
          zones.length
            ? `<div class="grid">${zones
                .map((z) => this._renderZone(z))
                .join("")}</div>`
            : `<div class="empty">No OREI zones found. Enable the media_player entities in the integration options.</div>`
        }
        ${linkDots}
      </ha-card>
    `;

    if (power) {
      const btn = this._root.getElementById("pwr");
      if (btn) btn.onclick = () => this._togglePower(power.entity_id);
    }
    zones.forEach((z) => {
      const sel = this._root.getElementById(`sel_${z.entity_id}`);
      if (sel) sel.onchange = (e) => this._callSelect(z.entity_id, e.target.value);
    });
  }

  _deviceName(zone) {
    // Best-effort friendly device/model name from the zone's friendly_name.
    const fn = zone.attributes.friendly_name || "OREI HDMI Matrix";
    return fn.replace(/\s+(Output|Zone).*$/i, "") || "OREI HDMI Matrix";
  }

  _renderZone(z) {
    const sources = z.attributes.source_list || [];
    const current = z.attributes.source || "";
    const name = z.attributes.friendly_name || z.entity_id;
    const opts = sources
      .map(
        (s) =>
          `<option value="${s}" ${s === current ? "selected" : ""}>${s}</option>`
      )
      .join("");
    return `
      <div class="zone">
        <div class="zone-name">${name}</div>
        <select id="sel_${z.entity_id}">
          ${current ? "" : '<option value="">—</option>'}${opts}
        </select>
      </div>`;
  }

  _renderLinks(zones) {
    const host = zones.length ? zones[0].attributes.host : this._config.host;
    const sensors = this._linkSensors(host);
    if (!sensors.length) return "";
    const dots = sensors
      .map((s) => {
        const on = s.state === "on";
        const label = (s.attributes.friendly_name || s.entity_id).replace(
          /\s+link$/i,
          ""
        );
        return `<span class="dot"><i class="${on ? "on" : "off"}"></i>${label}</span>`;
      })
      .join("");
    return `<div class="links">${dots}</div>`;
  }
}

customElements.define("orei-hdmi-card", OreiHdmiCard);

window.customCards = window.customCards || [];
window.customCards.push({
  type: "orei-hdmi-card",
  name: "OREI HDMI Matrix Card",
  description: "Zone routing, power and link status for the OREI HDMI Matrix integration.",
  preview: false,
});
