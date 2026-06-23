#!/usr/bin/env bash
set -euo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$DIR/config.env"

curl -s "$CONTROLLER_URL/sdn/topology" | python3 -c '
import sys, json
d = json.load(sys.stdin)
sw    = d.get("switches", [])
links = d.get("links", [])
hosts = d.get("hosts", {})
dis   = d.get("disabled_links", [])
print("=== ESTADO DE LA RED SDN ===")
print("Switches activos:", len(sw), sw)
print("Enlaces activos :", len(links))
print("Hosts conocidos :", len(hosts), list(hosts.keys()))
if dis:
    print("Enlaces deshabilitados por politica:", dis)
'
echo "--- Rutas activas ---"
curl -s "$CONTROLLER_URL/sdn/flows" | python3 -c '
import sys, json
flows = json.load(sys.stdin)
if not flows:
    print(" (sin flujos activos; ejecuta pingall o trafico en Mininet)")
for f in flows:
    print(" ", f["src_ip"], "->", f["dst_ip"], " path=", f["path"])
'
