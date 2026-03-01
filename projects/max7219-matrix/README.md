# IceMatrix - MAX7219 LED Matrix Displays mit Tasmota & Home Assistant

Steuerung von MAX7219 8x8 LED Dot-Matrix Displays über Tasmota, Node-RED und Home Assistant.

![Overview](docs/images/overview.png)

## Hardware

| Display | Module | Farbe | ESP | Funktion |
|---------|--------|-------|-----|----------|
| Matrix1 (PV-Matrix) | 4x MAX7219 (32x8) | Rot | ESP-12F | PV-Leistung (Sonnenstand-basiert) |
| Matrix2 | 4x MAX7219 (32x8) | Rot | ESP-12F | Uhrzeit + PV-Leistung |
| Matrix3 | 8x MAX7219 (64x8) | 4x Rot + 4x Blau | Wemos D1 Mini | Uhrzeit + PV + Alerts |
| Matrix4 (Strompreis) | 4x MAX7219 (32x8) | Rot | Wemos D1 Mini | Tibber Strompreis + Trend |

## Verkabelung

### Wemos D1 Mini (Matrix3, Matrix4)

| MAX7219 Pin | Wemos D1 Mini Pin | GPIO |
|-------------|-------------------|------|
| CLK | D5 | GPIO14 |
| DIN (MOSI) | D7 | GPIO13 |
| CS | D3 | GPIO0 |
| VCC | 5V | - |
| GND | GND | - |

### ESP-12F (Matrix1, Matrix2) - andere Pinbelegung!

| MAX7219 Pin | ESP-12F Pin | GPIO |
|-------------|-------------|------|
| CLK | - | GPIO16 |
| DIN (MOSI) | - | GPIO4 |
| CS | - | GPIO5 |
| VCC | 5V | - |
| GND | GND | - |

> **Wichtig**: ESP-12F hat andere GPIO-Zuordnungen als Wemos D1 Mini!
> `Module` muss auf `0 (Generic)` stehen, da `Module 1 (Sonoff Basic)` GPIO-Overrides ignoriert.

## Architektur

```
Home Assistant ──► Node-RED ──► MQTT (Mosquitto) ──► Tasmota ESP8266 ──► MAX7219 Matrix
     │                │
     │  Sensoren:     │  Formatierung:
     │  - PV Leistung │  - Uhrzeit (HH:MM)
     │  - Tibber      │  - PV Watt/kWh
     │  - NINA/DWD    │  - Alert-Codes (4 Zeichen)
     │  - Divera THW  │
     │  - Netzwerk    │  MQTT Topics:
     │  - Petkit      │  cmnd/<name>/DisplayText
     │  - Meshtastic  │  cmnd/<name>/DisplayDimmer
     └────────────────┘
```

## Custom Firmware (Pflicht!)

Die Standard-Tasmota-Firmware (`tasmota-display.bin`) enthält **NICHT** den MAX7219 Dot-Matrix-Treiber!
Sie enthält nur `USE_DISPLAY_MAX7219` (7-Segment), nicht `USE_DISPLAY_MAX7219_MATRIX` (Dot-Matrix).

**Ohne Custom-Build leuchten alle LEDs permanent!**

→ [Custom Build Anleitung](docs/custom-build.md)

## Node-RED Flows

Jedes Display hat einen eigenen Node-RED Flow:

- **Matrix1**: PV-Anzeige Sonnenstand-basiert (Vortag → Leistung → Tagesertrag → Lebensleistung)
- **Matrix2**: Uhrzeit (Standard) / PV-Leistung (10s alle 60s)
- **Matrix3**: Links Uhr/PV (5 Zeichen) | Rechts Alerts (4 Zeichen, rotierend)
- **Matrix4**: Tibber Strompreis + Trend-Pfeil + Min/Max

→ [Node-RED Konfiguration](docs/nodered-config.md)

## Alert-System (Matrix3)

| Code | Priorität | Quelle | Beschreibung |
|------|-----------|--------|--------------|
| ALM! | 1 (Kritisch) | Divera | THW Alarm aktiv |
| NNET | 1 (Kritisch) | FritzBox | Internet offline |
| NINA | 2 (Hoch) | NINA | Katastrophenwarnung |
| UNWT | 2 (Hoch) | DWD | Unwetterwarnung |
| HCHW | 2 (Hoch) | Pegel Isar | Hochwasser (>600cm) |
| THW! | 2 (Hoch) | Divera | Rückmeldung fällig |
| NETZ | 2 (Hoch) | Netzwerk | Netzwerkproblem |
| KATZ | 3 (Mittel) | Petkit | Katzen-Feeder Problem |
| MESH | 3 (Mittel) | Meshtastic | Neue Mesh-Nachricht (<30min) |
| Bxx | 3 (Mittel) | Meshtastic | Mesh-Batterie niedrig (<20%) |
| WSCH | 3 (Mittel) | HA | Waschmaschine fertig |
| TRCK | 3 (Mittel) | HA | Trockner fertig |
| TEUR | 4 (Niedrig) | Tibber | Strom sehr teuer |
| BIL! | 4 (Niedrig) | Tibber | Strom sehr günstig |

## Dateien

```
IceMatrix/
├── README.md                          # Diese Datei
├── docs/
│   ├── custom-build.md                # Schritt-für-Schritt Build-Anleitung
│   └── nodered-config.md              # Node-RED Flow Dokumentation
├── firmware/
│   └── tasmota-display.bin            # Fertige Custom-Firmware (v14.4.1)
├── config/
│   ├── tasmota/
│   │   ├── user_config_override.h     # PlatformIO Build-Override
│   │   └── platformio_override.ini    # PlatformIO Environment-Config
│   ├── nodered/
│   │   └── matrix_flows.json          # Exportierte Node-RED Flows
│   └── homeassistant/
│       └── matrix3_notifications.yaml # HA Package für Alert-Toggles
└── images/                            # Dokumentations-Grafiken
```

## Lessons Learned

1. **Standard tasmota-display.bin hat KEINEN Matrix-Treiber** - Custom Build erforderlich
2. **OP_DISPLAYTEST muss explizit deaktiviert werden** - Sonst bleiben nach Power-Glitch alle LEDs an
3. **CS-Pin verifizieren** - Nicht blind der ESPHome-Config vertrauen, Pin am Board prüfen
4. **ESP8266 1MB Flash zu klein für OTA** - Muss per USB/Serial geflasht werden
5. **CH340 USB-Serial hat Protocol Error 71** - Workaround: USB unbind/rebind + Python serial pre-open
6. **ESP-12F hat andere GPIO-Pins als Wemos D1 Mini** - CLK=GPIO16, DIN=GPIO4, CS=GPIO5
7. **Module muss 0 (Generic) sein** bei ESP-12F - Module 1 (Sonoff Basic) ignoriert GPIO-Overrides
8. **Utility-Meter auf Tasmota ENERGY.Today ist unzuverlässig** - Besser direkt Tasmota-Sensoren nutzen (pv_energie_gestern, pv_energie_heute)
