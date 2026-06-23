#!/usr/bin/env bash
set -uo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$DIR/config.env"
M="$MININET_SSH"; U="$MNUTIL"; C="$CONTROLLER_URL"
sshm() { ssh -n -o StrictHostKeyChecking=no -o ConnectTimeout=8 "$M" "$@" 2>&1; }

limpiar() {
    sshm "for i in \$(ls /sys/class/net | grep -E '^s[0-9]+-eth'); do sudo tc qdisc del dev \$i root 2>/dev/null; done; echo ok" >/dev/null
    curl -s "$C/sdn/topology" | python3 -c '
import sys, json
for l in json.load(sys.stdin).get("disabled_links", []):
    print(l[0], l[1])
' | while read RA RB; do
        [ -n "$RA" ] && curl -s -X POST "$C/sdn/link/enable" -H 'Content-Type: application/json' -d "{\"a\": $RA, \"b\": $RB}" >/dev/null
    done
    for pair in "10.0.0.3 10.0.0.8" "10.0.0.8 10.0.0.3"; do
        set -- $pair
        curl -s -X POST "$C/sdn/unblock" -H 'Content-Type: application/json' -d "{\"src_ip\": \"$1\", \"dst_ip\": \"$2\"}" >/dev/null
    done
    sshm "for s in 1 2 3 4 5 6 7 8; do for d in 1 2 3 4 5 6 7 8; do [ \$s -ne \$d ] && sudo $U h\$s ping -c1 -W1 10.0.0.\$d >/dev/null 2>&1; done; done; echo ok" >/dev/null
    rm -f "$DIR/.enlace_remediado" "$DIR/.enlace_degradado"
}

enlace_activo() {
    sshm "sudo $U h1 ping -c 6 -i 0.2 10.0.0.8 >/dev/null 2>&1"
    curl -s "$C/sdn/flows" | python3 -c '
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
'
}

case "${1:-on}" in
  on)
    limpiar; sleep 4
    read A B < <(enlace_activo)
    if [ -z "${A:-}" ]; then echo "No pude obtener la ruta activa h1->h8 (controlador caido?)."; exit 1; fi
    IFA=$(sshm "ip -o link show | grep -oE 's${A}-eth[0-9]+@s${B}-eth[0-9]+' | head -1 | cut -d@ -f1")
    IFB=$(sshm "ip -o link show | grep -oE 's${B}-eth[0-9]+@s${A}-eth[0-9]+' | head -1 | cut -d@ -f1")
    sshm "sudo tc qdisc replace dev $IFA root netem loss 30%" >/dev/null
    sshm "sudo tc qdisc replace dev $IFB root netem loss 30%" >/dev/null
    echo "$A $B" > "$DIR/.enlace_degradado"
    sleep 2
    echo "Falla ARMADA: 30% de perdida en el enlace s${A}-s${B} (ruta activa h1->h8)."
    bash "$DIR/revisar_salud.sh"
    ;;
  off)
    limpiar; sleep 3
    echo "Falla LIMPIADA: netem removido y todos los enlaces rehabilitados."
    bash "$DIR/revisar_salud.sh"
    ;;
  *) echo "Uso: simular_falla.sh on|off" ;;
esac
