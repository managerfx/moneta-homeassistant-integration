# Moneta Thermostat – Home Assistant Integration

Custom component per Home Assistant che integra il termostato **Delta Controls** tramite l'API cloud di PlanetSmartCity.

Replica la stessa business logic del plugin Homebridge [`moneta-homebridge-plugin`](https://github.com/managerfx/moneta-homebridge-plugin).

---

## ⚠️ Come ottenere il Bearer Token

> **Importante:** Prima di configurare l'integrazione devi recuperare il tuo Bearer Token.

1. **Accedi all'app mobile** PlanetSmartCity con le tue credenziali
2. Vai su **[https://managerfx.github.io/PlanetHack/](https://managerfx.github.io/PlanetHack/)**
3. Inserisci le tue credenziali (email e password) dell'app mobile
4. Il sito ti mostrerà il Bearer Token da copiare

Conserva questo token: lo inserirai nel campo **Bearer Token** durante la configurazione.

---

## Installazione

### Metodo 1 – HACS (consigliato)

1. Apri **HACS** in Home Assistant
2. Clicca sul menu **⋮ → Custom repositories**
3. Incolla l'URL: `https://github.com/managerfx/moneta-homeassistant-integration`
4. Categoria: **Integration** → **Add**
5. Cerca **"Moneta Thermostat"** → **Download**
6. **Riavvia Home Assistant**

### Metodo 2 – Manuale

1. Scarica o clona questo repository
2. Copia la cartella `custom_components/moneta_thermostat/` nella directory `custom_components/` della tua installazione di Home Assistant
3. **Riavvia Home Assistant**

---

## Configurazione

Dopo il riavvio:

1. Vai in **Impostazioni → Dispositivi e servizi → Aggiungi integrazione**
2. Cerca **"Moneta Thermostat"**
3. Compila il form:

| Campo | Descrizione | Default |
|---|---|---|
| **Bearer Token** | Il token recuperato su PlanetHack | — |
| **Polling Interval** | Frequenza di aggiornamento (minuti, min 5) | `10` |

4. Clicca **Invia** — le entità verranno create automaticamente

---

## Entità create

| Entità | Tipo | Descrizione |
|---|---|---|
| `climate.thermostat_zone_1` | Climate | Termostato zona 1 |
| `climate.thermostat_zone_N` | Climate | Una entità per ogni zona |
| `binary_sensor.thermostat_presence` | Binary Sensor | Presenza in casa (atHome) |
| `sensor.external_temperature` | Sensor | Temperatura esterna |

Le entità supportano le modalità: **Auto**, **Heat**, **Cool**, **Off**.

---

## Note

- Il token viene generato dall'app mobile PlanetSmartCity: ricordati di accedere all'app prima di usare PlanetHack, altrimenti la sessione potrebbe non essere aggiornata.
- La cache dei dati viene invalidata automaticamente ad ogni modifica, garantendo dati sempre aggiornati.
