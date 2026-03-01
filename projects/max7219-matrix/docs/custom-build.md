# Custom Tasmota Firmware Build für MAX7219 Dot-Matrix

## Warum Custom Build?

Die offizielle `tasmota-display.bin` enthält den Treiber `USE_DISPLAY_MAX7219` (7-Segment-Anzeige).
Für 8x8 Dot-Matrix-Module (z.B. 1088AS) wird aber `USE_DISPLAY_MAX7219_MATRIX` benötigt.

**Beide Treiber nutzen DisplayModel 19, sind aber nicht kompatibel!**

Der 7-Segment-Treiber sendet falsche SPI-Befehle an die Matrix-Module, was dazu führt,
dass alle LEDs permanent leuchten.

## Voraussetzungen

- Linux (getestet auf Debian/Ubuntu)
- Python 3.x
- Git
- ca. 1 GB Speicherplatz

## Schritt 1: PlatformIO installieren

```bash
pip3 install platformio
```

## Schritt 2: Tasmota Source Code klonen

```bash
cd /root
git clone --depth 1 https://github.com/arendst/Tasmota.git tasmota-build
cd tasmota-build
```

Für eine bestimmte Version (empfohlen):

```bash
git clone --depth 1 --branch v14.4.1 https://github.com/arendst/Tasmota.git tasmota-build
```

## Schritt 3: user_config_override.h erstellen

Erstelle die Datei `tasmota/user_config_override.h`:

```c
#ifndef _USER_CONFIG_OVERRIDE_H_
#define _USER_CONFIG_OVERRIDE_H_

// -- Force MAX7219 MATRIX driver (disables 7-segment and TM1637) --
#undef USE_DISPLAY_MAX7219
#undef USE_DISPLAY_TM1637
#define USE_DISPLAY_MAX7219_MATRIX

// -- UTF8 Latin1 charset support (Umlaute etc.) --
#define USE_UTF8_LATIN1

#endif  // _USER_CONFIG_OVERRIDE_H_
```

**Wichtig**: `USE_DISPLAY_MAX7219` muss explizit mit `#undef` entfernt werden,
da es in der Standard-Display-Konfiguration aktiviert ist und sich mit dem Matrix-Treiber gegenseitig ausschließt.

## Schritt 4: platformio_override.ini konfigurieren

Kopiere die Vorlage und aktiviere das `tasmota-display` Environment:

```bash
cp platformio_override_sample.ini platformio_override.ini
```

Bearbeite `platformio_override.ini`:

```ini
[platformio]
default_envs = tasmota-display

[env]
; Standard 1MB Flash Layout (ESP8266)
; Für Wemos D1 Mini mit 4MB Flash optional:
;board = esp8266_4M2M
```

## Schritt 5: LedMatrix Bug-Fix (OP_DISPLAYTEST)

**Kritischer Bug**: In der Datei `lib/lib_display/LedControl/src/LedMatrix.cpp` ist
der Befehl zum Deaktivieren des Display-Test-Modus auskommentiert (Zeile ~95):

```c
// VORHER (Bug):
//spiTransfer_value(OP_DISPLAYTEST, 0); // display test

// NACHHER (Fix):
spiTransfer_value(OP_DISPLAYTEST, 0); // disable display test mode
```

**Ohne diesen Fix:** Nach einem Power-Glitch oder Reset können MAX7219-Module im
Test-Modus starten (alle LEDs an) und werden nie wieder deaktiviert.

## Schritt 6: Firmware kompilieren

```bash
cd /root/tasmota-build
platformio run -e tasmota-display
```

Die fertige Firmware liegt in:
- `.pio/build/tasmota-display/firmware.bin` (~620 KB)
- `.pio/build/tasmota-display/firmware.bin.gz` (~435 KB, komprimiert)

Erwartete Build-Ausgabe:
```
RAM:   [=====     ]  50.9%
Flash: [======    ]  60.2%
========================= [SUCCESS] =========================
```

## Schritt 7: Firmware flashen

### Per USB-Serial (empfohlen)

**Wichtig**: OTA funktioniert NICHT bei ESP8266 mit 1MB Flash-Layout,
da die Firmware (~620KB) nicht in den OTA-Slot (~500KB) passt!

```bash
# ESP8266 per USB verbinden (CH340/CP2102 Adapter)

# Bei CH340 "Protocol Error 71" - USB Reset:
echo "1-2" > /sys/bus/usb/drivers/usb/unbind
sleep 3
echo "1-2" > /sys/bus/usb/drivers/usb/bind
sleep 3

# CH340 Workaround (RTS/DTR reset):
python3 -c "
import serial, time
ser = serial.Serial()
ser.port = '/dev/ttyUSB0'
ser.baudrate = 115200
ser.timeout = 1
ser.rts = False
ser.dtr = False
ser.open()
ser.setRTS(False)
ser.setDTR(False)
time.sleep(0.5)
ser.close()
"

# Flashen:
esptool.py --port /dev/ttyUSB0 --baud 115200 \
  write_flash --flash-size detect --flash-mode dout \
  0x0 .pio/build/tasmota-display/firmware.bin
```

Erwartete Ausgabe:
```
Connected to ESP8266 on /dev/ttyUSB0
Auto-detected flash size: 4MB
Writing at 0x00097980 [==============================] 100.0%
Wrote 620928 bytes in 39.6 seconds
Hash of data verified.
```

### Per Tasmota Web-UI (nur bei genug Flash)

Nur möglich wenn die Firmware kleiner als der OTA-Slot ist (~500KB bei 1MB Layout):

1. Browser öffnen: `http://<IP>/up`
2. Datei `firmware.bin.gz` hochladen
3. Warten bis Restart abgeschlossen

## Schritt 8: Tasmota konfigurieren

Nach dem Flashen über die Tasmota-Konsole oder HTTP:

```
# GPIO-Pins setzen
Backlog Gpio0 6976; Gpio13 6944; Gpio14 6912

# Display konfigurieren
Backlog DisplayModel 19; DisplayCols 8; DisplayWidth 64; DisplayHeight 8

# Netzwerk
Backlog SSId1 <SSID>; Password1 <WiFi-Passwort>
Backlog MqttHost <MQTT-IP>; MqttPort 1883; MqttUser <user>; MqttPassword <passwort>

# Geräte-Identität
Backlog Topic Matrix3; Hostname Matrix3; FriendlyName1 Matrix3

# Zeitzone (Europe/Berlin)
Timezone 99

# Display-Helligkeit (0-100)
DisplayDimmer 40

# Display-Rotation (2 = Standard für die meisten Module)
DisplayRotate 2

# Test
DisplayText Hallo!

# Neustart
Restart 1
```

### GPIO Component-IDs

| Funktion | Component-ID | Tasmota Name |
|----------|-------------|--------------|
| MAX7219 CLK | 6912 | MAX7219 CLK |
| MAX7219 DIN | 6944 | MAX7219 DIN |
| MAX7219 CS | 6976 | MAX7219 CS |

### Display-Parameter für verschiedene Konfigurationen

| Module | DisplayCols | DisplayWidth | DisplayHeight |
|--------|------------|-------------|--------------|
| 4x (1 Reihe) | 4 | 32 | 8 |
| 8x (1 Reihe) | 8 | 64 | 8 |
| 8x (2 Reihen) | 4 | 32 | 16 |

## Fehlerbehebung

### Alle LEDs dauerhaft an
1. **Falscher Treiber**: Standard-Firmware hat nur 7-Segment-Treiber → Custom Build nötig
2. **Display-Test-Modus**: LedMatrix.cpp Bug → OP_DISPLAYTEST Fix anwenden
3. **Falscher CS-Pin**: GPIO am Board physisch prüfen, nicht der Software vertrauen

### CH340 USB "Protocol Error 71"
```bash
# USB-Port unbind/rebind
echo "1-2" > /sys/bus/usb/drivers/usb/unbind
sleep 3
echo "1-2" > /sys/bus/usb/drivers/usb/bind
sleep 3
# Dann Python-Workaround vor esptool ausführen (siehe oben)
```

### OTA "Not enough space"
ESP8266 mit 1MB Flash-Layout hat nur ~500KB pro Partition.
Custom-Firmware ist ~620KB → nur per USB-Serial flashbar.

### DisplayText wird akzeptiert aber nichts passiert
- GPIOs prüfen: `Gpio all`
- DisplayModel prüfen: `DisplayModel` (muss 19 sein)
- CS-Pin systematisch durchprobieren (GPIO0, 2, 4, 5, 12, 15, 16)
