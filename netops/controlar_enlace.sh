#!/usr/bin/env bash
set -euo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$DIR/config.env"

ACTION="${1:?uso: controlar_enlace.sh disable|enable A B}"
A="${2:?switch A (numero, ej 3)}"
B="${3:?switch B (numero, ej 4)}"

if [ "$ACTION" != "disable" ] && [ "$ACTION" != "enable" ]; then
    echo "Accion invalida: usa 'disable' o 'enable'"; exit 1
fi

curl -s -X POST "$CONTROLLER_URL/sdn/link/$ACTION" \
     -H 'Content-Type: application/json' \
     -d "{\"a\": $A, \"b\": $B}"
echo
