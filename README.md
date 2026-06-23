# NetOps AI — Agente de gestión de fallas SDN sobre Hermes Agent

Agente que actúa como administrador de red de nivel 1 y 2, accesible por Telegram. Monitorea una red definida por software, avisa de incidencias de forma proactiva y, a petición del operador, diagnostica la falla y aplica una política de enrutamiento alternativo. Corresponde a la Opción 1 del microproyecto de la electiva.

## Arquitectura

- **Hermes Agent v0.16.0** gestiona la conversación por Telegram y la ejecución de herramientas.
- **Modelo de lenguaje** en la nube mediante **NVIDIA NIM** (`meta/llama-3.3-70b-instruct`), porque la GPU del portátil (8 GB) no alcanza para un modelo local con la capacidad necesaria.
- **Scripts locales** en `netops/` son las herramientas del agente. Ejecutan ping, consultas de topología y políticas sobre el controlador.
- **Red SDN** con controlador **Ryu** (`sdn/routing_engine_simple.py`, Dijkstra, OpenFlow 1.3) y topología **GEANT** en **Mininet** (`sdn/geant_topo.py`, 10 switches, 8 hosts, 15 enlaces).
- **Trabajo programado** nativo de Hermes (`hermes/cron/`) revisa cada cinco minutos la red y el servidor web del host h5 y publica alertas en Telegram.

## Estructura

- `hermes/` configuración del agente (SOUL, skill, cron, config de ejemplo).
- `netops/` los scripts que son las herramientas del agente.
- `sdn/` controlador Ryu y topología Mininet que corren en las VMs.
- `docker/` Hermes Agent en modo Docker.

## Dependencias

- Hermes Agent v0.16.0 (paquete `hermes-agent`) o la imagen `nousresearch/hermes-agent`.
- Cuenta y API key de NVIDIA NIM (gratuita, prefijo `nvapi-`).
- Bot de Telegram (token de BotFather).
- Ryu y Mininet en las máquinas virtuales (16 GB RAM, 4 vCPUs cada una).
- Herramientas de red en el entorno del agente: `ssh`, `curl`, `nc`, `python3`.

## Permisos

- Repositorio público para que el enlace de Classroom sea de acceso directo.
- Los scripts `.sh` conservan el bit de ejecución.
- Las acciones de escritura del agente (deshabilitar enlaces, bloquear tráfico) piden autorización explícita por Telegram antes de ejecutarse.

## Configuración (no se suben secretos)

Este repositorio no incluye credenciales. Para correrlo:

1. Copiar `.env.example` a `.env` y completar el token de Telegram y la API key de NVIDIA.
2. Copiar `hermes/config.yaml.example` a `config.yaml` y poner la API key real.
3. Copiar `netops/config.env.example` a `config.env` y poner las IPs del controlador y de Mininet.

## Cómo validar el resultado

La demostración completa necesita las dos máquinas virtuales y los tokens, así que la validación principal es el video de la demo:

**Video de la demostración:** PENDIENTE_ENLACE_DEL_VIDEO

El video muestra, en orden: la alerta proactiva del trabajo programado, la consulta de estado de la red, la revisión de salud, una prueba de conectividad, el diagnóstico con remediación automática (con evidencia cruzada en el registro de Ryu), la verificación de la recuperación y el bloqueo de tráfico bajo autorización.

Para reproducir el entorno, ver `docker/README.md`.
