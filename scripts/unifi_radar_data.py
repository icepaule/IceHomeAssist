#!/usr/bin/env python3
"""Fetch UniFi rogueap + client data, generate radar SVGs, output JSON for HA."""
import requests, urllib3, json, re, sys, time, math, os
urllib3.disable_warnings()

HOST = 'https://YOUR_UNIFI_HOST:8443'
USER = 'YOUR_UNIFI_USERNAME'
PW = 'YOUR_UNIFI_PASSWORD'
SVG_DIR = '/config/www'

SSID_COLORS = {
    'Bad:INet': '#00ff88',
    'Bad:IoT': '#ffaa00',
    'Bad:Bad': '#aa44ff',
}

def login():
    s = requests.Session()
    s.verify = False
    r = s.post(f'{HOST}/api/auth/login',
        json={'username': USER, 'password': PW}, timeout=10)
    if r.status_code != 200:
        return None
    sc = r.headers.get('Set-Cookie', '')
    m = re.search(r'TOKEN=([^;]+)', sc)
    csrf = r.headers.get('X-Csrf-Token', '')
    if m:
        s.cookies.set('TOKEN', m.group(1))
        s.headers['X-Csrf-Token'] = csrf
    return s

def signal_to_radius(signal, max_r=170):
    """Convert signal (dBm) to radius. Closer = stronger signal."""
    s = max(min(abs(signal), 95), 20)
    return max(20, (s - 20) / 75 * max_r)

def generate_radar_svg(ap_name, clients, nearby, filename):
    """Generate an SVG radar visualization."""
    W, H = 440, 460
    CX, CY = 220, 210
    R = 180

    lines = []
    lines.append(f'<svg viewBox="0 0 {W} {H}" xmlns="http://www.w3.org/2000/svg">')
    lines.append(f'<rect width="{W}" height="{H}" rx="12" fill="#0f0f1a"/>')

    # Radar rings with gradient
    for i, r in enumerate([45, 90, 135, 180]):
        opacity = 0.15 + i * 0.05
        lines.append(f'<circle cx="{CX}" cy="{CY}" r="{r}" fill="none" stroke="#3a3a5c" stroke-width="0.8" opacity="{opacity}"/>')

    # Ring labels
    for r, label in [(45, '-30'), (90, '-50'), (135, '-70'), (180, '-90')]:
        lines.append(f'<text x="{CX+r+3}" y="{CY-3}" fill="#444" font-size="8" font-family="monospace">{label}</text>')

    # Cross hair
    lines.append(f'<line x1="{CX}" y1="{CY-R}" x2="{CX}" y2="{CY+R}" stroke="#2a2a3c" stroke-width="0.5"/>')
    lines.append(f'<line x1="{CX-R}" y1="{CY}" x2="{CX+R}" y2="{CY}" stroke="#2a2a3c" stroke-width="0.5"/>')

    # AP center glow
    lines.append(f'<circle cx="{CX}" cy="{CY}" r="16" fill="#00d4ff" opacity="0.08"/>')
    lines.append(f'<circle cx="{CX}" cy="{CY}" r="10" fill="#00d4ff" opacity="0.15"/>')
    lines.append(f'<circle cx="{CX}" cy="{CY}" r="5" fill="#00d4ff" opacity="0.9"/>')

    # Nearby devices (red dots, drawn first = behind)
    n_count = max(len(nearby), 1)
    for i, n in enumerate(nearby[:25]):
        dist = signal_to_radius(n.get('signal', -95))
        angle = (i * 360 / min(n_count, 25) + 7) * math.pi / 180
        x = CX + dist * math.cos(angle)
        y = CY + dist * math.sin(angle)
        opacity = max(0.2, 0.7 - dist / R * 0.5)
        size = max(2, 4 - dist / R * 2)
        lines.append(f'<circle cx="{x:.0f}" cy="{y:.0f}" r="{size:.1f}" fill="#ff4444" opacity="{opacity:.2f}"/>')
        if n.get('essid') and dist < 140:
            lines.append(f'<text x="{x:.0f}" y="{y+size+8:.0f}" text-anchor="middle" fill="#663333" font-size="6" font-family="sans-serif" opacity="0.6">{n["essid"][:12]}</text>')

    # Connected clients (large colored dots)
    c_count = max(len(clients), 1)
    for i, c in enumerate(clients):
        dist = signal_to_radius(c.get('signal', -70))
        angle = (i * 360 / c_count + 180) * math.pi / 180
        x = CX + dist * math.cos(angle)
        y = CY + dist * math.sin(angle)
        color = SSID_COLORS.get(c.get('essid', ''), '#00ff88')
        name = c.get('name', '?')[:14]
        sig = c.get('signal', 0)

        # Glow effect
        lines.append(f'<circle cx="{x:.0f}" cy="{y:.0f}" r="12" fill="{color}" opacity="0.1"/>')
        lines.append(f'<circle cx="{x:.0f}" cy="{y:.0f}" r="7" fill="{color}" opacity="0.85"/>')
        # Label
        lines.append(f'<text x="{x:.0f}" y="{y+18:.0f}" text-anchor="middle" fill="#ddd" font-size="8" font-family="sans-serif" font-weight="bold">{name}</text>')
        lines.append(f'<text x="{x:.0f}" y="{y+27:.0f}" text-anchor="middle" fill="#888" font-size="7" font-family="monospace">{sig} dBm</text>')

    # Legend bar
    ly = H - 35
    items = [
        ('#00ff88', 'Bad:INet'),
        ('#ffaa00', 'Bad:IoT'),
        ('#aa44ff', 'Bad:Bad'),
        ('#ff4444', 'Nearby'),
    ]
    lx = 20
    for color, label in items:
        r = 4 if label != 'Nearby' else 3
        op = '0.85' if label != 'Nearby' else '0.5'
        lines.append(f'<circle cx="{lx+r}" cy="{ly}" r="{r}" fill="{color}" opacity="{op}"/>')
        lines.append(f'<text x="{lx+r*2+5}" y="{ly+3}" fill="#888" font-size="9" font-family="sans-serif">{label}</text>')
        lx += len(label) * 7 + 25

    # Title
    lines.append(f'<text x="{CX}" y="{H-10}" text-anchor="middle" fill="#555" font-size="9" font-family="sans-serif">{ap_name} | {len(clients)} Clients | {len(nearby)} Nearby</text>')

    lines.append('</svg>')
    svg = '\n'.join(lines)

    os.makedirs(SVG_DIR, exist_ok=True)
    with open(os.path.join(SVG_DIR, filename), 'w') as f:
        f.write(svg)

def main():
    s = login()
    if not s:
        print(json.dumps({"error": "login_failed", "aps": [], "total_clients": 0, "total_nearby": 0}))
        sys.exit(0)

    now = int(time.time())

    # Get APs
    r = s.get(f'{HOST}/proxy/network/api/s/default/stat/device', timeout=10)
    aps = {}
    if r.status_code == 200:
        for d in r.json().get('data', []):
            if d.get('type') == 'uap':
                aps[d['mac']] = {
                    'name': d.get('name', d.get('mac')),
                    'mac': d['mac'],
                    'ip': d.get('ip', ''),
                    'clients': [],
                    'nearby': []
                }

    # Get connected clients
    r = s.get(f'{HOST}/proxy/network/api/s/default/stat/sta', timeout=10)
    if r.status_code == 200:
        for c in r.json().get('data', []):
            ap = c.get('ap_mac')
            if ap and ap in aps and c.get('essid'):
                aps[ap]['clients'].append({
                    'name': c.get('name') or c.get('hostname') or c.get('mac', '?')[:8],
                    'mac': c.get('mac', ''),
                    'ip': c.get('ip', ''),
                    'essid': c.get('essid', ''),
                    'rssi': c.get('rssi', 0),
                    'signal': c.get('signal', -100),
                    'channel': c.get('channel', 0),
                    'radio': c.get('radio', ''),
                    'satisfaction': c.get('satisfaction', 0),
                })

    # Get rogueap / nearby
    r = s.get(f'{HOST}/proxy/network/api/s/default/stat/rogueap', timeout=10)
    if r.status_code == 200:
        for d in r.json().get('data', []):
            ap = d.get('ap_mac')
            age = now - d.get('last_seen', 0)
            if ap and ap in aps and age < 86400:
                aps[ap]['nearby'].append({
                    'bssid': d.get('bssid', ''),
                    'essid': d.get('essid', ''),
                    'rssi': d.get('rssi', 0),
                    'signal': d.get('signal', -100),
                    'channel': d.get('channel', 0),
                    'oui': d.get('oui', ''),
                    'band': d.get('band', ''),
                    'age': age,
                })

    # Sort
    for ap in aps.values():
        ap['nearby'].sort(key=lambda x: x.get('signal', -100), reverse=True)
        ap['clients'].sort(key=lambda x: x.get('signal', -100), reverse=True)

    ap_list = list(aps.values())

    # Generate SVG radar files
    if len(ap_list) > 0:
        generate_radar_svg(ap_list[0]['name'], ap_list[0]['clients'], ap_list[0]['nearby'], 'radar_1og.svg')
    if len(ap_list) > 1:
        generate_radar_svg(ap_list[1]['name'], ap_list[1]['clients'], ap_list[1]['nearby'], 'radar_keller.svg')

    result = {
        'timestamp': now,
        'aps': ap_list,
        'total_clients': sum(len(a['clients']) for a in ap_list),
        'total_nearby': sum(len(a['nearby']) for a in ap_list),
    }

    # Write JSON data file for interactive radar
    os.makedirs(SVG_DIR, exist_ok=True)
    with open(os.path.join(SVG_DIR, 'radar_data.json'), 'w') as f:
        json.dump(result, f)

    print(json.dumps(result))

if __name__ == '__main__':
    main()
