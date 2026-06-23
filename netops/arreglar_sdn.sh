#!/usr/bin/env bash
set -uo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$DIR/config.env"
M="$MININET_SSH"; U="$MNUTIL"; C="$CONTROLLER_URL"
sshm() { ssh -n -o StrictHostKeyChecking=no -o ConnectTimeout=8 "$M" "$@" 2>&1; }
loss() { sshm "sudo $U h1 ping -c 10 -i 0.2 -W 1 10.0.0.8" | grep -oP '[0-9]+(?=% packet loss)' | tail -1; }

A=""; B=""; ORIG="monitoreo"
if [ -f "$DIR/.enlace_degradado" ]; then
    read A B < "$DIR/.enlace_degradado"
fi
if [ -z "${A:-}" ]; then
    ORIG="ruta activa"
    sshm "sudo $U h1 ping -c 5 -i 0.2 10.0.0.8 >/dev/null 2>&1"
    read A B < <(curl -s "$C/sdn/flows" | python3 -c '
import sys, json
p = []
for f in json.load(sys.stdin):
    s, d = f.get("src_ip"), f.get("dst_ip")
    if {s, d} == {"10.0.0.1", "10.0.0.8"}:
        p = f.get("path", [])
        if s == "10.0.0.8": p = list(reversed(p))
        break
links = [(p[i], p[i+1]) for i in range(len(p)-1)]
if links:
    a, b = links[len(links)//2]; print(a, b)
')
fi
if [ -z "${A:-}" ]; then
    echo "No se pudo identificar el enlace degradado de h1->h8. success: false"; exit 0
fi
echo "Diagnostico ($ORIG): el enlace troncal degradado en la ruta h1->h8 es s${A}-s${B}."

lb=$(loss); lb=${lb:-100}
echo "Perdida h1->h8 antes de remediar: ${lb}%."

echo "Aplicando politica de ruta alternativa: deshabilitando enlace s${A}-s${B}..."
resp=$(curl -s -X POST "$C/sdn/link/disable" -H 'Content-Type: application/json' -d "{\"a\": $A, \"b\": $B}")
echo "Respuesta del controlador: ${resp}"
echo "$A $B" > "$DIR/.enlace_remediado"

sleep 3
sshm "sudo $U h1 ping -c 3 -W 1 10.0.0.8" >/dev/null 2>&1 || true

la=$(loss); la=${la:-100}
echo "Perdida h1->h8 despues de remediar: ${la}%."

if [ "${la:-100}" -le "$LOSS_THRESHOLD" ]; then
    echo "REMEDIACION EXITOSA. La ruta alternativa restauro la conectividad: perdida bajo de ${lb}% a ${la}%. success: true"
else
    echo "REMEDIACION NO efectiva (perdida ${la}%). Revisar manualmente. success: false"
fi
