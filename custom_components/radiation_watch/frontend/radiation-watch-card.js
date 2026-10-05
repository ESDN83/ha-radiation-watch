/*
 * Radiation Watch card.
 * Served and registered by the radiation_watch integration, no Lovelace resource needed.
 *
 * Draws all stations from the integration in their true direction and distance around home,
 * coloured by dose rate, on a locally stored map. The wind sector shows whose air is heading
 * towards home, arcs show how long it takes to arrive. Tap toggles near and far view.
 *
 * Projection: x = east km, y = north km, flat (same as geo.offset_km and the map images).
 * Texts live in locales/<lang>.json next to this file, English is the fallback.
 */

const CARD_VERSION = "0.1.2";
const BASE = "/radiation_watch_files/frontend";
const LOCALES = {};
const LOADING = {};
const STORAGE_KEY = "radiation-watch-card-view";

// One shared promise per language: a second card on the page waits for the same download
// instead of seeing an empty entry and rendering the raw keys.
function loadLocale(lang) {
  if (!LOADING[lang]) {
    LOADING[lang] = fetch(`${BASE}/locales/${lang}.json?v=${CARD_VERSION}`)
      .then((r) => (r.ok ? r.json() : null))
      .catch(() => null)
      .then((j) => (LOCALES[lang] = j));
  }
  return LOADING[lang];
}

const esc = (s) => String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

class RadiationWatchCard extends HTMLElement {
  static getConfigForm() {
    return {
      schema: [
        { name: "entity", selector: { entity: { domain: "sensor", integration: "radiation_watch" } } },
        { name: "local_sensors", selector: { entity: { domain: "sensor", multiple: true } } },
        {
          type: "grid",
          name: "",
          schema: [
            { name: "start_view", selector: { select: { mode: "dropdown", options: ["near", "far"] } } },
            { name: "map_style", selector: { select: { mode: "dropdown", options: ["auto", "light", "dark", "none"] } } },
            { name: "warn_threshold", selector: { number: { min: 0.01, max: 1000, step: 0.01, mode: "box", unit_of_measurement: "µSv/h" } } },
            { name: "danger_threshold", selector: { number: { min: 0.01, max: 1000, step: 0.01, mode: "box", unit_of_measurement: "µSv/h" } } },
          ],
        },
        {
          type: "grid",
          name: "",
          schema: [
            { name: "color_ok", selector: { text: {} } },
            { name: "color_warn", selector: { text: {} } },
            { name: "color_danger", selector: { text: {} } },
            { name: "color_wind", selector: { text: {} } },
          ],
        },
        {
          type: "grid",
          name: "",
          schema: [
            { name: "show_status", selector: { boolean: {} } },
            { name: "show_legend", selector: { boolean: {} } },
            { name: "show_names", selector: { boolean: {} } },
            { name: "show_values", selector: { boolean: {} } },
          ],
        },
      ],
      computeLabel: (s) => {
        const t = (LOCALES[(document.querySelector("home-assistant")?.hass?.locale?.language || "en").split("-")[0]] || LOCALES.en || {}).editor || {};
        return t[s.name] || s.name;
      },
    };
  }

  static getStubConfig(hass) {
    const e = Object.keys(hass.states).find((k) => k.startsWith("sensor.") && hass.states[k].attributes.stations_entity);
    return { entity: e || "" };
  }

  setConfig(config) {
    this._config = {
      start_view: "near",
      map_style: "auto",
      warn_threshold: 0.3,
      danger_threshold: 1,
      color_ok: "var(--success-color, #43a047)",
      color_warn: "var(--warning-color, #ffa600)",
      color_danger: "var(--error-color, #db4437)",
      color_wind: "var(--primary-color, #03a9f4)",
      show_status: true,
      show_legend: true,
      show_names: true,
      show_values: true,
      local_sensors: [],
      ...config,
    };
    try {
      this._view = localStorage.getItem(STORAGE_KEY) || this._config.start_view;
    } catch (e) {
      this._view = this._config.start_view;
    }
    if (!this.shadowRoot) {
      this.attachShadow({ mode: "open" });
      this.shadowRoot.addEventListener("click", (ev) => {
        if (!ev.composedPath().some((n) => n.classList && n.classList.contains("map"))) return;
        this._view = this._view === "far" ? "near" : "far";
        try {
          localStorage.setItem(STORAGE_KEY, this._view);
        } catch (e) {
          /* private mode: view is not remembered */
        }
        this._render(true);
      });
    }
    this._render(true);
  }

  set hass(hass) {
    this._hass = hass;
    const lang = (hass.locale?.language || hass.language || "en").split("-")[0];
    if (this._lang !== lang) {
      this._lang = lang;
      Promise.all([loadLocale("en"), loadLocale(lang)]).then(() => this._render(true));
    }
    this._render(false);
  }

  getCardSize() {
    return 9;
  }

  getGridOptions() {
    return { columns: "full", rows: "auto" };
  }

  _t(path, vars = {}) {
    const get = (o) => path.split(".").reduce((a, k) => (a && a[k] !== undefined ? a[k] : undefined), o);
    let s = get(LOCALES[this._lang]) ?? get(LOCALES.en) ?? path;
    if (typeof s === "string") for (const [k, v] of Object.entries(vars)) s = s.replaceAll(`{${k}}`, v);
    return s;
  }

  _entityId() {
    if (this._config.entity) return this._config.entity;
    const h = this._hass;
    return Object.keys(h.states).find((k) => k.startsWith("sensor.") && h.states[k].attributes.stations_entity);
  }

  _render(force) {
    if (!this._hass || !this._config || !this.shadowRoot) return;
    const h = this._hass;
    const eid = this._entityId();
    const ew = eid && h.states[eid];
    const stEnt = ew && h.states[ew.attributes.stations_entity];
    const local = (this._config.local_sensors || []).map((x) => (typeof x === "string" ? { entity: x } : x));
    // Only redraw when something relevant changed, hass updates arrive many times per second.
    const key = [ew, stEnt, ...local.map((l) => h.states[l.entity]), h.themes?.darkMode, this._view];
    if (!force && this._last && key.length === this._last.length && key.every((v, i) => v === this._last[i])) return;
    this._last = key;
    if (!ew) {
      this.shadowRoot.innerHTML = `<ha-card><div style="padding:16px">${esc(this._t("errors.no_entity"))}</div></ha-card>`;
      return;
    }
    // While the integration (re)loads the sensor is unavailable and has no attributes.
    // Show that instead of drawing, the card redraws by itself once the data is back.
    if (!Array.isArray(ew.attributes.home)) {
      const st = ["unknown", "unavailable"].includes(ew.state) ? ew.state : "unavailable";
      this.shadowRoot.innerHTML = `<ha-card><ha-alert alert-type="warning" title="${esc(this._t(`status.${st}.title`))}">${esc(this._t(`status.${st}.text`))}</ha-alert><div style="height:12px"></div></ha-card>`;
      return;
    }
    // Never throw out of the hass setter: Home Assistant would replace the card with a
    // permanent configuration error until the page is reloaded.
    try {
      this.shadowRoot.innerHTML = this._html(ew, stEnt, local);
    } catch (err) {
      console.error("radiation-watch-card", err);
      this.shadowRoot.innerHTML = `<ha-card><div style="padding:16px">Radiation Watch: ${esc(err && err.message)}</div></ha-card>`;
    }
  }

  _html(ew, stEnt, local) {
    const c = this._config, h = this._hass, a = ew.attributes;
    const far = this._view === "far";
    const KM = (far ? a.radius_far : a.radius_near) || (far ? 120 : 40);
    const C = 200, R = 180, k = R / KM;
    const [hlat, hlon] = a.home;
    const rules = a.rules || {};
    const col = (v) => (v >= c.danger_threshold ? c.color_danger : v >= c.warn_threshold ? c.color_warn : c.color_ok);
    const lng = this._lang || "en";
    const f = (v, d) => Number(v).toLocaleString(lng, { minimumFractionDigits: d, maximumFractionDigits: d });
    const pt = (b, r) => [C + r * Math.sin((b * Math.PI) / 180), C - r * Math.cos((b * Math.PI) / 180)];
    const diff = (x, y) => { const d = Math.abs(x - y) % 360; return d > 180 ? 360 - d : d; };
    const pos = (lat, lon) => {
      const dy = (lat - hlat) * 111.2, dx = (lon - hlon) * 111.2 * Math.cos((hlat * Math.PI) / 180);
      return { dx, dy, d: Math.hypot(dx, dy), b: ((Math.atan2(dx, dy) * 180) / Math.PI + 360) % 360 };
    };
    const wb = a.wind_bearing, kmh = a.wind_speed_kmh;
    const wind = typeof wb === "number" && typeof kmh === "number" && kmh >= (rules.min_wind ?? 2);

    const all = ((stEnt && stEnt.attributes.stations) || []).map((x) => ({ n: x[0], v: x[3], l: x[4], ...pos(x[1], x[2]) }));
    const st = all.filter((s) => s.d <= KM);
    // Notable uses the integration's median over the whole far radius, same as the warning sensor.
    const limit = typeof a.limit === "number" ? a.limit : Infinity;
    const absT = rules.abs_threshold ?? 0.3;

    const dark = c.map_style === "dark" || (c.map_style === "auto" && h.themes?.darkMode);
    const mapUrl = c.map_style !== "none" && a.maps ? a.maps[`${far ? "far" : "near"}_${dark ? "dark" : "light"}`] : null;
    const label = dark ? "#fff" : "#111";
    const halo = dark ? "#000" : "#fff";

    let o = `<svg class="map" viewBox="-12 -12 424 424">`;
    o += `<defs><clipPath id="rw-clip"><circle cx="${C}" cy="${C}" r="${R}"/></clipPath></defs>`;
    o += mapUrl
      ? `<image href="${mapUrl}" x="${C - R}" y="${C - R}" width="${2 * R}" height="${2 * R}" clip-path="url(#rw-clip)" opacity="0.9"/>`
      : `<circle cx="${C}" cy="${C}" r="${R}" fill="var(--secondary-background-color)"/>`;
    if (wind) {
      const p1 = pt(wb - (rules.sector ?? 45), R), p2 = pt(wb + (rules.sector ?? 45), R);
      o += `<path d="M${C},${C} L${p1[0]},${p1[1]} A${R},${R} 0 0 1 ${p2[0]},${p2[1]} Z" style="fill:${c.color_wind};opacity:.18"/>`;
    }
    const rings = far ? [KM / 3, (2 * KM) / 3, KM] : [KM / 4, KM / 2, KM];
    rings.forEach((r) => {
      o += `<circle cx="${C}" cy="${C}" r="${r * k}" style="fill:none;stroke:${label};stroke-opacity:.35;stroke-dasharray:3 3"/>`;
      o += `<text x="${C + 3}" y="${C - r * k + 10}" style="font-size:8px;fill:${label};fill-opacity:.75">${f(r, 0)} km</text>`;
    });
    const dirs = this._t("directions");
    [[0, 0], [2, 90], [4, 180], [6, 270]].forEach(([i, b]) => {
      const p = pt(b, R + 9);
      o += `<text x="${p[0]}" y="${p[1] + 4}" text-anchor="middle" style="font-size:11px;font-weight:bold;fill:var(--secondary-text-color)">${esc(Array.isArray(dirs) ? dirs[i] : "")}</text>`;
    });

    // Travel time arcs: what is on the "2 h" arc now arrives in about 2 h if the wind holds.
    if (wind) {
      const sec = rules.sector ?? 45;
      const step = [15, 30, 60, 120, 180, 360, 720].find((m) => KM / ((kmh * m) / 60) <= 6) || 720;
      const lab = (m) => (m < 60 ? `${m} min` : `${m / 60} h`);
      let rmax = R;
      for (let m = step; (kmh * m) / 60 <= KM; m += step) {
        const r = ((kmh * m) / 60) * k, p1 = pt(wb - sec, r), p2 = pt(wb + sec, r), p = pt(wb - sec, r + 2);
        rmax = r;
        o += `<path d="M${p1[0]},${p1[1]} A${r},${r} 0 0 1 ${p2[0]},${p2[1]}" style="fill:none;stroke:${c.color_wind};stroke-width:1.5;stroke-opacity:.9"/>`;
        o += `<text x="${p[0]}" y="${p[1]}" text-anchor="middle" style="font-size:8px;font-weight:bold;fill:${c.color_wind};paint-order:stroke;stroke:${halo};stroke-width:2px">${lab(m)}</text>`;
      }
      const s = pt(wb, rmax), e = pt(wb, 11), len = Math.hypot(e[0] - s[0], e[1] - s[1]);
      const ux = (e[0] - s[0]) / len, uy = (e[1] - s[1]) / len, bx = e[0] - ux * 12, by = e[1] - uy * 12;
      o += `<g opacity="0.75"><line x1="${s[0]}" y1="${s[1]}" x2="${bx}" y2="${by}" style="stroke:${c.color_wind};stroke-width:3"/>`;
      o += `<polygon points="${e[0]},${e[1]} ${bx - uy * 6},${by + ux * 6} ${bx + uy * 6},${by - ux * 6}" style="fill:${c.color_wind}"/></g>`;
    }

    const upwind = [];
    st.map((s) => ({ ...s, au: s.v >= absT || s.v >= limit }))
      .sort((x, y) => x.au - y.au)
      .forEach((s) => {
        const up = s.au && wind && diff(s.b, wb) <= (rules.sector ?? 45);
        if (up) upwind.push(s);
        const x = C + s.dx * k, y = C - s.dy * k;
        const ring = up ? `stroke:${c.color_danger};stroke-width:3` : s.au ? `stroke:${c.color_warn};stroke-width:3` : `stroke:${halo};stroke-opacity:.6;stroke-width:1`;
        const small = far && !s.au;
        const land = s.l !== "DE" ? ` (${esc(s.l)})` : "";
        o += `<g><title>${esc(s.n)}${land}: ${f(s.v, 3)} µSv/h, ${f(s.d, 0)} km</title>`;
        o += `<circle cx="${x}" cy="${y}" r="${small ? 3.5 : 6}" style="fill:${col(s.v)};${ring}"/>`;
        if (!small) {
          if (c.show_values) o += `<text x="${x + 8}" y="${y + 2}" style="font-size:8.5px;font-weight:bold;fill:${label};paint-order:stroke;stroke:${halo};stroke-width:2px">${f(s.v, 3)}</text>`;
          if (c.show_names) o += `<text x="${x + 8}" y="${y + 10}" style="font-size:6.5px;fill:${label};fill-opacity:.85;paint-order:stroke;stroke:${halo};stroke-width:1.5px">${esc(s.n)}${land}</text>`;
        }
        o += `</g>`;
      });

    const own = local.map((l) => {
      const s = h.states[l.entity];
      return { name: l.name || (s && s.attributes.friendly_name) || l.entity, v: s ? parseFloat(s.state) : NaN };
    });
    const ov = own.filter((x) => !isNaN(x.v)).map((x) => x.v);
    const hm = ov.length ? Math.max(...ov) : null;
    o += `<rect x="${C - 7}" y="${C - 7}" width="14" height="14" rx="3" style="fill:${hm === null ? "var(--secondary-text-color)" : col(hm)};stroke:${label};stroke-width:2"/>`;
    o += `<text x="${C + R}" y="${C + R + 8}" text-anchor="end" style="font-size:7px;fill:var(--secondary-text-color)">${esc(this._t("attribution"))}</text></svg>`;

    // Text below the map
    const dot = (cl) => `<span class="dot" style="background:${cl}"></span>`;
    let t = `<div class="text">`;
    t += `<b>${esc(this._t(far ? "view.far" : "view.near", { km: f(KM, 0) }))}</b>, ${esc(this._t("stations", { n: st.length }))}. ${esc(this._t(far ? "tap.to_near" : "tap.to_far"))}`;
    t += wind
      ? `<br><b>${esc(this._t("wind.from", { dir: Array.isArray(dirs) ? dirs[Math.round(wb / 45) % 8] : "" }))}</b> (${Math.round(wb)}°), ${f(kmh, 1)} km/h. ${esc(this._t("wind.hint"))}`
      : `<br>${esc(this._t("wind.none"))}`;
    if (own.length) t += `<br>${esc(this._t("home"))}: ${own.map((x) => (isNaN(x.v) ? `${esc(x.name)} ${esc(this._t("no_value"))}` : `${dot(col(x.v))}${esc(x.name)} ${f(x.v, 3)}`)).join(" ")} µSv/h`;
    if (typeof a.median === "number") t += `<br>${esc(this._t("median", { median: f(a.median, 3), limit: f(Math.min(limit, absT), 3) }))}`;
    if (c.show_legend) {
      t += `<br>${dot(c.color_ok)}${esc(this._t("legend.below", { v: f(c.warn_threshold, 1) }))} ${dot(c.color_warn)}${esc(this._t("legend.from", { v: f(c.warn_threshold, 1) }))} ${dot(c.color_danger)}${esc(this._t("legend.from", { v: f(c.danger_threshold, 1) }))} µSv/h. ${esc(this._t("legend.rings"))}`;
    }
    upwind.sort((x, y) => x.d - y.d).slice(0, 5).forEach((s) => {
      const m = Math.round((s.d / kmh) * 60);
      const eta = m >= 60 ? `${Math.floor(m / 60)} h ${m % 60} min` : `${m} min`;
      t += `<br><b style="color:${c.color_danger}">${esc(this._t("eta", { name: s.n + (s.l !== "DE" ? ` (${s.l})` : ""), km: f(s.d, 0), eta }))}</b>`;
    });
    if (upwind.length) t += `<br>${esc(this._t("eta_note"))}`;
    if (a.map_status === "building") t += `<br><i>${esc(this._t("map_building"))}</i>`;
    t += `</div>`;

    let status = "";
    if (c.show_status) {
      const type = { calm: "success", notable: "warning", warning: "error" }[ew.state] || "info";
      status = `<ha-alert alert-type="${type}" title="${esc(this._t(`status.${ew.state}.title`))}">${esc(this._t(`status.${ew.state}.text`, { km: f(a.radius_far, 0) }))}</ha-alert>`;
    }

    return `<style>
      ha-card { overflow: hidden; }
      ha-alert { display: block; margin: 12px 12px 0; }
      .map { display: block; width: 100%; max-width: 640px; margin: 0 auto; cursor: pointer; }
      .text { padding: 8px 16px 14px; font-size: 13px; line-height: 1.6; }
      .dot { display: inline-block; width: 10px; height: 10px; border-radius: 50%; margin: 0 4px 0 8px; vertical-align: middle; }
    </style><ha-card>${status}${o}${t}</ha-card>`;
  }
}

if (!customElements.get("radiation-watch-card")) {
  customElements.define("radiation-watch-card", RadiationWatchCard);
  window.customCards = window.customCards || [];
  window.customCards.push({
    type: "radiation-watch-card",
    name: "Radiation Watch",
    description: "Dose rate stations around home with wind sector and travel time arcs.",
    preview: false,
  });
  console.info(`%c RADIATION-WATCH-CARD %c ${CARD_VERSION} `, "background:#43a047;color:#fff", "background:#333;color:#fff");
}
