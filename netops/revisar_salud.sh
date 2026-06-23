#!/usr/bin/env bash
set -uo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$DIR/config.env"
U="$MNUTIL"
SSHM="ssh -n -o StrictHostKeyChecking=no -o ConnectTimeout=8 $MININET_SSH"

problemas=()

links=$(curl -s --max-time 5 "$CONTROLLER_URL/sdn/topology" \
        | python3 -c 'import sys,json;print(len(json.load(sys.stdin).get("links",[])))' 2>/dev/null || echo "0")
if [ "${links:-0}" -lt "$EXPECTED_LINKS" ]; then
    problemas+=("Topologia degradada. Enlaces activos ${links} de ${EXPECTED_LINKS}. Posible enlace caido.")
fi

loss=$($SSHM "sudo $U h1 ping -c 10 -i 0.2 -W 1 10.0.0.8" 2>/dev/null \
       | grep -oP '[0-9]+(?=% packet loss)' | tail -1)
loss=${loss:-100}
if [ "${loss:-100}" -gt "$LOSS_THRESHOLD" ]; then
    problemas+=("Perdida de paquetes en el camino h1 a h8 de ${loss}%, por encima del umbral de ${LOSS_THRESHOLD}%. Posible enlace degradado.")
fi

web=$($SSHM "sudo $U h1 nc -z -w3 ${WEB_SERVER_IP} 80 && echo UP || echo DOWN" 2>/dev/null)
if ! echo "$web" | grep -q UP; then
    problemas+=("Servidor web en ${WEB_SERVER_HOST} (${WEB_SERVER_IP}) sin respuesta en el puerto 80.")
fi

if [ ${#problemas[@]} -eq 0 ]; then
    echo "Estado de la red operativa. Enlaces ${links} de ${EXPECTED_LINKS}. Perdida h1 a h8 del ${loss}%. Servidor web ${WEB_SERVER_HOST} respondiendo en el puerto 80."
else
    echo "PROBLEMA detectado. Se identificaron las siguientes incidencias:"
    for p in "${problemas[@]}"; do echo "  $p"; done
fi
