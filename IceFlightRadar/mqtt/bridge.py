#!/usr/bin/env python3
"""IceFlightRadar MQTT-Bridge: liest readsb/tar1090 (aircraft.json, stats.json) und
meldet Werte per MQTT + Home-Assistant-Discovery. Laeuft nur, wenn MQTT_HOST gesetzt ist."""
import json, os, socket, sys, time, urllib.request
import paho.mqtt.client as mqtt

SRC = os.environ.get("SOURCE_URL", "http://127.0.0.1:8095").rstrip("/")
CONFIG_FILE = os.environ.get("CONFIG_FILE", "/config/iceflightradar.json")
DEV = os.environ.get("DEVICE_ID") or socket.gethostname().lower().replace(" ", "_")
BASE = f"iceflightradar/{DEV}"
NM_KM = 1.852

# key, Anzeigename, Einheit, device_class, state_class, Icon
SENSORS = [
    ("aircraft_total", "Flugzeuge", None, None, "measurement", "mdi:airplane"),
    ("aircraft_with_position", "Flugzeuge mit Position", None, None, "measurement", "mdi:map-marker"),
    ("messages_per_min", "Nachrichten pro Minute", "msg/min", None, "measurement", "mdi:message-text"),
    ("positions_per_min", "Positionen pro Minute", "pos/min", None, "measurement", "mdi:crosshairs-gps"),
    ("signal_dbfs", "Signalpegel", "dBFS", None, "measurement", "mdi:signal"),
    ("noise_dbfs", "Rauschpegel", "dBFS", None, "measurement", "mdi:waveform"),
    ("max_distance_km", "Maximale Distanz", "km", "distance", "measurement", "mdi:radar"),
    ("nearest_distance_km", "Naechstes Flugzeug", "km", "distance", "measurement", "mdi:airplane-marker"),
]


def get(path):
    with urllib.request.urlopen(SRC + path, timeout=8) as r:
        return json.load(r)


def collect():
    ac = get("/data/aircraft.json").get("aircraft", [])
    st = get("/data/stats.json")
    l1 = st.get("last1min", {})
    loc = l1.get("local", {})
    with_pos = [a for a in ac if "lat" in a]
    dist = [a for a in ac if "r_dst" in a]
    nearest = min(dist, key=lambda a: a["r_dst"]) if dist else None
    state = {
        "aircraft_total": len(ac),
        "aircraft_with_position": len(with_pos),
        "messages_per_min": l1.get("messages_valid"),
        "positions_per_min": l1.get("position_count_total"),
        "signal_dbfs": loc.get("signal"),
        "noise_dbfs": loc.get("noise"),
        "max_distance_km": round(max(a["r_dst"] for a in dist) * NM_KM, 1) if dist else None,
        "nearest_distance_km": round(nearest["r_dst"] * NM_KM, 1) if nearest else None,
    }
    attrs = {}
    if nearest:
        attrs = {
            "callsign": (nearest.get("flight") or "").strip() or None,
            "hex": nearest.get("hex"),
            "altitude_ft": nearest.get("alt_baro"),
            "speed_kt": nearest.get("gs"),
            "track": nearest.get("track"),
            "distance_km": round(nearest["r_dst"] * NM_KM, 1),
        }
    return state, attrs, bool(l1.get("messages_valid"))


def settings():
    """Konfigseite (JSON) hat Vorrang, Umgebungsvariablen sind der Standard fuer reine Docker-Nutzer."""
    env = {"enabled": bool(os.environ.get("MQTT_HOST")), "host": os.environ.get("MQTT_HOST", ""),
           "port": int(os.environ.get("MQTT_PORT", "1883")), "user": os.environ.get("MQTT_USER", ""),
           "password": os.environ.get("MQTT_PASSWORD", ""), "discovery_prefix": os.environ.get("HA_DISCOVERY_PREFIX", "homeassistant"),
           "device_name": os.environ.get("DEVICE_NAME", "IceFlightRadar")}
    interval = int(os.environ.get("INTERVAL", "10"))
    try:
        with open(CONFIG_FILE) as f:
            j = json.load(f)
        if isinstance(j.get("mqtt"), dict):  # Konfigseite vorhanden: sie gilt vollstaendig
            env.update(j["mqtt"])
        interval = int(j.get("poll_interval_s", interval))
    except (OSError, ValueError):
        pass
    return env, max(2, interval)


def publish_discovery(c, m):
    DISC, NAME = m["discovery_prefix"], m["device_name"]
    device = {"identifiers": [f"iceflightradar_{DEV}"], "name": NAME, "manufacturer": "IceFlightRadar",
              "model": "readsb/tar1090", "configuration_url": f"http://{DEV}.local/"}
    for key, name, unit, dclass, sclass, icon in SENSORS:
        cfg = {"name": name, "unique_id": f"iceflightradar_{DEV}_{key}", "state_topic": f"{BASE}/state",
               "value_template": "{{ value_json.%s }}" % key, "availability_topic": f"{BASE}/availability",
               "state_class": sclass, "icon": icon, "device": device}
        if unit: cfg["unit_of_measurement"] = unit
        if dclass: cfg["device_class"] = dclass
        if key == "nearest_distance_km":
            cfg["json_attributes_topic"] = f"{BASE}/nearest"
        c.publish(f"{DISC}/sensor/iceflightradar_{DEV}/{key}/config", json.dumps(cfg), retain=True)
    c.publish(f"{DISC}/binary_sensor/iceflightradar_{DEV}/receiving/config", json.dumps({
        "name": "Empfang aktiv", "unique_id": f"iceflightradar_{DEV}_receiving", "state_topic": f"{BASE}/receiving",
        "payload_on": "ON", "payload_off": "OFF", "device_class": "connectivity",
        "availability_topic": f"{BASE}/availability", "device": device}), retain=True)


def new_client(m):
    c = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=f"iceflightradar-{DEV}")
    if m["user"]:
        c.username_pw_set(m["user"], m["password"] or None)
    c.will_set(f"{BASE}/availability", "offline", retain=True)
    c.on_connect = lambda cl, u, f, rc, p=None: (print("MQTT verbunden" if not getattr(rc, "is_failure", rc) else f"MQTT-Fehler: {rc}", flush=True),
                                                  publish_discovery(cl, m), cl.publish(f"{BASE}/availability", "online", retain=True))
    c.connect_async(m["host"], int(m["port"]), keepalive=60)
    c.loop_start()
    return c


def main():
    client, active = None, None
    while True:
        m, interval = settings()
        if not m["enabled"] or not m["host"]:
            if client:
                client.publish(f"{BASE}/availability", "offline", retain=True)
                client.loop_stop(); client.disconnect(); client = None
                print("MQTT deaktiviert", flush=True)
            active = None
            time.sleep(5)
            continue
        if client is None or m != active:
            if client:
                client.loop_stop(); client.disconnect()
            print(f"MQTT-Bridge {DEV}: {SRC} -> {m['host']}:{m['port']}", flush=True)
            client, active = new_client(m), dict(m)
        try:
            state, attrs, receiving = collect()
            client.publish(f"{BASE}/state", json.dumps(state))
            client.publish(f"{BASE}/nearest", json.dumps(attrs))
            client.publish(f"{BASE}/receiving", "ON" if receiving else "OFF")
        except Exception as e:  # Quelle kurz weg (z.B. Container-Neustart): weiter versuchen
            print("Quelle nicht erreichbar:", e, file=sys.stderr, flush=True)
        time.sleep(interval)


if __name__ == "__main__":
    main()
