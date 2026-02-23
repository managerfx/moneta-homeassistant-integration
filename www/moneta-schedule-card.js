/**
 * Moneta Schedule Card  v3.0
 * Lovelace custom card — visualizza e modifica la pianificazione settimanale
 * del termostato Moneta (EVO).
 *
 * Installazione:
 *   1. Copia in <ha-config>/www/moneta-schedule-card.js
 *   2. Lovelace → Risorse → /local/moneta-schedule-card.js  (Modulo JavaScript)
 *   3. Card YAML:
 *        type: custom:moneta-schedule-card
 *        entity: climate.NOME_ENTITA
 *        zone_id: "1"                     # opzionale, default "1"
 *        title: "Pianificazione Soggiorno" # opzionale
 *        show_current_time: true           # default true
 */

// ── Costanti ────────────────────────────────────────────────────────────────

const DAY_LABELS = {
  MON: "Lunedì", TUE: "Martedì", WED: "Mercoledì",
  THU: "Giovedì", FRI: "Venerdì", SAT: "Sabato", SUN: "Domenica",
};
const DAY_ORDER = ["MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN"];

const C_PRESENT = "#FF8C69";
const C_ABSENT = "#4ECDC4";
const C_NOW_LINE = "#FFD166";
const STEP_MIN = 30; // granularità snap in minuti

const SERVICE_DOMAIN = "moneta_thermostat_evo";
const SERVICE_NAME = "set_zone_schedule";

// ── Helpers ─────────────────────────────────────────────────────────────────

const toMin = (h, m) => h * 60 + m;
const fromMin = (m) => ({ hour: Math.floor(m / 60), min: m % 60 });
const pad = (n) => String(n).padStart(2, "0");
const fmtTime = (h, m) => `${pad(h)}:${pad(m)}`;
const snapTo = (minutes, step = STEP_MIN) => Math.round(minutes / step) * step;

function parseTime(str) {
  const [h, m] = str.split(":").map(Number);
  return { hour: h || 0, min: m || 0 };
}

function buildSegments(bands) {
  const total = 1440;
  const sorted = [...bands].sort(
    (a, b) => toMin(a.start.hour, a.start.min) - toMin(b.start.hour, b.start.min)
  );
  const segs = [];
  let cur = 0;
  for (const b of sorted) {
    const s = toMin(b.start.hour, b.start.min);
    const e = toMin(b.end.hour, b.end.min);
    if (s > cur) segs.push({ s: cur, e: s, type: "absent" });
    segs.push({ s, e, type: b.setpointType === "present" ? "present" : "absent" });
    cur = e;
  }
  if (cur < total) segs.push({ s: cur, e: total, type: "absent" });
  return segs;
}

function nowMinutes() {
  const d = new Date();
  return d.getHours() * 60 + d.getMinutes();
}

function todayKey() {
  const days = ["SUN", "MON", "TUE", "WED", "THU", "FRI", "SAT"];
  return days[new Date().getDay()];
}

function deepClone(obj) { return JSON.parse(JSON.stringify(obj)); }

// ── Card ─────────────────────────────────────────────────────────────────────

class MonetaScheduleCard extends HTMLElement {

  constructor() {
    super();
    this._editing = null;   // { day, bands }
    this._saving = false;
    this._error = null;
    this._toast = null;   // testo del toast di conferma
    this._toastTimer = null;
  }

  set hass(hass) {
    this._hass = hass;
    this._render();
  }

  setConfig(config) {
    if (!config.entity) throw new Error("Specifica 'entity'.");
    this._config = {
      zone_id: "1",
      show_current_time: true,
      ...config,
    };
  }

  getCardSize() { return 7; }

  // ── Render ──────────────────────────────────────────────────────────────

  _render() {
    if (!this._hass || !this._config) return;

    const stateObj = this._hass.states[this._config.entity];
    if (!stateObj) {
      this.innerHTML = `<ha-card><div class="err">Entità non trovata: ${this._config.entity}</div></ha-card>${CARD_CSS}`;
      return;
    }

    const schedule = stateObj.attributes.schedule || [];
    const entityName = this._config.title || stateObj.attributes.friendly_name || this._config.entity;
    const byDay = {};
    for (const e of schedule) byDay[e.day] = e.bands || [];

    const today = todayKey();
    const nowMin = nowMinutes();
    const showNowLine = this._config.show_current_time !== false;

    // ── time axis ───────────────────────────────────────────────────────
    const ticks = [0, 3, 6, 9, 12, 15, 18, 21, 24].map(h => {
      const pct = ((h / 24) * 100).toFixed(2);
      return `<span class="tick" style="left:${pct}%">${pad(h)}:00</span>`;
    }).join("");

    // ── day rows ────────────────────────────────────────────────────────
    const rows = DAY_ORDER.map(day => {
      const bands = byDay[day] || [];
      const segments = buildSegments(bands);
      const total = 1440;
      const isActive = this._editing?.day === day;
      const isToday = day === today;

      // bar segments
      const barSegs = segments.map(s => {
        const pct = (((s.e - s.s) / total) * 100).toFixed(3);
        const color = s.type === "present" ? C_PRESENT : C_ABSENT;
        const sh = fromMin(s.s), eh = fromMin(s.e);
        const lbl = `${s.type === "present" ? "In casa" : "Fuori casa"}: ${fmtTime(sh.hour, sh.min)}–${fmtTime(eh.hour, eh.min)}`;
        return `<div class="seg" style="width:${pct}%;background:${color}" title="${lbl}"></div>`;
      }).join("");

      // "now" vertical line (only on today's bar)
      const nowLineHtml = (showNowLine && isToday)
        ? `<div class="now-line" style="left:${((nowMin / total) * 100).toFixed(2)}%"></div>`
        : "";

      // edit panel
      let editPanel = "";
      if (isActive) {
        const bandRows = this._editing.bands.map((b, i) => `
          <div class="band-row" data-idx="${i}">
            <button class="type-btn ${b.setpointType === "present" ? "present" : "absent"}"
                    data-action="toggle-type" data-idx="${i}">
              ${b.setpointType === "present" ? "🏠 In casa" : "🚶 Fuori"}
            </button>
            <input class="time-input" type="time"
                   value="${fmtTime(b.start.hour, b.start.min)}"
                   data-action="set-start" data-idx="${i}">
            <span class="time-sep">→</span>
            <input class="time-input" type="time"
                   value="${fmtTime(b.end.hour, b.end.min)}"
                   data-action="set-end" data-idx="${i}">
            <button class="del-btn" data-action="del-band" data-idx="${i}" title="Rimuovi fascia">✕</button>
          </div>`).join("");

        editPanel = `
          <div class="edit-panel">
            ${bandRows || `<div class="no-bands">Nessuna fascia — tutto il giorno: Fuori casa</div>`}
            <div class="edit-actions">
              <button class="btn-add" data-action="add-band">＋ Aggiungi fascia</button>
              <div class="spacer"></div>
              <button class="btn-cancel" data-action="cancel-edit">Annulla</button>
              <button class="btn-save${this._saving ? " saving" : ""}" data-action="save-day"
                      ${this._saving ? "disabled" : ""}>
                ${this._saving ? '<span class="spinner"></span> Salvo…' : "💾 Salva"}
              </button>
            </div>
            ${this._error ? `<div class="save-error">⚠ ${this._error}</div>` : ""}
          </div>`;
      }

      return `
        <div class="day-row${isActive ? " active" : ""}${isToday ? " today" : ""}" data-day="${day}">
          <div class="day-head" data-action="edit-day" data-day="${day}">
            <span class="day-label">${DAY_LABELS[day]}${isToday ? " <span class='today-dot'></span>" : ""}</span>
            <div class="bar-wrap">
              <div class="bar">${barSegs}${nowLineHtml}</div>
            </div>
            <span class="edit-icon">${isActive ? "▲" : "✎"}</span>
          </div>
          ${editPanel}
        </div>`;
    }).join("");

    // ── toast ────────────────────────────────────────────────────────────
    const toastHtml = this._toast
      ? `<div class="toast show">${this._toast}</div>`
      : `<div class="toast"></div>`;

    this.innerHTML = `
      <ha-card>
        <div class="card-header">
          <span class="title">🗓 ${entityName}</span>
          <span class="subtitle">Zona ${this._config.zone_id}</span>
        </div>
        <div class="card-body">
          ${rows}
          <div class="time-axis">${ticks}</div>
          <div class="legend">
            <span class="dot" style="background:${C_ABSENT}"></span> Fuori casa &nbsp;
            <span class="dot" style="background:${C_PRESENT}"></span> In casa
            ${showNowLine ? `&nbsp; <span class="dot" style="background:${C_NOW_LINE};border-radius:2px;width:3px;height:12px"></span> Ora` : ""}
          </div>
        </div>
        ${toastHtml}
      </ha-card>
      ${CARD_CSS}`;

    this._attachListeners();
  }

  // ── Event handling ───────────────────────────────────────────────────────

  _attachListeners() {
    this.querySelectorAll("[data-action]").forEach(el => {
      el.addEventListener("click", e => this._handleClick(e));
    });
    this.querySelectorAll("input[data-action]").forEach(el => {
      el.addEventListener("change", e => this._handleChange(e));
    });
  }

  _getByDay(day) {
    const stateObj = this._hass.states[this._config.entity];
    const schedule = stateObj?.attributes?.schedule || [];
    const entry = schedule.find(e => e.day === day);
    return deepClone(entry?.bands || []);
  }

  _handleClick(e) {
    const el = e.target.closest("[data-action]");
    if (!el) return;
    const action = el.dataset.action;
    const idx = parseInt(el.dataset.idx ?? -1, 10);

    switch (action) {
      case "edit-day": {
        const day = el.closest("[data-day]")?.dataset.day;
        if (!day) return;
        this._editing = (this._editing?.day === day) ? null : { day, bands: this._getByDay(day) };
        this._error = null;
        this._render();
        break;
      }

      case "toggle-type": {
        if (!this._editing || idx < 0) return;
        const b = this._editing.bands[idx];
        b.setpointType = b.setpointType === "present" ? "absent" : "present";
        this._render();
        break;
      }

      case "add-band": {
        if (!this._editing) return;
        const nextId = (this._editing.bands.reduce((mx, b) => Math.max(mx, b.id || 0), 0)) + 1;
        this._editing.bands.push({
          id: nextId,
          setpointType: "present",
          start: { hour: 7, min: 0 },
          end: { hour: 22, min: 0 },
        });
        this._render();
        break;
      }

      case "del-band": {
        if (!this._editing || idx < 0) return;
        this._editing.bands.splice(idx, 1);
        this._render();
        break;
      }

      case "cancel-edit": {
        this._editing = null;
        this._error = null;
        this._render();
        break;
      }

      case "save-day": {
        this._saveDay();
        break;
      }
    }
  }

  _handleChange(e) {
    const el = e.target.closest("[data-action]");
    if (!el || !this._editing) return;
    const action = el.dataset.action;
    const idx = parseInt(el.dataset.idx, 10);

    if (action === "set-start" || action === "set-end") {
      const t = parseTime(el.value);
      // snap to STEP_MIN
      const snapped = snapTo(toMin(t.hour, t.min));
      const clamped = Math.max(0, Math.min(snapped, 1440 - STEP_MIN));
      const { hour, min } = fromMin(clamped);
      const key = action === "set-start" ? "start" : "end";
      this._editing.bands[idx][key] = { hour, min };
      // update input display to snapped value
      el.value = fmtTime(hour, min);
      this._renderBarOnly(this._editing.day);
    }
  }

  /** Ridisegna solo la barra del giorno in editing (evita perdita focus). */
  _renderBarOnly(day) {
    const bands = this._editing?.bands || [];
    const segments = buildSegments(bands);
    const total = 1440;
    const bar = this.querySelector(`.day-row[data-day="${day}"] .bar`);
    if (!bar) return;
    bar.innerHTML = segments.map(s => {
      const pct = (((s.e - s.s) / total) * 100).toFixed(3);
      const color = s.type === "present" ? C_PRESENT : C_ABSENT;
      return `<div class="seg" style="width:${pct}%;background:${color}"></div>`;
    }).join("");
  }

  async _saveDay() {
    if (!this._editing || this._saving) return;
    const { day, bands } = this._editing;

    // ── Validation ──────────────────────────────────────────────────────
    for (const b of bands) {
      const s = toMin(b.start.hour, b.start.min);
      const e = toMin(b.end.hour, b.end.min);
      if (s >= e) {
        this._error = `Fascia non valida: l'orario di inizio deve essere prima della fine.`;
        this._render();
        return;
      }
    }
    const sorted = [...bands].sort((a, b) =>
      toMin(a.start.hour, a.start.min) - toMin(b.start.hour, b.start.min)
    );
    for (let i = 0; i < sorted.length - 1; i++) {
      const endA = toMin(sorted[i].end.hour, sorted[i].end.min);
      const stB = toMin(sorted[i + 1].start.hour, sorted[i + 1].start.min);
      if (endA > stB) {
        this._error = "Le fasce si sovrappongono — correggile prima di salvare.";
        this._render();
        return;
      }
    }

    // ── Build full week (solo il giorno editato cambia) ─────────────────
    const stateObj = this._hass.states[this._config.entity];
    const existing = stateObj?.attributes?.schedule || [];
    const fullSched = DAY_ORDER.map(d => {
      if (d === day) return { day: d, bands };
      const e = existing.find(x => x.day === d);
      return { day: d, bands: e?.bands || [] };
    });

    this._saving = true;
    this._error = null;
    this._render();

    try {
      await this._hass.callService(SERVICE_DOMAIN, SERVICE_NAME, {
        zone_id: this._config.zone_id,
        step: STEP_MIN,
        schedule: fullSched,
      });
      this._editing = null;
      this._showToast(`✅ Pianificazione ${DAY_LABELS[day]} salvata`);
    } catch (err) {
      this._error = `Errore: ${err?.message ?? err}`;
    }

    this._saving = false;
    this._render();
  }

  _showToast(msg) {
    if (this._toastTimer) clearTimeout(this._toastTimer);
    this._toast = msg;
    this._toastTimer = setTimeout(() => {
      this._toast = null;
      this._render();
    }, 3000);
  }
}

// ── CSS ──────────────────────────────────────────────────────────────────────

const CARD_CSS = `<style>
  moneta-schedule-card { display: block; }

  ha-card {
    background: var(--ha-card-background, #1c1c1e);
    border-radius: 14px;
    overflow: hidden;
    font-family: var(--primary-font-family, sans-serif);
    position: relative;
  }

  /* ── header ── */
  .card-header {
    padding: 14px 18px 12px;
    border-bottom: 1px solid rgba(255,255,255,0.08);
    display: flex;
    align-items: baseline;
    gap: 10px;
  }
  .title   { font-size: 1rem; font-weight: 600; color: var(--primary-text-color,#fff); }
  .subtitle{ font-size: .78rem; color: var(--secondary-text-color,#888); }

  /* ── card body ── */
  .card-body { padding: 10px 16px 16px; }

  /* ── day rows ── */
  .day-row { margin: 6px 0; border-radius: 10px; overflow: hidden; }
  .day-row.active { background: rgba(255,255,255,0.05); }
  .day-row.today  { }

  .day-head {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 5px 4px;
    cursor: pointer;
    border-radius: 8px;
  }
  .day-head:hover { background: rgba(255,255,255,0.04); }

  .day-label {
    width: 82px; flex-shrink: 0;
    font-size: 0.84rem; font-weight: 500;
    color: var(--primary-text-color,#ddd);
    display: flex; align-items: center; gap: 5px;
  }
  .today-dot {
    display: inline-block; width: 6px; height: 6px;
    border-radius: 50%; background: ${C_NOW_LINE};
    flex-shrink: 0;
  }

  /* ── bar ── */
  .bar-wrap { flex: 1; position: relative; }
  .bar {
    height: 18px; border-radius: 9px;
    display: flex; overflow: visible;
    background: ${C_ABSENT};
    box-shadow: 0 1px 4px rgba(0,0,0,0.4);
    position: relative;
    clip-path: inset(0 round 9px);
  }
  .seg { height: 100%; transition: opacity .15s; }
  .seg:hover { opacity: .75; }

  /* "now" line */
  .now-line {
    position: absolute;
    top: -2px; bottom: -2px;
    width: 2px;
    background: ${C_NOW_LINE};
    border-radius: 2px;
    z-index: 2;
    box-shadow: 0 0 4px ${C_NOW_LINE};
  }

  .edit-icon {
    flex-shrink: 0; width: 22px; text-align: center;
    font-size: 0.78rem; color: var(--secondary-text-color,#888);
  }
  .day-head:hover .edit-icon { color: ${C_NOW_LINE}; }

  /* ── edit panel ── */
  .edit-panel { padding: 8px 10px 10px; }

  .band-row {
    display: flex; align-items: center; gap: 6px;
    margin: 6px 0; flex-wrap: wrap;
  }

  .type-btn {
    border: none; border-radius: 14px; padding: 4px 10px;
    font-size: 0.76rem; font-weight: 600; cursor: pointer;
    transition: filter .15s; white-space: nowrap;
  }
  .type-btn:hover { filter: brightness(1.15); }
  .type-btn.present { background: ${C_PRESENT}; color: #1c1c1e; }
  .type-btn.absent  { background: ${C_ABSENT};  color: #1c1c1e; }

  .time-input {
    border: 1px solid rgba(255,255,255,0.2);
    border-radius: 6px; padding: 4px 6px;
    background: rgba(255,255,255,0.07);
    color: var(--primary-text-color,#fff);
    font-size: 0.82rem; width: 88px;
  }
  .time-input:focus { outline: none; border-color: ${C_NOW_LINE}; }

  .time-sep { color: var(--secondary-text-color,#888); font-size: .85rem; }

  .del-btn {
    border: none; background: transparent;
    color: #e55; font-size: 0.9rem; cursor: pointer;
    padding: 2px 6px; border-radius: 4px;
  }
  .del-btn:hover { background: rgba(229,85,85,.15); }

  .no-bands {
    font-size: .8rem; color: var(--secondary-text-color,#888);
    padding: 4px 2px; font-style: italic;
  }

  .edit-actions {
    display: flex; align-items: center; gap: 8px; margin-top: 10px;
    flex-wrap: wrap;
  }
  .spacer { flex: 1; }

  .btn-add {
    border: 1px solid ${C_ABSENT}; border-radius: 14px;
    background: transparent; color: ${C_ABSENT};
    padding: 4px 12px; font-size: .8rem; cursor: pointer;
  }
  .btn-add:hover { background: rgba(78,205,196,.12); }

  .btn-cancel {
    border: 1px solid rgba(255,255,255,0.2); border-radius: 14px;
    background: transparent; color: var(--secondary-text-color,#aaa);
    padding: 4px 12px; font-size: .8rem; cursor: pointer;
  }
  .btn-cancel:hover { background: rgba(255,255,255,.06); }

  .btn-save {
    border: none; border-radius: 14px;
    background: ${C_PRESENT}; color: #1c1c1e;
    padding: 4px 14px; font-size: .8rem; font-weight: 600; cursor: pointer;
    display: flex; align-items: center; gap: 5px;
    transition: filter .15s;
  }
  .btn-save:hover:not(.saving) { filter: brightness(1.1); }
  .btn-save.saving { opacity: .6; cursor: default; }

  /* spinner */
  .spinner {
    display: inline-block; width: 10px; height: 10px;
    border: 2px solid rgba(0,0,0,0.3);
    border-top-color: #1c1c1e;
    border-radius: 50%;
    animation: spin .7s linear infinite;
  }
  @keyframes spin { to { transform: rotate(360deg); } }

  .save-error {
    margin-top: 8px; font-size: .78rem;
    color: #e55; padding: 4px 8px;
    background: rgba(229,85,85,.1); border-radius: 6px;
  }

  /* ── time axis ── */
  .time-axis {
    position: relative; height: 16px;
    margin: 6px 0 0 92px;
    font-size: .68rem; color: var(--secondary-text-color,#888);
  }
  .tick {
    position: absolute; transform: translateX(-50%);
    white-space: nowrap;
  }

  /* ── legend ── */
  .legend {
    margin-top: 10px; font-size: .78rem;
    color: var(--secondary-text-color,#aaa);
    display: flex; align-items: center; gap: 5px; flex-wrap: wrap;
  }
  .dot {
    display: inline-block; width: 10px; height: 10px; border-radius: 50%;
    flex-shrink: 0;
  }

  /* ── toast ── */
  .toast {
    position: absolute; bottom: 14px; left: 50%;
    transform: translateX(-50%) translateY(8px);
    background: rgba(30,30,30,0.95);
    border: 1px solid rgba(255,255,255,0.12);
    color: var(--primary-text-color,#fff);
    padding: 8px 16px; border-radius: 20px;
    font-size: .82rem; white-space: nowrap;
    opacity: 0; pointer-events: none;
    transition: opacity .3s, transform .3s;
    z-index: 10;
  }
  .toast.show {
    opacity: 1;
    transform: translateX(-50%) translateY(0);
  }

  .err { padding: 16px; color: var(--error-color,#e55); }

  /* ── responsive ── */
  @media (max-width: 400px) {
    .day-label { width: 64px; font-size: .78rem; }
    .type-btn  { font-size: .7rem; padding: 3px 7px; }
    .time-input{ width: 76px; font-size: .76rem; }
  }
</style>`;

// ── Registration ─────────────────────────────────────────────────────────────

customElements.define("moneta-schedule-card", MonetaScheduleCard);

console.info(
  "%c MONETA-SCHEDULE-CARD %c v3.0 ",
  "background:#4ECDC4;color:#000;font-weight:bold;border-radius:4px 0 0 4px;padding:2px 6px",
  "background:#FF8C69;color:#000;font-weight:bold;border-radius:0 4px 4px 0;padding:2px 6px"
);
