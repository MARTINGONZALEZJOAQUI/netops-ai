#!/usr/bin/env bash
source ~/netops/config.env
C="$CONTROLLER_URL"; M="$MININET_SSH"; U="$MNUTIL"
sshm() { ssh -n -o StrictHostKeyChecking=no -o ConnectTimeout=10 "$M" "$@" 2>&1; }

sshm "for i in \$(ls /sys/class/net | grep -E '^s[0-9]+-eth'); do sudo tc qdisc del dev \$i root 2>/dev/null; done; echo ok"
curl -s "$C/sdn/topology" | python3 -c 'import sys,json
for l in json.load(sys.stdin).get("disabled_links",[]): print(l[0],l[1])' | while read A B; do
    [ -n "$A" ] && curl -s -X POST "$C/sdn/link/enable" -H 'Content-Type: application/json' -d "{\"a\": $A, \"b\": $B}" >/dev/null
done
for pair in "10.0.0.3 10.0.0.8" "10.0.0.8 10.0.0.3"; do
    set -- $pair
    curl -s -X POST "$C/sdn/unblock" -H 'Content-Type: application/json' -d "{\"src_ip\": \"$1\", \"dst_ip\": \"$2\"}" >/dev/null
done
sshm "for s in 1 2 3 4 5 6 7 8; do for d in 1 2 3 4 5 6 7 8; do [ \$s -ne \$d ] && sudo $U h\$s ping -c1 -W1 10.0.0.\$d >/dev/null 2>&1; done; done; echo ok"
rm -f ~/netops/.enlace_degradado ~/netops/.enlace_remediado
bash ~/netops/revisar_salud.sh
