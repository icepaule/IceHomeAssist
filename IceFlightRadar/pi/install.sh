#!/bin/bash
# Installiert die optionalen Pi-Dienste (Steuerdienst mit Konfigseite, WLAN-Fallback) auf Raspberry Pi OS / Debian.
# Voraussetzung: dieses Repo liegt unter /opt/iceflightradar, Docker ist installiert, NetworkManager ist aktiv.
set -euo pipefail
D=/opt/iceflightradar
[ "$(id -u)" = 0 ] || { echo "bitte mit sudo starten"; exit 1; }
apt-get install -y --no-install-recommends iw network-manager >/dev/null
mkdir -p $D/config /etc/NetworkManager/dnsmasq-shared.d
install -m 0644 $D/pi/nm/iceflightradar-captive.conf /etc/NetworkManager/dnsmasq-shared.d/
install -m 0644 $D/pi/systemd/iceflightradar-control.service /etc/systemd/system/
install -m 0644 $D/pi/systemd/iceflightradar-wifi-fallback.service /etc/systemd/system/
chmod +x $D/pi/iceflightradar-wifi-fallback.sh
systemctl daemon-reload
systemctl enable --now iceflightradar-control.service
[ "${1:-}" = "--no-ap" ] || systemctl enable --now iceflightradar-wifi-fallback.service
echo "fertig. Konfigseite: http://$(hostname).local/config/ (beim ersten Aufruf Passwort festlegen)"
