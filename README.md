# Moneta Thermostat — Home Assistant Integration (EVO)

[![HACS Custom Repository](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/hacs/integration)
[![GitHub Release](https://img.shields.io/github/v/release/managerfx/moneta-homeassistant-integration-evo)](https://github.com/managerfx/moneta-homeassistant-integration-evo/releases)

Home Assistant custom integration for the **Delta Control / Moneta** district-heating thermostat, powered by the [PlanetSmartCity](https://portal.planetsmartcity.com) cloud backend.

> **EVO** — complete rewrite of the original integration with full entity coverage, token update flow, per-zone season handling, programmable schedule service, and independent present/absent setpoint controls.

---

## Features

| Entity type | What it exposes |
|---|---|
| `climate` | Mode (off / heat / cool / auto) + target temperature |
| `number` | Present temperature, Absent temperature (per zone) |
| `sensor` | External temperature, per-zone temperature, schedule status |
| `binary_sensor` | Occupancy (atHome), Holiday mode |

- ⛅ **Season-aware**: zone 2 is only active in winter; entities become `unavailable` in summer automatically
- 🔑 **Token update**: update Bearer token from HA UI without reinstalling
- 📅 **Schedule service**: set weekly programming bands via `moneta_thermostat_evo.set_zone_schedule`
- 🔁 **Polling interval**: configurable (min 5 minutes)

---

## Requirements

- Home Assistant 2024.1 or newer
- A valid Bearer token from the PlanetSmartCity

### Obtaining the Bearer token

1. Open the **PlanetHome** mobile app and log in
2. Intercept the network traffic (Charles Proxy, mitmproxy, or browser DevTools)
3. Look for a request to `portal.planetsmartcity.com/api/v3/sensors_data_request`
4. Copy the `Authorization: Bearer <token>` header value

The token has a long expiry (months). You can update it anytime from **Settings → Integrations → Moneta Thermostat → Configure**.

---

## Installation via HACS

1. In HA, go to **HACS → Integrations → ⋮ → Custom repositories**
2. Add `https://github.com/managerfx/moneta-homeassistant-integration-evo` as **Integration**
3. Search for **Moneta Thermostat** and install
4. Restart Home Assistant
5. Go to **Settings → Integrations → + Add Integration → Moneta Thermostat**
6. Enter your Bearer token and polling interval

---

## Entities

### Climate (one per zone)

| Mode | Behaviour |
|---|---|
| `off` | Zone turned off |
| `heat` / `cool` | Manual fixed temperature |
| `auto` | Follows weekly schedule; `target_temperature` is read-only (shows `effective_setpoint`) |

Extra attributes: `at_home`, `at_home_for_scheduler`, `setpoint_selected`, `holiday_active`, `effective_setpoint`, `schedule` (full JSON)

### Number (two per zone)

- **Present temperature** — temperature used when "at home" is active
- **Absent temperature** — setback temperature used when away

Both are settable at any time, independently of the current mode.

### Sensor

- **External Temperature** — outdoor sensor from the thermostat
- **Zone X Temperature** — indoor temperature per zone (unavailable for zones missing in the current season)
- **Active Scheduling** — indicates if there are active schedules (`active`, `inactive`, or `unknown`)
- **Schedule** — displays the first zone's weekly schedule in human-readable format. Contiguous days sharing the same bands are grouped; days with no active bands are omitted. Groups are separated by ` | ` and multiple bands within a day by `, `.
  - All days same → `MON-SUN 05:00-08:00, 13:30-20:30`
  - Two groups → `MON-FRI 07:00-22:30 | SAT-SUN 09:00-23:00`
  - Non-contiguous days → `MON 07:00-22:30 | WED 07:00-22:30 | FRI 07:00-22:30 | SAT-SUN 09:00-23:00`

### Binary Sensor

- **Thermostat Presence** (`occupancy`) — reflects `atHome` flag (set by physical thermostat button only, read-only from API)
- **Holiday Mode** — reflects `holidayActive` flag (set by physical thermostat button only, read-only from API)
- **Party Mode** — exposes `mode=party` (Boost) with expiration metadata; updates automatically when the backend reports a comfort override

> ⚠️ **Note**: `atHome` and `holidayActive` can only be changed via the physical thermostat panel. The API ignores attempts to set these fields remotely.

### Button

- **Refresh State** — forces an immediate API poll by invalidating the cached client state and asking the coordinator for an update, useful when you want to confirm the latest thermostat response without waiting for the next interval.

---

## Schedule Service

To update the weekly programming:

```yaml
service: moneta_thermostat_evo.set_zone_schedule
data:
  zone_id: "1"
  step: 30          # slot size in minutes (15 or 30)
  schedule:
    - day: MON
      bands:
        - id: 1
          setpointType: present
          start: {hour: 7, min: 0}
          end: {hour: 22, min: 30}
    - day: TUE
      bands: []     # empty = entire day uses 'absent' setpoint
    - day: WED
      bands:
        - id: 1
          setpointType: present
          start: {hour: 7, min: 0}
          end: {hour: 22, min: 30}
    - day: THU
      bands: []
    - day: FRI
      bands:
        - id: 1
          setpointType: present
          start: {hour: 7, min: 0}
          end: {hour: 22, min: 30}
    - day: SAT
      bands:
        - id: 1
          setpointType: present
          start: {hour: 9, min: 0}
          end: {hour: 23, min: 0}
    - day: SUN
      bands:
        - id: 1
          setpointType: present
          start: {hour: 9, min: 0}
          end: {hour: 23, min: 0}
```

With this configuration the **Schedule** sensor would display:
```
MON 07:00-22:30 | WED 07:00-22:30 | FRI 07:00-22:30 | SAT-SUN 09:00-23:00
```
-(TUE and THU have no active bands and are omitted; SAT and SUN share the same bands and are grouped)

<details>
<summary><strong>Verifying schedule updates</strong></summary>

1. Call `moneta_thermostat_evo.set_zone_schedule` from Developer Tools → Services and examine the service response (success/failure). A successful call invalidates the cached state and forces the coordinator to refresh immediately.
2. Watch the **Schedule** sensor and per-zone `calendar` attributes to confirm the uploaded bands appear; they are rebuilt from the API response via `MonetaFirstZoneScheduleSensor::_build_schedule_value`.
3. The API client `set_schedule_by_zone_id` already mirrors the working request structure from the original plugin (UTC step/schedule payload), so if the service completes without errors the thermostat accepts the new program.

</details>

---

## Differences from v1.x

| Feature | v1.x | v2.0 (EVO) |
|---|---|---|
| Present/absent setpoints | Exposed as climate dual-range | **Separate `number` entities** |
| Schedule | Not exposed | **Visible as attribute + service** |
| Token update | Reinstall required | **Options flow in HA UI** |
| Zone 2 (winter only) | Could crash in summer | **`unavailable` entity in summer** |
| Holiday mode | Not exposed | **Binary sensor** |
| set_off / set_auto | Zone 1 only | **All zones** |

---

## Credits

Reverse-engineered from the [moneta-homebridge-plugin](https://github.com/managerfx/moneta-homebridge-plugin) TypeScript implementation.
