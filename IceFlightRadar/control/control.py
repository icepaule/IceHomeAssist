#!/usr/bin/env python3
"""IceFlightRadar Steuerdienst (nur Python-Standardbibliothek).

- /config/  Konfigseite (Passwortschutz): MQTT, Intervalle, ADSBExchange
- /setup/   WLAN-Einrichtung (im AP-Modus ohne Login, sonst mit Login)
- /public.json  nicht geheime Werte fuer die Startseite
Lauscht nur auf 127.0.0.1, der Webserver (nginx) reicht die Anfragen durch."""
import base64, hashlib, hmac, html, json, os, re, secrets, subprocess, threading, time, uuid as uuidlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

APPDIR = os.environ.get("ICEFLIGHT_DIR", "/opt/iceflightradar")
CONF = os.environ.get("ICEFLIGHT_CONFIG", f"{APPDIR}/config/iceflightradar.json")
ENVFILE = f"{APPDIR}/.env"
AP_MARKER = "/run/iceflightradar-ap-active"
BIND = ("127.0.0.1", int(os.environ.get("ICEFLIGHT_PORT", "8099")))
CONTAINER = os.environ.get("ULTRAFEEDER_CONTAINER", "iceflightradar-ultrafeeder")
LOCK = threading.Lock()

DEFAULT = {"poll_interval_s": 10, "ui_refresh_s": 5, "admin": {},
           "mqtt": {"enabled": False, "host": "", "port": 1883, "user": "", "password": "",
                    "discovery_prefix": "homeassistant", "device_name": "IceFlightRadar"},
           "adsbx": {"enabled": False, "uuid": "", "feed_id": ""}}


def load():
    try:
        with open(CONF) as f:
            d = json.load(f)
    except (OSError, ValueError):
        d = {}
    out = json.loads(json.dumps(DEFAULT))
    for k, v in d.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k].update(v)
        else:
            out[k] = v
    return out


def save(cfg):
    os.makedirs(os.path.dirname(CONF), exist_ok=True)
    tmp = CONF + ".tmp"
    with open(tmp, "w") as f:
        json.dump(cfg, f, indent=2)
    os.chmod(tmp, 0o600)
    os.replace(tmp, CONF)


def hash_pw(pw, salt=None):
    salt = salt or secrets.token_hex(16)
    h = hashlib.pbkdf2_hmac("sha256", pw.encode(), salt.encode(), 200_000).hex()
    return {"salt": salt, "hash": h}


def check_pw(cfg, pw):
    a = cfg.get("admin") or {}
    if not a.get("hash"):
        return False
    return hmac.compare_digest(hash_pw(pw, a["salt"])["hash"], a["hash"])


def run(cmd, timeout=60):
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return r.returncode, (r.stdout + r.stderr).strip()
    except Exception as e:
        return 1, str(e)


# ---------- .env fuer den Ultrafeeder (ADSBExchange) ----------
def read_env():
    d = {}
    try:
        for line in open(ENVFILE):
            if "=" in line and not line.lstrip().startswith("#"):
                k, v = line.rstrip("\n").split("=", 1)
                d[k] = v
    except OSError:
        pass
    return d


def write_env(updates):
    d = read_env()
    d.update(updates)
    tmp = ENVFILE + ".tmp"
    with open(tmp, "w") as f:
        for k, v in d.items():
            f.write(f"{k}={v}\n")
    os.chmod(tmp, 0o600)
    os.replace(tmp, ENVFILE)


def adsbx_env(adsbx):
    if adsbx.get("enabled") and adsbx.get("uuid"):
        u = adsbx["uuid"]
        return {"ADSBX_UUID": u,
                "ULTRAFEEDER_CONFIG": f"adsb,feed.adsbexchange.com,30004,beast_reduce_plus_out,uuid={u};mlat,feed.adsbexchange.com,31090,uuid={u}"}
    return {"ADSBX_UUID": "", "ULTRAFEEDER_CONFIG": ""}


def apply_adsbx(cfg):
    """schreibt .env und startet den Ultrafeeder nur bei Aenderung neu (kurze Unterbrechung)."""
    new = adsbx_env(cfg["adsbx"])
    old = {k: read_env().get(k, "") for k in new}
    if old == new:
        return False
    write_env(new)
    threading.Thread(target=lambda: run(["docker", "compose", "--project-directory", APPDIR, "up", "-d", "ultrafeeder"], 300), daemon=True).start()
    return True


def detect_feed_id():
    rc, out = run(["docker", "logs", CONTAINER], 20)
    m = re.findall(r"Stats URL is https://www\.adsbexchange\.com/api/feeders/\?feed=([A-Za-z0-9_-]+)", out)
    return m[-1] if m else ""


def feed_status():
    rc, out = run(["docker", "logs", "--since", "10m", CONTAINER], 20)
    lines = [l for l in out.splitlines() if re.search(r"adsbexchange|mlat-client", l, re.I)]
    return "\n".join(lines[-6:]) or "(keine Feed-Meldungen in den letzten 10 Minuten)"


# ---------- HTML ----------
CSS = """<style>body{font:15px/1.5 system-ui,sans-serif;background:#14171c;color:#e6e9ee;margin:0}
main{max-width:720px;margin:0 auto;padding:16px}h1{font-size:20px}h2{font-size:16px;margin-top:26px;border-bottom:1px solid #2c323b;padding-bottom:4px}
label{display:block;margin:10px 0 2px;color:#aab2bd}input,select{width:100%;padding:8px;border-radius:6px;border:1px solid #2c323b;background:#1d2127;color:#e6e9ee;font:inherit}
input[type=checkbox]{width:auto;margin-right:8px}.row{display:flex;gap:12px}.row>div{flex:1}
button{margin-top:18px;padding:10px 18px;border:0;border-radius:6px;background:#4aa8ff;color:#001;font:inherit;font-weight:600;cursor:pointer}
.msg{padding:10px;border-radius:6px;background:#1f3a24;margin:12px 0}.err{background:#4a2020}pre{background:#1d2127;padding:10px;border-radius:6px;overflow:auto;font-size:12px}
a{color:#4aa8ff}small{color:#8b95a3}</style>"""


def page(title, body):
    return f"<!doctype html><html lang=de><meta charset=utf-8><meta name=viewport content='width=device-width,initial-scale=1'><title>{html.escape(title)}</title>{CSS}<main><p><a href='/'>&larr; Startseite</a></p>{body}</main></html>"


def e(v):
    return html.escape(str(v), quote=True)


def config_page(cfg, msg="", err=False):
    m, a = cfg["mqtt"], cfg["adsbx"]
    chk = lambda b: "checked" if b else ""
    note = f"<div class='msg{' err' if err else ''}'>{e(msg)}</div>" if msg else ""
    return page("Konfiguration", f"""<h1>IceFlightRadar Konfiguration</h1>{note}
<form method=post action=/config/>
<h2>Intervalle</h2><div class=row>
<div><label>MQTT-Abfrageintervall (Sekunden)</label><input name=poll_interval_s type=number min=2 max=3600 value='{e(cfg["poll_interval_s"])}'></div>
<div><label>Aktualisierung der Startseite (Sekunden)</label><input name=ui_refresh_s type=number min=2 max=60 value='{e(cfg["ui_refresh_s"])}'></div></div>
<h2>MQTT / Home Assistant</h2>
<label><input type=checkbox name=mqtt_enabled {chk(m["enabled"])}>MQTT-Anbindung aktivieren</label>
<div class=row><div><label>Broker (Host/IP)</label><input name=mqtt_host value='{e(m["host"])}'></div>
<div><label>Port</label><input name=mqtt_port type=number min=1 max=65535 value='{e(m["port"])}'></div></div>
<div class=row><div><label>Benutzer</label><input name=mqtt_user value='{e(m["user"])}' autocomplete=off></div>
<div><label>Passwort <small>(leer = unveraendert)</small></label><input name=mqtt_password type=password autocomplete=new-password></div></div>
<div class=row><div><label>Discovery-Prefix</label><input name=mqtt_prefix value='{e(m["discovery_prefix"])}'></div>
<div><label>Geraetename</label><input name=mqtt_name value='{e(m["device_name"])}'></div></div>
<h2>ADS-B Exchange</h2>
<label><input type=checkbox name=adsbx_enabled {chk(a["enabled"])}>Feed an ADSBExchange aktivieren</label>
<label>Stations-UUID <small>(leer = beim Speichern neu erzeugen; danach nicht mehr aendern)</small></label><input name=adsbx_uuid value='{e(a["uuid"])}'>
<label>Feeder-ID fuer die Statistik-Seite <small>(leer = automatisch aus den Logs)</small></label><input name=adsbx_feed_id value='{e(a["feed_id"])}'>
<p><small>Aenderungen an dieser Einstellung starten den Empfaenger-Container kurz neu (ca. 20 Sekunden ohne Empfang).</small></p>
<h2>Feed-Status</h2><pre>{e(feed_status()) if a["enabled"] else "ADSBExchange ist deaktiviert."}</pre>
<h2>Admin-Passwort</h2><label>Neues Passwort <small>(leer = unveraendert)</small></label><input name=admin_password type=password autocomplete=new-password>
<button>Speichern und anwenden</button></form>
<p><a href='/setup/'>WLAN einrichten</a></p>""")


def setup_page(msg="", err=False):
    rc, out = run(["nmcli", "-t", "-f", "SSID,SIGNAL,SECURITY", "dev", "wifi", "list", "--rescan", "auto"], 30)
    nets, seen = [], set()
    for line in out.splitlines():
        p = re.split(r"(?<!\\):", line)
        if len(p) >= 3 and p[0] and p[0].replace("\\:", ":") not in seen:
            s = p[0].replace("\\:", ":"); seen.add(s); nets.append((s, p[1], p[2]))
    opts = "".join(f"<option value='{e(s)}'>{e(s)} ({e(sig)}%{' , ' + e(sec) if sec else ''})</option>" for s, sig, sec in nets)
    _, cur = run(["nmcli", "-t", "-f", "GENERAL.STATE,GENERAL.CONNECTION", "dev", "show", "wlan0"], 10)
    note = f"<div class='msg{' err' if err else ''}'>{e(msg)}</div>" if msg else ""
    ap = os.path.exists(AP_MARKER)
    hint = "Der Access Point ist aktiv: Nach dem Speichern verbindet sich das Geraet mit dem gewaehlten WLAN und dieser Zugang verschwindet. Bei falschem Passwort startet er nach etwa einer Minute wieder." if ap else "Achtung: Ein WLAN-Wechsel kann die Verbindung zu diesem Geraet trennen."
    return page("WLAN einrichten", f"""<h1>WLAN einrichten</h1>{note}<p><small>{e(hint)}</small></p>
<form method=post action=/setup/><label>Netzwerk</label><select name=ssid_sel><option value=''>-- waehlen --</option>{opts}</select>
<label>oder SSID manuell</label><input name=ssid_manual>
<label>Passwort</label><input name=password type=password autocomplete=new-password>
<button>Verbinden</button></form><h2>Aktuell</h2><pre>{e(cur)}</pre>""")


def connect_wifi(ssid, pw):
    time.sleep(2)  # Antwort zuerst ausliefern
    run(["nmcli", "con", "delete", "iceflightradar-wifi"], 15)
    cmd = ["nmcli", "dev", "wifi", "connect", ssid, "ifname", "wlan0", "name", "iceflightradar-wifi"]
    if pw:
        cmd += ["password", pw]
    rc, _ = run(cmd, 90)
    if rc == 0:
        run(["nmcli", "con", "modify", "iceflightradar-wifi", "connection.autoconnect", "yes", "connection.autoconnect-priority", "50"], 15)


class H(BaseHTTPRequestHandler):
    server_version = "IceFlightRadar"

    def log_message(self, *a):
        pass

    def send(self, code, body, ctype="text/html; charset=utf-8", extra=None):
        b = body.encode() if isinstance(body, str) else body
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(b)))
        self.send_header("Cache-Control", "no-store")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(b)

    def auth(self, cfg, allow_ap=False):
        if allow_ap and os.path.exists(AP_MARKER):
            return True
        if not (cfg.get("admin") or {}).get("hash"):
            return True  # noch kein Passwort: Ersteinrichtung (wird auf der Konfigseite erzwungen)
        h = self.headers.get("Authorization", "")
        if h.startswith("Basic "):
            try:
                _, _, pw = base64.b64decode(h[6:]).decode().partition(":")
                if check_pw(cfg, pw):
                    return True
            except Exception:
                pass
        self.send(401, page("Anmeldung", "<h1>Anmeldung erforderlich</h1>"), extra={"WWW-Authenticate": 'Basic realm="IceFlightRadar"'})
        return False

    def same_origin(self):
        o = self.headers.get("Origin") or self.headers.get("Referer") or ""
        host = self.headers.get("Host", "")
        return (not o) or urlparse(o).netloc == host

    def do_GET(self):
        path = urlparse(self.path).path.rstrip("/") or "/"
        cfg = load()
        if path == "/public.json":
            fid = cfg["adsbx"].get("feed_id") if cfg["adsbx"].get("enabled") else ""
            return self.send(200, json.dumps({"ui_refresh_s": cfg["ui_refresh_s"], "adsbx_feed_id": fid}), "application/json")
        if path == "/config":
            if not self.auth(cfg):
                return
            if not (cfg.get("admin") or {}).get("hash"):
                return self.send(200, page("Ersteinrichtung", "<h1>Admin-Passwort festlegen</h1><p>Bevor du etwas einstellen kannst, lege ein Passwort fest.</p><form method=post action=/config/><label>Passwort (min. 8 Zeichen)</label><input name=admin_password type=password minlength=8 required><button>Festlegen</button></form>"))
            return self.send(200, config_page(cfg))
        if path == "/setup":
            if not self.auth(cfg, allow_ap=True):
                return
            return self.send(200, setup_page())
        self.send(404, page("Nicht gefunden", "<h1>404</h1>"))

    def do_POST(self):
        path = urlparse(self.path).path.rstrip("/")
        cfg = load()
        if not self.same_origin():
            return self.send(403, page("Verboten", "<h1>403</h1>"))
        n = int(self.headers.get("Content-Length") or 0)
        f = {k: v[0] for k, v in parse_qs(self.rfile.read(min(n, 65536)).decode(), keep_blank_values=True).items()}
        with LOCK:
            if path == "/config":
                if not self.auth(cfg):
                    return
                first = not (cfg.get("admin") or {}).get("hash")
                if first:
                    pw = f.get("admin_password", "")
                    if len(pw) < 8:
                        return self.send(200, page("Ersteinrichtung", "<h1>Passwort zu kurz (min. 8 Zeichen)</h1><p><a href='/config/'>zurueck</a></p>"))
                    cfg["admin"] = hash_pw(pw)
                    save(cfg)
                    return self.send(200, page("Gespeichert", "<h1>Passwort gesetzt</h1><p><a href='/config/'>Weiter zur Konfiguration</a> (du wirst nach dem Passwort gefragt, Benutzername beliebig).</p>"))
                try:
                    cfg["poll_interval_s"] = max(2, min(3600, int(f.get("poll_interval_s", 10))))
                    cfg["ui_refresh_s"] = max(2, min(60, int(f.get("ui_refresh_s", 5))))
                    m = cfg["mqtt"]
                    m["enabled"] = "mqtt_enabled" in f
                    m["host"] = f.get("mqtt_host", "").strip()
                    m["port"] = max(1, min(65535, int(f.get("mqtt_port", 1883))))
                    m["user"] = f.get("mqtt_user", "").strip()
                    if f.get("mqtt_password"):
                        m["password"] = f["mqtt_password"]
                    m["discovery_prefix"] = f.get("mqtt_prefix", "homeassistant").strip() or "homeassistant"
                    m["device_name"] = f.get("mqtt_name", "IceFlightRadar").strip() or "IceFlightRadar"
                    if m["enabled"] and not m["host"]:
                        raise ValueError("MQTT aktiviert, aber kein Broker angegeben")
                    a = cfg["adsbx"]
                    a["enabled"] = "adsbx_enabled" in f
                    a["uuid"] = f.get("adsbx_uuid", "").strip()
                    if a["enabled"] and not a["uuid"]:
                        a["uuid"] = str(uuidlib.uuid4())
                    if a["uuid"] and not re.fullmatch(r"[0-9a-fA-F-]{8,64}", a["uuid"]):
                        raise ValueError("UUID hat ein ungueltiges Format")
                    a["feed_id"] = f.get("adsbx_feed_id", "").strip()
                    if a["enabled"] and not a["feed_id"]:
                        a["feed_id"] = detect_feed_id()
                    if f.get("admin_password"):
                        if len(f["admin_password"]) < 8:
                            raise ValueError("Neues Passwort zu kurz (min. 8 Zeichen)")
                        cfg["admin"] = hash_pw(f["admin_password"])
                except ValueError as ex:
                    return self.send(200, config_page(load(), f"Nicht gespeichert: {ex}", True))
                save(cfg)
                restarted = apply_adsbx(cfg)
                msg = "Gespeichert." + (" Empfaenger wird neu gestartet (ca. 20 s)." if restarted else "")
                return self.send(200, config_page(cfg, msg))
            if path == "/setup":
                if not self.auth(cfg, allow_ap=True):
                    return
                ssid = f.get("ssid_manual", "").strip() or f.get("ssid_sel", "").strip()
                if not ssid:
                    return self.send(200, setup_page("Bitte ein Netzwerk waehlen.", True))
                threading.Thread(target=connect_wifi, args=(ssid, f.get("password", "")), daemon=True).start()
                return self.send(200, setup_page(f"Verbinde mit '{ssid}' ... Dieses Fenster kann sich trennen. Danach das Geraet unter seiner neuen Adresse aufrufen."))
        self.send(404, page("Nicht gefunden", "<h1>404</h1>"))


if __name__ == "__main__":
    ThreadingHTTPServer(BIND, H).serve_forever()
