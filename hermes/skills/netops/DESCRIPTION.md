---
name: netops
description: "Gestion y monitoreo de la red SDN (Mininet/Ryu, topologia GEANT). USAR SIEMPRE que el usuario pregunte por: estado de la red, switches, enlaces, hosts, conectividad, ping, latencia, perdida de paquetes, fallas, salud de la red, enrutamiento/routing, bloquear trafico, o aplicar politica de ruta alternativa."
version: 3.0.0
author: NetOps AI
license: MIT
platforms: [linux]
metadata:
  hermes:
    tags: [sdn, red, network, mininet, ryu, netops, monitoreo, routing]
---

# NetOps — red SDN (Ryu + Mininet, topologia GEANT)

10 switches (s1..s10), 8 hosts (h1..h8); el host hN tiene IP 10.0.0.N. Red sana: 15 enlaces.

Para CUALQUIER pregunta sobre la red, ejecuta el script correspondiente con la tool
`terminal` y responde con su salida REAL. Nunca inventes cifras ni estados.

Lectura (ejecuta directo):
- estado de la red / switches / enlaces / hosts / rutas -> `bash ~/netops/estado_red.sh`
- ping / conectividad entre dos hosts -> `bash ~/netops/probar_conexion.sh h1 h8`
  (NUNCA uses el comando `ping` del sistema; los hosts hN solo existen en Mininet)
- salud / "¿hay alguna falla?" -> `bash ~/netops/revisar_salud.sh`

Escritura (pide "¿confirmas? (si/no)" y ejecuta solo tras un "si"):
- bloquear trafico -> `bash ~/netops/bloquear_trafico.sh 10.0.0.X 10.0.0.Y`

## Diagnostico y remediacion (politica de ruta alternativa)
Cuando el usuario pida "diagnostica y aplica la politica de enrutamiento alternativo"
ante una perdida en h1->h8, haz EXACTAMENTE esto con la tool `terminal`:
1. Confirma la falla: ejecuta `bash ~/netops/revisar_salud.sh` y reporta el % de perdida real.
2. Pide confirmacion al usuario: "Voy a aplicar la ruta alternativa. ¿Confirmas? (si/no)".
3. Solo tras un "si", ejecuta UN SOLO comando, exactamente asi y sin cambiarlo:
   `bash ~/netops/arreglar_sdn.sh`
   Ese script diagnostica, deshabilita el enlace degradado (reruteo Dijkstra) y mide la
   recuperacion con ping real. NO inventes ni uses otro comando; no escribas placeholders.
4. Reporta su salida REAL. Declara exito SOLO si la salida contiene `success: true`
   y la perdida final bajo a ~0%. Si dice `success: false`, reporta el fallo, no exito.

Reporta el resultado real del script. Declara exito SOLO si la salida lo confirma
(`success: true` o perdida ~0%). Nunca inventes. No uses comandos genericos de Linux; solo ~/netops/.
