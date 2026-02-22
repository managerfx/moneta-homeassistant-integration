/**
 * Moneta Schedule Card  v2.0
 * Lovelace custom card — visualizza e modifica la pianificazione settimanale.
 *
 * Installaione:
 *   1. Copia in <ha-config>/www/moneta-schedule-card.js
 *   2. Lovelace → Risorse → /local/moneta-schedule-card.js  (Modulo JavaScript)
 *   3. Card YAML:
 *        type: custom:moneta-schedule-card
 *        entity: climate.NOME_ENTITA
 *        zone_id: "1"           # opzionale, di default "1"
 */

const DAY_LABELS = {
    MON: "Lunedì", TUE: "Martedì", WED: "Mercoledì",
    THU: "Giovedì", FRI: "Venerdì", SAT: "Sabato", SUN: "Domenica",
};
const DAY_ORDER = ["MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN"];

const C_PRESENT = "#FF8C69";
const C_ABSENT = "#4ECDC4";
const C_EDIT = "#FFD166";

const SERVICE_DOMAIN = "moneta_thermostat_evo";
const SERVICE_NAME = "set_zone_schedule";

// ── helpers ──────────────────────────────────────────────────────────────────

function toMin(h, m) { return h * 60 + m; }
function fromMin(m) { return { hour: Math.floor(m / 60), min: m % 60 }; }
function pad(n) { return String(n).padStart(2, "0"); }
function fmtTime(h, m) { return `${pad(h)}:${pad(m)}`; }

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

function deepClone(obj) { return JSON.parse(JSON.stringify(obj)); }

// ── Card ─────────────────────────────────────────────────────────────────────

class MonetaScheduleCard extends HTMLElement {

    constructor() {
        super();
        // editing state: { day: "MON", bands: [...] } | null
        this._editing = null;
        this._saving = false;
        this._error = null;
    }

    set hass(hass) {
        this._hass = hass;
        this._render();
    }

    setConfig(config) {
        if (!config.entity) throw new Error("Specifica 'entity'.");
        this._config = config;
    }

    getCardSize() { return 6; }

    // ── render ─────────────────────────────────────────────────────────────

    _render() {
        if (!this._hass || !this._config) return;

        const stateObj = this._hass.states[this._config.entity];
        if (!stateObj) {
            this.innerHTML = `<ha-card><div class="err">Entità non trovata: ${this._config.entity}</div></ha-card>${BASE_CSS}`;
            return;
        }

        const schedule = stateObj.attributes.schedule || [];
        const entityName = stateObj.attributes.friendly_name || this._config.entity;
        const byDay = {};
        for (const e of schedule) byDay[e.day] = e.bands || [];

        // ── day rows ──────────────────────────────────────────────────────────
        const rows = DAY_ORDER.map(day => {
            const bands = byDay[day] || [];
            const segments = buildSegments(bands);
            const total = 1440;
            const isActive = this._editing?.day === day;

            const barSegs = segments.map(s => {
                const pct = (((s.e - s.s) / total) * 100).toFixed(3);
                const color = s.type === "present" ? C_PRESENT : C_ABSENT;
                const sh = fromMin(s.s), eh = fromMin(s.e);
                const lbl = `${s.type === "present" ? "In casa" : "Fuori casa"}: ${fmtTime(sh.hour, sh.min)}–${fmtTime(eh.hour, eh.min)}`;
                return `<div class="seg" style="width:${pct}%;background:${color}" title="${lbl}"></div>`;
            }).join("");

            // edit panel (only shown for active day)
            let editPanel = "";
            if (isActive) {
                const bandRows = this._editing.bands.map((b, i) => `
          <div class="band-row" data-band="${i}">
            <button class="type-btn ${b.setpointType === "present" ? "present" : "absent"}"
                    data-action="toggle-type" data-idx="${i}">
              ${b.setpointType === "present" ? "🏠 In casa" : "🚶 Fuori casa"}
            </button>
            <input class="time-input" type="time" value="${fmtTime(b.start.hour, b.start.min)}"
                   data-action="set-start" data-idx="${i}">
            <span class="time-sep">→</span>
            <input class="time-input" type="time" value="${fmtTime(b.end.hour, b.end.min)}"
                   data-action="set-end" data-idx="${i}">
            <button class="del-btn" data-action="del-band" data-idx="${i}" title="Rimuovi fascia">✕</button>
          </div>`).join("");

                editPanel = `
          <div class="edit-panel">
            ${bandRows || `<div class="no-bands">Nessuna fascia (tutto fuori casa)</div>`}
            <div class="edit-actions">
              <button class="btn-add" data-action="add-band">＋ Aggiungi fascia</button>
              <div class="spacer"></div>
              <button class="btn-cancel" data-action="cancel-edit">Annulla</button>
              <button class="btn-save ${this._saving ? "saving" : ""}" data-action="save-day">
                ${this._saving ? "Salvo…" : "💾 Salva"}
              </button>
            </div>
            ${this._error ? `<div class="save-error">⚠ ${this._error}</div>` : ""}
          </div>`;
            }

            return `
        <div class="day-row ${isActive ? "active" : ""}" data-day="${day}">
          <div class="day-head" data-action="edit-day" data-day="${day}">
            <span class="day-label">${DAY_LABELS[day]}</span>
            <div class="bar">${barSegs}</div>
            <span class="edit-icon">${isActive ? "▲" : "✎"}</span>
          </div>
          ${editPanel}
        </div>`;
        }).join("");

        // time axis ticks
        const ticks = [0, 4, 8, 12, 16, 20, 24].map(h => {
            const pct = ((h / 24) * 100).toFixed(1);
            return `<span style="position:absolute;left:${pct}%;transform:translateX(-50%)">${pad(h)}:00</span>`;
        }).join("");

        this.innerHTML = `
      <ha-card>
        <div class="card-header">
          <span class="title">🗓 Pianificazione — ${entityName}</span>
        </div>
        <div class="card-body">
          ${rows}
          <div class="time-axis">${ticks}</div>
          <div class="legend">
            <span class="dot" style="background:${C_ABSENT}"></span> Fuori casa &nbsp;
            <span class="dot" style="background:${C_PRESENT}"></span> In casa
          </div>
        </div>
      </ha-card>
      ${BASE_CSS}`;

        this._attachListeners();
    }

    // ── event handling ──────────────────────────────────────────────────────

    _attachListeners() {
        this.querySelectorAll("[data-action]").forEach(el => {
            el.addEventListener("click", e => this._handleClick(e));
            el.addEventListener("change", e => this._handleChange(e));
        });
        this.querySelectorAll("[data-action='set-start'], [data-action='set-end']").forEach(el => {
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
                if (this._editing?.day === day) {
                    this._editing = null; // toggle off
                } else {
                    this._editing = { day, bands: this._getByDay(day) };
                    this._error = null;
                }
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
                    start: { hour: 8, min: 0 },
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
            const key = action === "set-start" ? "start" : "end";
            this._editing.bands[idx][key] = { hour: t.hour, min: t.min };
            // keep bar in sync without full re-render (just re-render)
            this._renderBarOnly(this._editing.day);
        }
    }

    /** Lightweight: only redraw the bar of a given day without losing input focus. */
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

        // Validate: no overlapping bands
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
        // start < end
        for (const b of bands) {
            if (toMin(b.start.hour, b.start.min) >= toMin(b.end.hour, b.end.min)) {
                this._error = "Ogni fascia deve avere orario di inizio < fine.";
                this._render();
                return;
            }
        }

        // Build full week schedule (only the edited day changes)
        const stateObj = this._hass.states[this._config.entity];
        const existing = stateObj?.attributes?.schedule || [];
        const fullSched = DAY_ORDER.map(d => {
            if (d === day) return { day: d, bands };
            const e = existing.find(x => x.day === d);
            return { day: d, bands: e?.bands || [] };
        });

        const zoneId = this._config.zone_id ?? "1";

        this._saving = true;
        this._error = null;
        this._render();

        try {
            await this._hass.callService(SERVICE_DOMAIN, SERVICE_NAME, {
                zone_id: zoneId,
                step: 30,
                schedule: fullSched,
            });
            this._editing = null;
        } catch (err) {
            this._error = `Errore: ${err?.message ?? err}`;
        }

        this._saving = false;
        this._render();
    }
}

// ── CSS ────────────────────────────────────────────────────────────────────

const BASE_CSS = `<style>
  moneta-schedule-card { display: block; }

  ha-card {
    background: var(--ha-card-background, #1c1c1e);
    border-radius: 12px;
    overflow: hidden;
    font-family: var(--primary-font-family, sans-serif);
  }

  .card-header {
    padding: 14px 16px 10px;
    border-bottom: 1px solid rgba(255,255,255,0.08);
  }
  .title { font-size: 1rem; font-weight: 600; color: var(--primary-text-color, #fff); }

  .card-body { padding: 10px 16px 16px; }

  /* ── day rows ── */
  .day-row { margin: 8px 0; border-radius: 8px; overflow: hidden; }
  .day-row.active { background: rgba(255,255,255,0.05); }

  .day-head {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 4px 2px;
    cursor: pointer;
    border-radius: 6px;
  }
  .day-head:hover { background: rgba(255,255,255,0.04); }

  .day-label {
    width: 80px; flex-shrink: 0;
    font-size: 0.86rem; font-weight: 500;
    color: var(--primary-text-color, #ddd);
  }

  .bar {
    flex: 1; height: 18px; border-radius: 9px;
    display: flex; overflow: hidden;
    background: ${C_ABSENT};
    box-shadow: 0 1px 4px rgba(0,0,0,0.4);
  }
  .seg { height: 100%; transition: opacity .15s; }
  .seg:hover { opacity: .75; }
  .bar .seg:first-child { border-radius: 9px 0 0 9px; }
  .bar .seg:last-child  { border-radius: 0 9px 9px 0; }
  .bar .seg:only-child  { border-radius: 9px; }

  .edit-icon {
    flex-shrink: 0; width: 20px; text-align: center;
    font-size: 0.8rem; color: var(--secondary-text-color, #888);
  }
  .day-head:hover .edit-icon { color: ${C_EDIT}; }

  /* ── edit panel ── */
  .edit-panel { padding: 8px 10px 10px; }

  .band-row {
    display: flex; align-items: center; gap: 6px;
    margin: 6px 0; flex-wrap: wrap;
  }

  .type-btn {
    border: none; border-radius: 14px; padding: 4px 10px;
    font-size: 0.78rem; font-weight: 600; cursor: pointer;
    transition: filter .15s;
  }
  .type-btn:hover { filter: brightness(1.15); }
  .type-btn.present { background: ${C_PRESENT}; color: #1c1c1e; }
  .type-btn.absent  { background: ${C_ABSENT};  color: #1c1c1e; }

  .time-input {
    border: 1px solid rgba(255,255,255,0.2);
    border-radius: 6px; padding: 3px 6px;
    background: rgba(255,255,255,0.07);
    color: var(--primary-text-color, #fff);
    font-size: 0.82rem; width: 86px;
  }
  .time-sep { color: var(--secondary-text-color,#888); font-size:.85rem; }

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
    transition: filter .15s;
  }
  .btn-save:hover:not(.saving) { filter: brightness(1.1); }
  .btn-save.saving { opacity: .6; cursor: default; }

  .save-error {
    margin-top: 8px; font-size: .78rem;
    color: #e55; padding: 4px 6px;
    background: rgba(229,85,85,.1); border-radius: 6px;
  }

  /* ── time axis + legend ── */
  .time-axis {
    position: relative; height: 18px;
    margin: 6px 0 0 90px;
    font-size: .7rem; color: var(--secondary-text-color,#888);
  }
  .legend {
    margin-top: 10px; font-size: .78rem;
    color: var(--secondary-text-color,#aaa);
    display: flex; align-items: center; gap: 4px;
  }
  .dot { display:inline-block; width:10px; height:10px; border-radius:50%; }
  .err { padding:16px; color:var(--error-color,#e55); }
</style>`;

customElements.define("moneta-schedule-card", MonetaScheduleCard);

console.info(
    "%c MONETA-SCHEDULE-CARD %c v2.0 ",
    "background:#4ECDC4;color:#000;font-weight:bold;border-radius:4px 0 0 4px;padding:2px 6px",
    "background:#FF8C69;color:#000;font-weight:bold;border-radius:0 4px 4px 0;padding:2px 6px"
);
