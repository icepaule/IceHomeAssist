#!/bin/bash
# =============================================================================
# IceHomeAssist - Disaster Recovery Script
# =============================================================================
# Stellt das komplette Home Assistant Setup auf einem frischen System wieder her.
#
# Verwendung:
#   curl -sSL https://raw.githubusercontent.com/icepaule/IceHomeAssist/main/restore.sh | sudo bash
#
# Oder lokal:
#   sudo bash restore.sh
# =============================================================================

set -euo pipefail

# Farben
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

REPO_URL="https://github.com/icepaule/IceHomeAssist.git"
HA_CONFIG="/var/lib/homeassistant/homeassistant"
HA_ADDON_CONFIGS="/var/lib/homeassistant/addon_configs"
CONTAINER_NAME="homeassistant"
HA_IMAGE="ghcr.io/home-assistant/qemux86-64-homeassistant"
CLONE_DIR="/tmp/IceHomeAssist_restore"

# =============================================================================
# Hilfsfunktionen
# =============================================================================

log_info()  { echo -e "${BLUE}[INFO]${NC}  $1"; }
log_ok()    { echo -e "${GREEN}[OK]${NC}    $1"; }
log_warn()  { echo -e "${YELLOW}[WARN]${NC}  $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

check_root() {
    if [ "$EUID" -ne 0 ]; then
        log_error "Dieses Script muss als root ausgeführt werden!"
        echo "Verwende: sudo bash restore.sh"
        exit 1
    fi
}

# =============================================================================
# Phase 1: Systemvoraussetzungen
# =============================================================================

install_docker() {
    if command -v docker &>/dev/null; then
        log_ok "Docker ist bereits installiert: $(docker --version)"
        return
    fi

    log_info "Installiere Docker..."
    apt-get update -qq
    apt-get install -y -qq ca-certificates curl gnupg lsb-release

    install -m 0755 -d /etc/apt/keyrings
    curl -fsSL https://download.docker.com/linux/debian/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
    chmod a+r /etc/apt/keyrings/docker.gpg

    echo \
        "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/debian \
        $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | \
        tee /etc/apt/sources.list.d/docker.list > /dev/null

    apt-get update -qq
    apt-get install -y -qq docker-ce docker-ce-cli containerd.io docker-compose-plugin

    systemctl enable --now docker
    log_ok "Docker installiert"
}

install_dependencies() {
    log_info "Installiere Abhängigkeiten..."
    apt-get install -y -qq git jq curl
    log_ok "Abhängigkeiten installiert"
}

# =============================================================================
# Phase 2: Repository klonen
# =============================================================================

clone_repo() {
    log_info "Klone IceHomeAssist Repository..."

    if [ -d "$CLONE_DIR" ]; then
        rm -rf "$CLONE_DIR"
    fi

    git clone "$REPO_URL" "$CLONE_DIR"
    log_ok "Repository geklont nach $CLONE_DIR"
}

# =============================================================================
# Phase 3: Konfiguration wiederherstellen
# =============================================================================

restore_config() {
    log_info "Stelle Home Assistant Konfiguration wieder her..."

    # Verzeichnisse anlegen
    mkdir -p "$HA_CONFIG"
    mkdir -p "$HA_CONFIG/packages"
    mkdir -p "$HA_CONFIG/dashboards"
    mkdir -p "$HA_CONFIG/automations"
    mkdir -p "$HA_CONFIG/templates"
    mkdir -p "$HA_CONFIG/scripts"
    mkdir -p "$HA_CONFIG/themes"
    mkdir -p "$HA_CONFIG/www"

    # Hauptdateien kopieren
    cp "$CLONE_DIR/configuration.yaml" "$HA_CONFIG/"
    cp "$CLONE_DIR/scripts.yaml" "$HA_CONFIG/"
    cp "$CLONE_DIR/groups.yaml" "$HA_CONFIG/"
    cp "$CLONE_DIR/scenes.yaml" "$HA_CONFIG/"
    cp "$CLONE_DIR/utility_meters.yaml" "$HA_CONFIG/" 2>/dev/null || true

    # Verzeichnisse kopieren
    cp "$CLONE_DIR/packages/"*.yaml "$HA_CONFIG/packages/" 2>/dev/null || true
    cp "$CLONE_DIR/dashboards/"*.yaml "$HA_CONFIG/dashboards/" 2>/dev/null || true
    cp "$CLONE_DIR/automations/"*.yaml "$HA_CONFIG/automations/" 2>/dev/null || true
    cp "$CLONE_DIR/templates/"*.yaml "$HA_CONFIG/templates/" 2>/dev/null || true
    cp "$CLONE_DIR/scripts/"*.py "$HA_CONFIG/scripts/" 2>/dev/null || true

    # secrets.yaml Template erstellen
    if [ ! -f "$HA_CONFIG/secrets.yaml" ]; then
        cp "$CLONE_DIR/secrets.yaml.example" "$HA_CONFIG/secrets.yaml"
        log_warn "secrets.yaml wurde aus Template erstellt - MUSS noch ausgefüllt werden!"
    else
        log_warn "secrets.yaml existiert bereits - wird nicht überschrieben"
    fi

    # .gitignore kopieren
    cp "$CLONE_DIR/.gitignore" "$HA_CONFIG/"

    log_ok "Konfiguration wiederhergestellt"
}

# =============================================================================
# Phase 4: Node-RED wiederherstellen
# =============================================================================

restore_nodered() {
    log_info "Stelle Node-RED Flows wieder her..."

    local nodered_dir="$HA_ADDON_CONFIGS/a0d7b954_nodered"
    mkdir -p "$nodered_dir"

    if [ -f "$CLONE_DIR/nodered/flows.json" ]; then
        cp "$CLONE_DIR/nodered/flows.json" "$nodered_dir/"
        log_ok "Node-RED Flows wiederhergestellt"
    else
        log_warn "Keine Node-RED Flows im Backup gefunden"
    fi
}

# =============================================================================
# Phase 5: Docker Container starten
# =============================================================================

start_ha_container() {
    log_info "Starte Home Assistant Container..."

    # Prüfe ob Container bereits läuft
    if docker ps --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
        log_warn "Container '$CONTAINER_NAME' läuft bereits"
        read -p "Container stoppen und neu starten? (j/N) " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Jj]$ ]]; then
            docker stop "$CONTAINER_NAME" 2>/dev/null || true
            docker rm "$CONTAINER_NAME" 2>/dev/null || true
        else
            log_info "Container wird beibehalten"
            return
        fi
    fi

    # Container entfernen falls gestoppt
    docker rm "$CONTAINER_NAME" 2>/dev/null || true

    log_info "Lade HA Container Image..."
    docker pull "$HA_IMAGE"

    docker run -d \
        --name "$CONTAINER_NAME" \
        --privileged \
        --restart=unless-stopped \
        -v /var/lib/homeassistant:/data \
        -v /run/dbus:/run/dbus:ro \
        --network=host \
        "$HA_IMAGE"

    log_ok "Home Assistant Container gestartet"
    log_info "Warte auf HA Start (kann 2-3 Minuten dauern)..."

    # Warte bis HA erreichbar ist
    local retries=0
    while [ $retries -lt 60 ]; do
        if curl -s -o /dev/null -w "%{http_code}" http://localhost:8123 | grep -q "200\|401"; then
            log_ok "Home Assistant ist erreichbar auf http://localhost:8123"
            break
        fi
        sleep 5
        retries=$((retries + 1))
        echo -n "."
    done
    echo

    if [ $retries -ge 60 ]; then
        log_warn "HA reagiert noch nicht - prüfe logs mit: docker logs $CONTAINER_NAME"
    fi
}

# =============================================================================
# Phase 6: HACS installieren
# =============================================================================

install_hacs() {
    log_info "Installiere HACS..."

    local hacs_dir="$HA_CONFIG/custom_components/hacs"
    if [ -d "$hacs_dir" ]; then
        log_ok "HACS ist bereits installiert"
        return
    fi

    # HACS herunterladen
    local hacs_url="https://github.com/hacs/integration/releases/latest/download/hacs.zip"
    local tmp_zip="/tmp/hacs.zip"

    curl -fsSL "$hacs_url" -o "$tmp_zip"
    mkdir -p "$hacs_dir"
    unzip -o "$tmp_zip" -d "$hacs_dir"
    rm -f "$tmp_zip"

    log_ok "HACS installiert - nach HA Neustart unter Einstellungen → Integrationen hinzufügen"
}

# =============================================================================
# Phase 7: Zusammenfassung & manuelle Schritte
# =============================================================================

print_summary() {
    echo
    echo -e "${GREEN}=============================================================================${NC}"
    echo -e "${GREEN} IceHomeAssist - Wiederherstellung abgeschlossen!${NC}"
    echo -e "${GREEN}=============================================================================${NC}"
    echo
    echo -e "${YELLOW}MANUELLE SCHRITTE:${NC}"
    echo
    echo "1. secrets.yaml ausfüllen:"
    echo "   sudo nano $HA_CONFIG/secrets.yaml"
    echo "   → Alle YOUR_* Platzhalter mit echten Werten ersetzen"
    echo
    echo "2. Home Assistant neu starten:"
    echo "   docker restart $CONTAINER_NAME"
    echo
    echo "3. Ersteinrichtung im Browser:"
    echo "   http://$(hostname -I | awk '{print $1}'):8123"
    echo "   → Benutzer anlegen"
    echo "   → HACS Integration hinzufügen (Einstellungen → Integrationen → + HACS)"
    echo
    echo "4. HACS Custom Components installieren:"
    echo "   Folgende Komponenten über HACS → Integrationen nachinstallieren:"
    echo

    if [ -f "$CLONE_DIR/custom_components.txt" ]; then
        grep -v '^#' "$CLONE_DIR/custom_components.txt" | grep -v '^$' | while IFS= read -r line; do
            echo "   - $line"
        done
    fi

    echo
    echo "5. Integrationen neu einrichten (Einstellungen → Integrationen):"
    echo "   - MQTT (Mosquitto Addon installieren)"
    echo "   - Tibber (API Token aus secrets.yaml)"
    echo "   - Alexa Media Player (Amazon Login + 2FA)"
    echo "   - Divera 24/7 (API Key aus secrets.yaml)"
    echo "   - DWD Wetterwarnungen"
    echo "   - Dreame Vacuum (Cloud Credentials)"
    echo "   - FritzBox (Router Login)"
    echo "   - Meross (Cloud + LAN)"
    echo "   - Tractive (Pet Tracker Login)"
    echo
    echo "6. Node-RED Addon installieren:"
    echo "   Einstellungen → Add-ons → Add-on Store → Node-RED"
    echo "   Flows werden automatisch geladen aus: $HA_ADDON_CONFIGS/a0d7b954_nodered/"
    echo
    echo "7. scripts/unifi_radar_data.py Credentials eintragen:"
    echo "   sudo nano $HA_CONFIG/scripts/unifi_radar_data.py"
    echo "   → HOST, USER, PW anpassen"
    echo
    echo -e "${GREEN}=============================================================================${NC}"
    echo -e "${GREEN} Dokumentation: https://github.com/icepaule/IceHomeAssist${NC}"
    echo -e "${GREEN}=============================================================================${NC}"
}

# =============================================================================
# MAIN
# =============================================================================

main() {
    echo
    echo -e "${BLUE}=============================================================================${NC}"
    echo -e "${BLUE} IceHomeAssist - Disaster Recovery${NC}"
    echo -e "${BLUE}=============================================================================${NC}"
    echo

    check_root
    install_dependencies
    install_docker
    clone_repo
    restore_config
    restore_nodered
    start_ha_container
    install_hacs
    print_summary

    # Aufräumen
    rm -rf "$CLONE_DIR"
}

main "$@"
