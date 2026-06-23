#!/usr/bin/env bash
set -euo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$DIR/config.env"

SRC="${1:-h1}"
DST="${2:-h8}"
DSTNUM="${DST#h}"
DSTIP="10.0.0.${DSTNUM}"

echo "Probando conectividad $SRC -> $DST ($DSTIP) ..."
ssh -n -o StrictHostKeyChecking=no -o ConnectTimeout=8 "$MININET_SSH" \
    "sudo $MNUTIL $SRC ping -c 5 -i 0.3 -W 1 $DSTIP"
