#!/bin/bash
# IceFlightRadar: WLAN-Fallback. Findet das Geraet nach GRACE Sekunden kein WLAN (und kein LAN-Kabel),
# oeffnet es einen Access Point "IceFlightRadar-Setup" mit Einrichtungsseite (http://192.168.4.1/).
# Ohne verbundene Handys/Laptops wird alle RETRY Sekunden erneut versucht, sich mit einem bekannten WLAN zu verbinden.
# Einstellungen optional in /boot/firmware/iceflightradar.conf:  AP_SSID=...  AP_PSK=... (min. 8 Zeichen)  GRACE=120  RETRY=300
CONF=/boot/firmware/iceflightradar.conf
[ -f "$CONF" ] && . "$CONF"
AP_SSID="${AP_SSID:-IceFlightRadar-Setup}"; AP_PSK="${AP_PSK:-iceflightradar}"; GRACE="${GRACE:-120}"; RETRY="${RETRY:-300}"
[ "${#AP_PSK}" -ge 8 ] || AP_PSK="iceflightradar"
IF=wlan0; AP=iceflightradar-ap; MARK=/run/iceflightradar-ap-active
LOGF=/var/log/iceflightradar-wifi.log
log() { echo "$(date -Is) wifi-fallback: $*" | tee -a "$LOGF"; }

wifi_connected() { nmcli -t -f DEVICE,STATE,CONNECTION dev | grep "^$IF:connected:" | grep -qv ":$AP$"; }
eth_connected()  { nmcli -t -f DEVICE,STATE dev | grep -q "^eth0:connected"; }
ap_up()          { nmcli -t -f NAME con show --active | grep -qx "$AP"; }
stations()       { iw dev "$IF" station dump 2>/dev/null | grep -c '^Station'; }

start_ap() {
  log "starte Access Point '$AP_SSID'"
  nmcli con delete "$AP" >/dev/null 2>&1
  nmcli con add type wifi ifname "$IF" con-name "$AP" autoconnect no ssid "$AP_SSID" mode ap \
    802-11-wireless.band bg 802-11-wireless.channel 6 ipv4.method shared ipv4.addresses 192.168.4.1/24 ipv6.method ignore \
    wifi-sec.key-mgmt wpa-psk wifi-sec.psk "$AP_PSK" >/dev/null && nmcli con up "$AP" >/dev/null 2>&1 \
    && touch "$MARK" && log "AP aktiv" || log "AP-Start fehlgeschlagen"
  ap_since=$SECONDS
}
stop_ap() { nmcli con down "$AP" >/dev/null 2>&1; rm -f "$MARK"; }
# bekannte WLAN-Profile der Reihe nach probieren; vorher Funkmodul zuruecksetzen (Treiber haengt sonst im AP-Modus)
connect_known() {
  nmcli radio wifi off; sleep 2; nmcli radio wifi on; sleep 4
  for c in $(nmcli -t -f NAME,TYPE con show | awk -F: '$2=="802-11-wireless" && $1!="'"$AP"'"{print $1}'); do
    nmcli -w 25 con up id "$c" >/dev/null 2>&1 && { log "verbunden mit Profil '$c'"; return 0; }
  done
  nmcli dev connect "$IF" >/dev/null 2>&1; return 1
}

if [ "$1" = "--test-ap" ]; then   # kontrollierter Test: AP fuer N Sekunden, danach zurueck ins bekannte WLAN
  start_ap; sleep "${2:-120}"; stop_ap; connect_known; sleep 10
  if wifi_connected; then log "Test beendet, WLAN wieder verbunden"; exit 0; fi
  log "Test: WLAN nicht zurueck -> Neustart als Sicherung"; systemctl reboot
fi

down=0; ap_since=0; rm -f "$MARK"
while sleep 10; do
  if [ -f "$MARK" ]; then
    if wifi_connected; then log "WLAN verbunden, beende AP"; stop_ap; down=0; continue; fi
    if ! ap_up; then start_ap; continue; fi                      # Verbindungsversuch fehlgeschlagen -> AP wieder hoch
    if [ "$(stations)" -gt 0 ]; then ap_since=$SECONDS; continue; fi
    if (( SECONDS - ap_since > RETRY )); then
      log "keine Clients am AP, versuche bekanntes WLAN"
      stop_ap; connect_known; sleep 10
      wifi_connected || start_ap
    fi
  else
    if wifi_connected || eth_connected; then down=0; else down=$((down + 10)); fi
    (( down >= GRACE )) && { start_ap; down=0; }
  fi
done
