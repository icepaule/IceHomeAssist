# Node-RED Konfiguration für LED-Matrix Displays

## Übersicht

Jedes Matrix-Display wird über einen eigenen Node-RED Flow gesteuert.
Die Flows lesen Sensordaten aus Home Assistant und senden formatierte
Texte per MQTT an die Tasmota-Geräte.

## Architektur

```
┌─────────────────────────────────────────────────────────┐
│                      Node-RED                           │
│                                                         │
│  ┌──────────┐   ┌──────────────┐   ┌────────────────┐  │
│  │ HA State │──►│  Formatierung │──►│ MQTT Publisher │  │
│  │ Changed  │   │  (Function)   │   │                │  │
│  └──────────┘   └──────────────┘   └───────┬────────┘  │
│                                             │           │
│  ┌──────────┐   ┌──────────────┐            │           │
│  │ Inject   │──►│  Dimmer      │────────────┤           │
│  │ (Cron)   │   │  Tag/Nacht   │            │           │
│  └──────────┘   └──────────────┘            │           │
└─────────────────────────────────────────────┼───────────┘
                                              │
                              MQTT (Mosquitto 10.10.12.100:1883)
                                              │
                    ┌─────────────────────────┼────────────────────┐
                    │                         │                    │
          cmnd/Matrix1/          cmnd/Matrix2/           cmnd/Matrix3/
          DisplayText            DisplayText             DisplayText
          DisplayDimmer          DisplayDimmer            DisplayDimmer
```

## MQTT Topics

| Display | Text-Topic | Dimmer-Topic |
|---------|-----------|-------------|
| Matrix1 | `cmnd/Matrix1/DisplayText` | `cmnd/Matrix1/DisplayDimmer` |
| Matrix2 | `cmnd/Matrix2/DisplayText` | `cmnd/Matrix2/DisplayDimmer` |
| Matrix3 | `cmnd/Matrix3/DisplayText` | `cmnd/Matrix3/DisplayDimmer` |
| LED-Matrix2 (ESPHome) | `led-matrix2/display/time` + `led-matrix2/display/pv` | - |

## Flow: Matrix1 (PV-Matrix, Sonnenstand-basiert)

**Tab**: `Matrix1 (PV-Matrix)`
**Display**: 4 Module (32x8), Rot, ESP-12F, Standort Schuppen

### Phasen-Logik (Sonnenstand-gesteuert)

```
┌─────────────────────────────────────────────────────────┐
│                    Tagesablauf                           │
│                                                         │
│  Nacht          ──► Display AUS                         │
│  Sunrise - 30min ──► Vortags-Ertrag "4.5kW"  Dimmer 20│
│  PV ≥ 30W       ──► Aktuelle Leistung "350W"          │
│  PV < 30W        ──► Tagesertrag "3.2kW"              │
│  Sonnenuntergang ──► Dimmer auf 10                      │
│  21:00 - 22:00   ──► PV Lebensleistung "2.79M" (MWh)  │
│  22:00            ──► Display AUS                       │
└─────────────────────────────────────────────────────────┘
```

### Phasen

| Phase | Bedingung | Anzeige | Beispiel |
|-------|-----------|---------|----------|
| `off` | 22:00 - Sunrise-30min | Display aus | - |
| `morning` | Sunrise-30min, PV < 30W | Vortags-Ertrag | "4.5kW" |
| `producing` | PV ≥ 30W | Aktuelle Leistung | "350W" |
| `idle` | PV < 30W (nach Produktion) | Tagesertrag | "3.2kW" |
| `lifetime` | 21:00 - 22:00 | PV Lebensleistung | "2.79M" |

### Datenquellen (Home Assistant)

| Sensor | Verwendung |
|--------|-----------|
| `sensor.pv_leistung` | Aktuelle PV-Leistung in Watt |
| `sensor.pv_energie_heute` | Tagesertrag in kWh (Tasmota ENERGY.Today) |
| `sensor.pv_energie_gestern` | Vortags-Ertrag in kWh (Tasmota ENERGY.Yesterday) |
| `sensor.pv_energie_gesamt` | Gesamt-PV-Produktion in kWh (Tasmota ENERGY.Total) |
| `sun.sun` | Sonnenstand + next_rising/next_setting |

### Formatierung (max 5 Zeichen, kein Scrollen)

```javascript
// kWh-Anzeige (Morgen / Idle)
if (kwh < 10)    → "4.5kW"   // 5 Zeichen (. ist schmal)
if (kwh < 100)   → "12.3k"   // W weglassen
if (kwh >= 100)  → "100k"    // gerundet

// Leistung (Producing)
if (watts < 10000) → "350W"  // bis "9999W"
if (watts >= 10000) → "10kW" // Umrechnung in kW

// Lebensleistung (MWh)
if (mwh < 10)    → "2.79M"   // 2 Dezimalen
if (mwh < 100)   → "25.1M"   // 1 Dezimale
if (mwh >= 100)  → "100M"    // gerundet
```

### Helligkeit (automatisch)

| Zeitpunkt | Dimmer | Aktion |
|-----------|--------|--------|
| Display einschalten (Sunrise-30min) | 20 | Power ON |
| Sonnenuntergang | 10 | Abend-Dimm |
| 22:00 | - | Power OFF |

---

## Flow: Matrix2 (Uhr + PV)

**Tab**: `Matrix2 (Uhr + PV)`
**Display**: 4 Module (32x8), Rot

### Anzeige-Logik

```
┌──────────────────────────────────────────┐
│ 50 Sekunden: Uhrzeit (Standard)          │
│   "18:05" (blinkender Doppelpunkt)       │
├──────────────────────────────────────────┤
│ 10 Sekunden: PV-Daten (Flash)            │
│   ≥15W:  "1234W"  (aktuelle Leistung)   │
│   <15W:  "12.3kW" (Tagesertrag/Vortag)  │
└──────────────────────────────────────────┘
     ◄──────── 60s Zyklus ────────►
```

**Gleiche Datenquellen und Formatierung wie Matrix1, nur umgekehrte Priorität.**

---

## Flow: Matrix3 (Uhr+PV+Alerts)

**Tab**: `Matrix3 (Uhr+PV+Alerts)`
**Display**: 8 Module (64x8), 4x Rot + 4x Blau

### Display-Layout

```
◄─── Rote Module (32px) ───►◄── Blaue Module (32px) ──►
┌───────────────────────────┬──────────────────────────┐
│  Linke Hälfte (5 Zeichen) │ Rechte Hälfte (4 Zeichen)│
│  Uhrzeit / PV-Daten       │ Alert-Code (rotierend)   │
│  "18:05"  oder  "1234W"   │ "THW!" oder "UNWT"       │
└───────────────────────────┴──────────────────────────┘
```

### Anzeige-Logik

```
┌─────────────────────────────────────────────────────────────┐
│ LINKE HÄLFTE (5 Zeichen):                                   │
│   50s Uhrzeit: "18:05" (blinkender Doppelpunkt)             │
│   10s PV-Flash: "1234W" oder "12.3kW"                       │
│                                                             │
│ RECHTE HÄLFTE (4 Zeichen):                                  │
│   Höchster aktiver Alert, rotiert alle 3 Sekunden           │
│   Kein Alert → leer                                         │
│                                                             │
│ Kombiniert: "18:05 THW!" oder "1234W UNWT"                  │
└─────────────────────────────────────────────────────────────┘
```

### Alert-System

Alerts werden alle 5 Sekunden aus Home Assistant gesammelt und nach Priorität sortiert.
Mehrere aktive Alerts rotieren alle 3 Sekunden.

Jeder Alert kann per `input_boolean` in Home Assistant ein/ausgeschaltet werden.

#### Prioritäten und Quellen

```
PRIO 1 - KRITISCH (sofortige Aufmerksamkeit)
├── ALM!  ← binary_sensor.divera_alarm_aktiv (THW-Alarm)
└── NNET  ← binary_sensor.fritz_box_connection = off (Internet)

PRIO 2 - HOCH (wichtige Warnungen)
├── NINA  ← sensor.nina_munchen_warnungen_anzahl > 0
├── UNWT  ← sensor.dwd_munchen_warnungen > 0
├── HCHW  ← sensor.pegel_isar_muenchen > 600cm
├── THW!  ← binary_sensor.divera_ruckmeldung_fallig
└── NETZ  ← sensor.netzwerk_status ≠ "Alles OK"

PRIO 3 - MITTEL (Info-Alerts)
├── KATZ  ← sensor.petkit_status ≠ "ok"
├── MESH  ← sensor.mesh_letzte_nachricht (< 30 min alt)
├── Bxx   ← sensor.mesh_*_battery < 20%
├── WSCH  ← input_boolean.waschmaschine_warten = on
└── TRCK  ← input_boolean.trockner_warten = on

PRIO 4 - NIEDRIG (Hinweise)
├── TEUR  ← sensor.tibber_price_level = VERY_EXPENSIVE
└── BIL!  ← sensor.tibber_price_level = VERY_CHEAP
```

#### HA Input Booleans (Alert-Toggles)

| Entity ID | Beschreibung |
|-----------|-------------|
| `input_boolean.matrix3_thw_alarm` | THW Alarm anzeigen |
| `input_boolean.matrix3_internet_offline` | Internet-Ausfall anzeigen |
| `input_boolean.matrix3_nina_warnung` | NINA Warnungen |
| `input_boolean.matrix3_dwd_wetter` | DWD Unwetter |
| `input_boolean.matrix3_hochwasser` | Hochwasser Isar |
| `input_boolean.matrix3_thw_rueckmeldung` | THW Rückmeldung |
| `input_boolean.matrix3_netzwerk` | Netzwerk-Status |
| `input_boolean.matrix3_petkit` | Petkit Katzen-Feeder |
| `input_boolean.matrix3_meshtastic` | Meshtastic Nachrichten |
| `input_boolean.matrix3_mesh_batterie` | Mesh Batterie niedrig |
| `input_boolean.matrix3_waschmaschine` | Waschmaschine fertig |
| `input_boolean.matrix3_trockner` | Trockner fertig |
| `input_boolean.matrix3_tibber_teuer` | Tibber teuer |
| `input_boolean.matrix3_tibber_guenstig` | Tibber günstig |

---

## Tasmota DisplayText Befehle

### Basis-Befehle

| Befehl | Beschreibung |
|--------|-------------|
| `DisplayText <text>` | Text anzeigen (zentriert, scrollt bei Überlänge) |
| `DisplayClear` | Display löschen |
| `DisplayDimmer 0-100` | Helligkeit (0=aus, 100=max) |
| `DisplayRotate 0\|2` | 0=Normal, 2=Upside-Down (Standard) |
| `DisplayClock 0\|1\|2` | 0=Aus, 1=12h, 2=24h Uhr |
| `DisplayScrollDelay 0-15` | Scroll-Geschwindigkeit (0=schnell) |
| `DisplayBlinkrate 0-3` | Blinkrate (0=aus) |
| `Power ON\|OFF` | Display an/aus (behält Buffer) |

### Font

Eingebauter 6x8 Pixel Font. Unterstützt ASCII 0x20-0x7F.
Mit `USE_UTF8_LATIN1`: zusätzlich Umlaute (ä, ö, ü, ß, etc.)

### Zeichenkapazität

| Module | Pixel | Zeichen (6px breit) |
|--------|-------|-------------------|
| 4x (32px) | 32 | 5 Zeichen |
| 8x (64px) | 64 | 10 Zeichen |

---

## Node-RED Import

Die Flows können aus `config/nodered/matrix_flows.json` importiert werden:

1. Node-RED öffnen
2. Hamburger-Menü → Import
3. Datei auswählen oder JSON einfügen
4. Deploy

### Voraussetzungen

- Node `node-red-contrib-home-assistant-websocket` installiert
- MQTT-Broker konfiguriert (Mosquitto auf 10.10.12.100:1883)
- Home Assistant Sensoren vorhanden (PV, Divera, NINA, etc.)
