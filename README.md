# Moneta Thermostat

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/hacs/integration)
[![Version](https://img.shields.io/github/v/release/managerfx/moneta-homeassistant-integration)](https://github.com/managerfx/moneta-homeassistant-integration/releases)

Integrazione Home Assistant per il termostato **Delta Controls** via API cloud **PlanetSmartCity**.

---

## ⚠️ Come ottenere il Bearer Token

> Prima di configurare l'integrazione devi recuperare il tuo Bearer Token.

1. Accedi all'**app mobile PlanetSmartCity** con le tue credenziali
2. Vai su 👉 **[https://managerfx.github.io/PlanetHack/](https://managerfx.github.io/PlanetHack/)**
3. Inserisci email e password dell'app mobile
4. Copia il Bearer Token generato

---

## Installazione via HACS

1. Apri **HACS** in Home Assistant
2. **⋮ → Custom repositories** → incolla `https://github.com/managerfx/moneta-homeassistant-integration` → Categoria: **Integration**
3. Cerca **"Moneta Thermostat"** → **Download**
4. Riavvia Home Assistant

### Installazione manuale

1. Copia la cartella `custom_components/moneta_thermostat/` nella directory `custom_components/` di Home Assistant
2. Riavvia Home Assistant

---

## Configurazione

1. **Impostazioni → Dispositivi e servizi → Aggiungi integrazione**
2. Cerca **"Moneta Thermostat"**
3. Inserisci:

| Campo | Descrizione | Default |
|---|---|---|
| **Bearer Token** | Token ottenuto da PlanetHack | — |
| **Polling Interval** | Frequenza aggiornamento (min 5 minuti) | `10` |

---

## Entità

| Entità | Tipo | Descrizione |
|---|---|---|
| `climate.thermostat_zone_N` | Clima | Una per ogni zona (auto / heat / cool / off) |
| `binary_sensor.thermostat_presence` | Presenza | 🏠← in casa / 🏠→ fuori casa |
| `sensor.external_temperature` | Temperatura | Temperatura esterna |

---

## Modalità supportate

| Modalità | Comportamento |
|---|---|
| **Auto** | Schedula automatica. Usa `target_temp_high` (presente) e `target_temp_low` (assente) in inverno — invertiti in estate |
| **Heat / Cool** | Manuale. Usa la temperatura *presente* come setpoint |
| **Off** | Zona disattivata (`expiration=0`, setpoint = temp+1) |

> Il cambio di modalità invalida la cache e aggiorna immediatamente i dati.
