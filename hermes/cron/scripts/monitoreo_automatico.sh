#!/usr/bin/env bash
OUT="$(bash "$HOME/netops/revisar_salud.sh" 2>&1)"
if echo "$OUT" | grep -q "PROBLEMA"; then
    echo "NetOps AI. Alerta de monitoreo."
    echo
    echo "$OUT"
    echo
    echo "Puede responder en este chat para que el agente diagnostique y aplique una ruta alternativa."
fi
