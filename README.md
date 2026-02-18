# IceHomeAssist

Home Assistant Konfiguration & Dokumentation auf einem Intel NUC.

## Quick Start - Disaster Recovery

Komplettes Setup auf einem frischen System wiederherstellen:

```bash
curl -sSL https://raw.githubusercontent.com/icepaule/IceHomeAssist/main/restore.sh | sudo bash
```

## Dokumentation

Die vollständige HTML-Dokumentation (deutsch) ist unter GitHub Pages verfügbar:

**[https://icepaule.github.io/IceHomeAssist/docs/](https://icepaule.github.io/IceHomeAssist/docs/)**

## System-Übersicht

| Komponente | Details |
|---|---|
| **Hardware** | Intel NUC |
| **OS** | Debian mit Docker |
| **HA Image** | `ghcr.io/home-assistant/qemux86-64-homeassistant` |
| **Config-Pfad** | `/var/lib/homeassistant/homeassistant/` (Host) = `/config` (Container) |
| **Dashboards** | 11 YAML-Dashboards |
| **Packages** | 12 Konfigurations-Pakete |
| **Automationen** | 4 YAML-Automationen + Node-RED Flows (10 Tabs, 188 Nodes) |
| **Integrationen** | 40+ (davon 12 HACS Custom Components) |

## Integrationen

### HACS Custom Components

| Integration | Version | Beschreibung |
|---|---|---|
| Alexa Media Player | 5.11.0 | Amazon Echo Steuerung |
| Divera Control | 1.3.1 | THW/Feuerwehr Alarmierung |
| Dreame Vacuum | 1.0.8 | Staubsauger Roboter |
| DWD | 2025.12.1 | Wetterwarnungen |
| DWD Precipitation | 2025.7.0b1 | Niederschlagsradar |
| DWD Precipitation Forecast | 0.2.0 | Niederschlagsprognose |
| FritzBox VPN | 0.7.0 | VPN Status |
| HACS | 2.0.5 | Community Store |
| Meross Cloud | 1.3.12 | Smart Plugs (Cloud) |
| Meross LAN | 5.8.0 | Smart Plugs (Lokal) |
| PetKit | 0.1.14 | Haustier Zubehör |
| Xiaomi Cloud Map Extractor | 2.2.5 | Staubsauger Karte |

### Native Integrationen (Auswahl)

MQTT (Mosquitto), Tibber, Sony Bravia, Fritz!Box, Tractive, Matter, und weitere.

## Verzeichnisstruktur

```
IceHomeAssist/
├── configuration.yaml          # Hauptkonfiguration
├── secrets.yaml.example        # Secrets Template (ausfüllen!)
├── scripts.yaml                # HA Scripts
├── groups.yaml                 # Gruppen
├── scenes.yaml                 # Szenen (sanitisiert)
├── utility_meters.yaml         # Zähler
├── custom_components.txt       # HACS Komponenten-Liste
├── restore.sh                  # Disaster Recovery Script
├── capture_screenshots.py      # Screenshot Automation
├── .gitignore
├── packages/                   # Konfigurations-Pakete
│   ├── energy.yaml
│   ├── wifi_buttons.yaml
│   ├── network_switches.yaml
│   ├── notifications.yaml
│   ├── matrix3_notifications.yaml
│   ├── thw_divera.yaml
│   ├── thw_nina.yaml
│   ├── wetter.yaml
│   ├── internet.yaml
│   ├── android_tv_bravia.yaml
│   ├── bring_einkaufsliste.yaml
│   └── unifi.yaml
├── dashboards/                 # 11 YAML Dashboards
├── automations/                # Automatisierungen
├── templates/                  # Template Sensoren
├── scripts/                    # Python Scripts
│   ├── unifi_radar_data.py     # UniFi Radar SVG (sanitisiert)
│   └── snmp_switch_ports.py    # SNMP Switch Monitoring
├── nodered/                    # Node-RED
│   └── flows.json
├── projects/                   # Hardware-Projekte (Bauanleitungen)
│   └── max7219-matrix/         # MAX7219 LED-Matrix Uhr & PV-Anzeige
└── docs/                       # HTML Dokumentation
    ├── index.html
    ├── css/style.css
    ├── images/
    └── 01-16 HTML Seiten
```

## Hardware-Projekte

| Projekt | Beschreibung |
|---|---|
| [MAX7219 LED-Matrix](projects/max7219-matrix/) | 3x ESP8266 + MAX7219 (32x8 & 64x8) als Uhr, PV-Anzeige & HA-Benachrichtigungen (Tasmota + Node-RED) |
| Tibber Strompreis-Ampel | 2x ESP8266 (Tasmota) mit je 3 LEDs (Rot/Gelb/Gruen) - zeigt Tibber Preisstatus, blinkt bei guenstigster Periode, Rot bei Peak-Preisen |

## Sicherheit

- **Keine echten Secrets** in diesem Repository
- `secrets.yaml` wird **nie** committed (`.gitignore`)
- `secrets.yaml.example` enthält nur Platzhalter (`YOUR_*`)
- Seriennummern, Tokens und Credentials sind sanitisiert
- Pre-Commit Hook scannt nach versehentlich eingecheckten Secrets
- Lokale IPs (192.168.x.x) in Netzwerk-Dokumentation sind private, nicht-routbare Adressen

## Nach dem Klonen

1. `secrets.yaml.example` → `secrets.yaml` kopieren
2. Alle `YOUR_*` Platzhalter mit echten Werten ersetzen
3. `scripts/unifi_radar_data.py` Credentials eintragen
4. Home Assistant Container starten

Detaillierte Anleitung: [Wiederherstellung](docs/15-wiederherstellung.html)

---

Erstellt Februar 2026
