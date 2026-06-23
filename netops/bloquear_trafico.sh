#!/usr/bin/env bash
set -uo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$DIR/config.env"

norm_ip() { local x="$1"; if [[ "$x" == h* ]]; then echo "10.0.0.${x#h}"; else echo "$x"; fi; }
SRC="$(norm_ip "${1:?host o IP origen, ej h3 o 10.0.0.3}")"
DST="$(norm_ip "${2:?host o IP destino, ej h8 o 10.0.0.8}")"
sn="${SRC##*.}"

ssh -n -o StrictHostKeyChecking=no -o ConnectTimeout=8 "$MININET_SSH" \
    "sudo $MNUTIL h$sn ping -c 2 -W 1 $DST" >/dev/null 2>&1 || true

post() {
    curl -s -X POST "$CONTROLLER_URL/sdn/block" \
         -H 'Content-Type: application/json' \
         -d "{\"src_ip\": \"$1\", \"dst_ip\": \"$2\"}"
    echo
}

echo "Bloqueo $SRC -> $DST:"
post "$SRC" "$DST"
echo "Bloqueo $DST -> $SRC:"
post "$DST" "$SRC"
