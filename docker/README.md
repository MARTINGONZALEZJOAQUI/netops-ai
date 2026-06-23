# Hermes Agent en modo Docker

El PDF del microproyecto pide correr Hermes Agent en modo Docker para aislar la ejecución de comandos. La imagen oficial `nousresearch/hermes-agent` ya trae Hermes instalado y monta toda la configuración del usuario (`~/.hermes`) en `/opt/data`. Este directorio agrega una capa delgada con las herramientas de red que necesitan los scripts del agente.

## Por qué la imagen envoltorio

Los scripts de NetOps hacen SSH a la máquina de Mininet y consultas HTTP al controlador. La imagen oficial no incluye `ssh`, `curl` ni `nc`, así que el `Dockerfile` parte de la oficial y los instala.

## Requisitos

- Docker instalado en WSL2.
- Las dos máquinas virtuales encendidas (Ryu y Mininet).
- El directorio `~/.hermes` configurado con `config.yaml` y `.env` reales.
- Los scripts en `~/netops` y la llave SSH en `~/.ssh`.

## Instalar Docker en WSL

    curl -fsSL https://get.docker.com -o get-docker.sh
    sudo sh get-docker.sh
    sudo usermod -aG docker $USER
    sudo service docker start

Cerrar y reabrir la terminal de WSL para aplicar el grupo `docker`.

## Parar el gateway nativo

Si el gateway nativo está corriendo hay que pararlo antes para que los dos procesos no choquen contra el mismo bot de Telegram.

    hermes gateway stop

## Construir y levantar

    cd docker
    docker compose up -d --build

## Verificar

    docker logs -f hermes
    docker exec hermes bash -lc 'echo HOME=$HOME; command -v ssh curl nc python3; ls ~/netops'

Si `HOME` dentro del contenedor no es `/opt/data`, ajustar los destinos de los montajes `~/netops` y `~/.ssh` en `docker-compose.yml` para que coincidan con el home real del usuario del contenedor.
