#!/usr/bin/env python3
"""Get active port details with utilization from a MikroTik SwOS switch.

Usage: python3 snmp_switch_ports.py <host_ip>
Output: JSON with count, ports (including utilization bar)

Uses individual get_cmd calls (not walk) because SwOS walk traverses
into counter tables and can time out.
Tracks state between runs to calculate port utilization.
"""
import asyncio
import json
import os
import sys
import time
from pysnmp.hlapi.v3arch.asyncio import (
    SnmpEngine, CommunityData, UdpTransportTarget, ContextData,
    ObjectType, ObjectIdentity, get_cmd,
)

HOST = sys.argv[1] if len(sys.argv) > 1 else "192.168.178.165"
PORTS = 26
STATE_FILE = f"/tmp/snmp_ports_{HOST.replace('.', '_')}.json"


def load_previous():
    try:
        with open(STATE_FILE) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return None


def save_state(data):
    try:
        with open(STATE_FILE, "w") as f:
            json.dump(data, f)
    except OSError:
        pass


def make_bar(pct):
    filled = min(int(pct / 10), 10)
    return "\u2588" * filled + "\u2591" * (10 - filled)


async def main():
    engine = SnmpEngine()
    community = CommunityData("public")
    transport = await UdpTransportTarget.create((HOST, 161), timeout=3, retries=1)

    now = time.time()
    previous = load_previous()
    prev_time = previous["timestamp"] if previous else 0
    prev_counters = previous.get("counters", {}) if previous else {}
    time_delta = now - prev_time if prev_time else 0

    ports = []
    counters = {}

    for port in range(1, PORTS + 1):
        oids = [
            ObjectType(ObjectIdentity(f"1.3.6.1.2.1.2.2.1.2.{port}")),
            ObjectType(ObjectIdentity(f"1.3.6.1.2.1.2.2.1.8.{port}")),
            ObjectType(ObjectIdentity(f"1.3.6.1.2.1.2.2.1.5.{port}")),
            ObjectType(ObjectIdentity(f"1.3.6.1.2.1.2.2.1.10.{port}")),
            ObjectType(ObjectIdentity(f"1.3.6.1.2.1.2.2.1.16.{port}")),
        ]
        ei, es, _, vbs = await get_cmd(
            engine, community, transport, ContextData(), *oids
        )
        if ei or es:
            continue

        name = str(vbs[0][1])
        try:
            status = int(vbs[1][1])
        except (ValueError, TypeError):
            continue
        if status != 1:
            continue

        try:
            speed_bps = int(vbs[2][1])
        except (ValueError, TypeError):
            speed_bps = 0
        speed_mbps = speed_bps // 1000000

        try:
            in_octets = int(vbs[3][1])
        except (ValueError, TypeError):
            in_octets = 0
        try:
            out_octets = int(vbs[4][1])
        except (ValueError, TypeError):
            out_octets = 0

        counters[str(port)] = {"in": in_octets, "out": out_octets}

        util_pct = 0
        in_mbps = 0.0
        out_mbps = 0.0
        prev = prev_counters.get(str(port))
        if prev and time_delta > 10 and speed_bps > 0:
            in_delta = (in_octets - prev["in"]) % 4294967296
            out_delta = (out_octets - prev["out"]) % 4294967296
            in_rate = in_delta / time_delta
            out_rate = out_delta / time_delta
            in_mbps = round(in_rate * 8 / 1000000, 1)
            out_mbps = round(out_rate * 8 / 1000000, 1)
            max_rate = speed_bps / 8
            if max_rate > 0:
                util_pct = round(max(in_rate, out_rate) / max_rate * 100, 1)
                util_pct = min(util_pct, 100.0)

        ports.append({
            "port": port,
            "name": name,
            "speed": speed_mbps,
            "in": in_mbps,
            "out": out_mbps,
            "util": round(util_pct),
            "bar": make_bar(util_pct),
        })

    save_state({"timestamp": now, "counters": counters})
    print(json.dumps({"count": len(ports), "ports": ports}))


try:
    asyncio.run(main())
except Exception:
    print('{"count":0,"ports":[]}')
