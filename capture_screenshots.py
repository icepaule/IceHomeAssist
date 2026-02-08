#!/usr/bin/env python3
"""
IceHomeAssist - Screenshot Automation
Erfasst Screenshots aller HA Dashboards und Settings-Seiten.
Redaktiert sensible Daten automatisch (IP, Benutzername, Tokens).

Verwendung:
    python3 capture_screenshots.py [--ha-url URL] [--username USER] [--password PASS]

Voraussetzungen:
    - Chromium/Chrome
    - selenium (pip install selenium)
    - Pillow (pip install Pillow)
"""

import argparse
import json
import os
import re
import time
import sys

import requests
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from PIL import Image, ImageFilter, ImageDraw

# =============================================================================
# Konfiguration
# =============================================================================

SCREENSHOT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "docs", "images")

# Seiten die erfasst werden sollen
PAGES = {
    # Dashboards
    "dashboard_home": "/lovelace-home/0",
    "dashboard_energie": "/lovelace-energie/0",
    "dashboard_wetter": "/lovelace-wetter/0",
    "dashboard_raeume": "/lovelace-raeume/0",
    "dashboard_medien": "/lovelace-medien/0",
    "dashboard_vacuum": "/lovelace-vacuum/0",
    "dashboard_system": "/lovelace-system/0",
    "dashboard_thw": "/lovelace-thw/0",
    "dashboard_network": "/lovelace-network/0",
    "dashboard_charly": "/lovelace-katze/0",
    "dashboard_kiosk": "/lovelace-kiosk/0",
    # Settings
    "settings_integrations": "/config/integrations",
    "settings_devices": "/config/devices/dashboard",
    "settings_automations": "/config/automation/dashboard",
    "settings_addons": "/hassio/dashboard",
    "settings_system": "/config/info",
}

# Sensible Muster die verwischt werden sollen
SENSITIVE_PATTERNS = [
    r'\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b',  # IP-Adressen
    r'[a-fA-F0-9]{2}:[a-fA-F0-9]{2}:[a-fA-F0-9]{2}:[a-fA-F0-9]{2}:[a-fA-F0-9]{2}:[a-fA-F0-9]{2}',  # MAC
    r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}',  # E-Mail
    r'Bearer\s+[a-zA-Z0-9_-]+',  # Bearer Tokens
    r'api[_-]?key["\s:=]+["\']?[a-zA-Z0-9_-]{10,}',  # API Keys
]

# =============================================================================
# Browser Setup
# =============================================================================

def create_driver():
    """Erstellt einen headless Chrome/Chromium Browser."""
    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--force-device-scale-factor=1")
    options.add_argument("--lang=de-DE")
    # Windy-Iframe blockieren (WebGL-Alert blockiert sonst das Rendering)
    options.add_argument("--host-resolver-rules=MAP embed.windy.com 127.0.0.1")

    # Chromium Pfade prüfen
    for path in ["/usr/bin/chromium", "/usr/bin/chromium-browser", "/usr/bin/google-chrome"]:
        if os.path.exists(path):
            options.binary_location = path
            break

    # ChromeDriver explizit angeben falls vorhanden
    service = None
    for driver_path in ["/usr/bin/chromedriver", "/usr/lib/chromium/chromedriver"]:
        if os.path.exists(driver_path):
            service = Service(executable_path=driver_path)
            break

    if service:
        driver = webdriver.Chrome(service=service, options=options)
    else:
        driver = webdriver.Chrome(options=options)
    driver.set_page_load_timeout(30)
    return driver


def login_ha(driver, base_url, username, password):
    """Login bei Home Assistant via REST API Auth Flow.

    HA nutzt Web Components mit tiefem Shadow DOM, was Selenium-basiertes
    Login unzuverlässig macht. Stattdessen wird die HA REST API verwendet:
    1. Login-Flow starten
    2. Credentials übermitteln
    3. Auth-Code gegen Token tauschen
    4. Token in Browser-localStorage injizieren
    """
    print("  Authentifizierung via HA REST API...")
    client_id = f"{base_url}/"

    try:
        # Schritt 1: Login-Flow starten
        resp = requests.post(
            f"{base_url}/auth/login_flow",
            json={"client_id": client_id, "handler": ["homeassistant", None], "redirect_uri": f"{base_url}/?auth_callback=1"},
        )
        resp.raise_for_status()
        flow = resp.json()
        flow_id = flow["flow_id"]

        # Schritt 2: Credentials senden
        resp = requests.post(
            f"{base_url}/auth/login_flow/{flow_id}",
            json={"client_id": client_id, "username": username, "password": password},
        )
        resp.raise_for_status()
        result = resp.json()

        if result.get("type") != "create_entry":
            print(f"  Login fehlgeschlagen: {result}")
            return False

        auth_code = result["result"]

        # Schritt 3: Auth-Code gegen Token tauschen
        resp = requests.post(
            f"{base_url}/auth/token",
            data={"grant_type": "authorization_code", "code": auth_code, "client_id": client_id},
        )
        resp.raise_for_status()
        tokens = resp.json()

        # Schritt 4: Token in Browser-localStorage setzen
        driver.get(base_url)
        time.sleep(2)

        hass_tokens = json.dumps({
            "hassUrl": base_url,
            "clientId": client_id,
            "access_token": tokens["access_token"],
            "refresh_token": tokens["refresh_token"],
            "token_type": "Bearer",
        })
        driver.execute_script(f"localStorage.setItem('hassTokens', '{hass_tokens}');")
        driver.get(base_url)
        time.sleep(3)

        print("  Login erfolgreich")
        return True

    except Exception as e:
        print(f"  Login fehlgeschlagen: {e}")
        return False


# =============================================================================
# Screenshot & Redaktion
# =============================================================================

def take_screenshot(driver, url, name, output_dir):
    """Nimmt einen Screenshot und speichert ihn."""
    print(f"  Erfasse: {name} ({url})")
    try:
        driver.get(url)
        time.sleep(4)  # Warte auf Dashboard-Rendering

        # Scrolle nach oben
        driver.execute_script("window.scrollTo(0, 0);")
        time.sleep(1)

        filepath = os.path.join(output_dir, f"{name}.png")
        driver.save_screenshot(filepath)
        return filepath
    except Exception as e:
        print(f"    FEHLER: {e}")
        return None


def redact_screenshot(filepath):
    """Verwischt sensible Bereiche im Screenshot."""
    if not filepath or not os.path.exists(filepath):
        return

    img = Image.open(filepath)
    width, height = img.size
    name = os.path.basename(filepath)

    # ---- Feste Bereiche verwischen ----

    # 1. Sidebar-Benutzername (unten links, ca. 256px breit, letzte 60px)
    sidebar_region = (0, height - 60, 256, height)
    _blur_region(img, sidebar_region)

    # 2. Home-Dashboard: Anwesenheit-Karte (Benutzername + Status)
    if "dashboard_home" in name:
        _blur_region(img, (690, 140, 1080, 170))

    img.save(filepath, optimize=True)


def _blur_region(img, region):
    """Verwischt eine Region im Bild mit starkem Gaussian Blur."""
    x1, y1, x2, y2 = region
    w, h = img.size
    # Begrenze auf Bildgrenzen
    x1, y1 = max(0, x1), max(0, y1)
    x2, y2 = min(w, x2), min(h, y2)
    if x2 <= x1 or y2 <= y1:
        return

    cropped = img.crop((x1, y1, x2, y2))
    blurred = cropped.filter(ImageFilter.GaussianBlur(radius=20))
    img.paste(blurred, (x1, y1))


# =============================================================================
# Main
# =============================================================================

def main():
    parser = argparse.ArgumentParser(description="IceHomeAssist Screenshot Automation")
    parser.add_argument("--ha-url", default="http://127.0.0.1:8123",
                        help="Home Assistant URL (default: http://127.0.0.1:8123)")
    parser.add_argument("--username", default="",
                        help="HA Benutzername")
    parser.add_argument("--password", default="",
                        help="HA Passwort")
    parser.add_argument("--skip-login", action="store_true",
                        help="Login überspringen (z.B. wenn trusted_networks konfiguriert)")
    parser.add_argument("--pages", nargs="*", default=None,
                        help="Nur bestimmte Seiten erfassen (z.B. dashboard_home dashboard_energie)")
    args = parser.parse_args()

    os.makedirs(SCREENSHOT_DIR, exist_ok=True)

    print("=" * 60)
    print(" IceHomeAssist - Screenshot Automation")
    print("=" * 60)
    print(f" Ziel: {SCREENSHOT_DIR}")
    print(f" HA URL: {args.ha_url}")
    print()

    driver = create_driver()

    try:
        # Login
        if not args.skip_login and args.username and args.password:
            if not login_ha(driver, args.ha_url, args.username, args.password):
                print("Login fehlgeschlagen. Beende.")
                return
        elif not args.skip_login:
            print("Kein Login konfiguriert. Versuche ohne Login...")
            driver.get(args.ha_url)
            time.sleep(3)

        # Screenshots erfassen
        pages = PAGES
        if args.pages:
            pages = {k: v for k, v in PAGES.items() if k in args.pages}

        captured = []
        failed = []

        for name, path in pages.items():
            url = f"{args.ha_url}{path}"
            filepath = take_screenshot(driver, url, name, SCREENSHOT_DIR)
            if filepath:
                redact_screenshot(filepath)
                captured.append(filepath)
            else:
                failed.append(name)

        # Zusammenfassung
        print()
        print("=" * 60)
        print(f" Erfolgreich: {len(captured)} Screenshots")
        if failed:
            print(f" Fehlgeschlagen: {len(failed)} ({', '.join(failed)})")
        print()
        print(" Bitte Screenshots vor dem Commit manuell prüfen:")
        for f in captured:
            print(f"   {f}")
        print("=" * 60)

    finally:
        driver.quit()


if __name__ == "__main__":
    main()
