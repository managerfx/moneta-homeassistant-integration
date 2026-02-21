# Moneta Thermostat – Home Assistant Integration

Custom component per Home Assistant che replica la business logic del [moneta-homebridge-plugin](https://github.com/felicelombardi/moneta-homebridge-plugin), integrando il termostato Delta Controls via le API cloud di **PlanetSmartCity**.

## Entità create

| Entità | Tipo | Descrizione |
|---|---|---|
| `climate.thermostat_zone_<N>` | Climate | Una per ogni zona (heat/cool/auto/off) |
| `binary_sensor.thermostat_presence` | Binary Sensor | Presenza in casa (atHome zona 1) |
| `sensor.external_temperature` | Sensor | Temperatura esterna |

## Installazione

1. Copia la cartella `custom_components/moneta_thermostat/` nella directory `custom_components/` della tua installazione di Home Assistant
2. Riavvia Home Assistant
3. Vai in **Impostazioni → Dispositivi e servizi → Aggiungi integrazione**
4. Cerca **"Moneta Thermostat"**
5. Inserisci il tuo Bearer token (lo stesso usato nel Homebridge plugin, campo `accessToken`)
6. Imposta l'intervallo di polling (default: 10 minuti, minimo: 5)

## Configurazione

| Campo | Tipo | Default | Descrizione |
|---|---|---|---|
| `access_token` | string | — | Bearer token dell'API PlanetSmartCity |
| `polling_interval` | number | 10 | Intervallo di polling in minuti (min 5) |

## Business logic

Identica al plugin Homebridge:

- **AUTO**: Schedula automatica. In inverno → `target_temp_high` = temperatura *presente*, `target_temp_low` = temperatura *assente*. In estate il contrario.
- **HEAT / COOL**: Modalità manuale. Usa la temperatura `present` corrente come setpoint.
- **OFF**: Zona impostata su OFF con `expiration=0` e `effectiveSetpoint = temp+1`.
- Il cambio di modalità invalida la cache e interroga subito le API.
