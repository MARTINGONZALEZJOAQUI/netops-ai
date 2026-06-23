# NetOps AI. Agente de gestión de fallas SDN sobre Hermes Agent

NetOps AI es un agente que actúa como administrador de red de nivel 1 y 2 y se opera por Telegram. El agente monitorea una red definida por software, avisa de las incidencias de forma proactiva y, cuando el operador se lo pide, diagnostica la falla y aplica una política de enrutamiento alternativo. El proyecto corresponde a la Opción 1 del microproyecto de la electiva.

## Arquitectura

El sistema se reparte en tres máquinas que trabajan juntas.

1. El portátil ejecuta el subsistema WSL2 con Ubuntu. Allí corre el framework Hermes Agent, que gestiona la conversación de Telegram y la ejecución de las herramientas. En ese mismo entorno viven los scripts que el agente usa como herramientas.
2. La primera máquina virtual ejecuta el controlador Ryu en la dirección 192.168.43.154. El controlador calcula las rutas con el algoritmo de Dijkstra sobre OpenFlow 1.3 y expone una interfaz REST para consultar la topología y aplicar políticas.
3. La segunda máquina virtual ejecuta Mininet en la dirección 192.168.43.65. Mininet levanta la topología GEANT, que contiene diez switches, ocho hosts y quince enlaces, y un servidor web en el host crítico h5 que sirve como servicio vigilado.

El modelo de lenguaje no corre en el portátil. Se consume en la nube mediante NVIDIA NIM con el modelo meta/llama-3.3-70b-instruct, porque la tarjeta gráfica del portátil dispone de ocho gigabytes de memoria, una cantidad insuficiente para un modelo local con la capacidad de razonamiento y de uso de herramientas que el proyecto necesita. La arquitectura del agente es la misma y lo único que cambia es el lugar donde se ejecuta el modelo.

Un trabajo programado nativo de Hermes revisa cada cinco minutos el estado de la red y del servidor web del host h5. Cuando detecta una incidencia, publica una alerta en el chat de Telegram sin que el operador intervenga.

## Estructura del repositorio

El repositorio agrupa los archivos por responsabilidad.

1. La carpeta `hermes/` contiene la configuración del agente. Incluye el archivo de personalidad SOUL.md, la skill que asocia cada consulta con su script, el trabajo programado y los archivos de configuración de ejemplo.
2. La carpeta `netops/` contiene los scripts que son las herramientas del agente.
3. La carpeta `sdn/` contiene el controlador Ryu y la topología de Mininet que se ejecutan dentro de las máquinas virtuales.
4. La carpeta `docker/` contiene los archivos para correr Hermes Agent en modo Docker.

## Dependencias

El proyecto necesita dependencias en dos entornos distintos.

En el entorno del agente, que es el portátil con WSL2, se necesita lo siguiente.

1. Hermes Agent versión 0.16.0, instalado como el paquete `hermes-agent`, o bien la imagen oficial `nousresearch/hermes-agent` si se usa el modo Docker.
2. Una cuenta y una clave de API de NVIDIA NIM. La clave es gratuita y empieza con el prefijo `nvapi-`.
3. Un bot de Telegram con su token, creado a través de BotFather.
4. Las herramientas de red que los scripts invocan, que son `ssh`, `curl`, `nc` y `python3`.

En las máquinas virtuales se necesita lo siguiente.

1. La primera máquina virtual requiere Ryu con soporte de OpenFlow 1.3 y la opción de observación de enlaces.
2. La segunda máquina virtual requiere Mininet con Open vSwitch y Python 3.
3. Cada máquina virtual dispone de dieciséis gigabytes de memoria y cuatro procesadores virtuales, según las restricciones de hardware del enunciado.

## Permisos

El proyecto maneja tres clases de permisos.

1. Permisos de acceso al repositorio. El repositorio es público, de modo que el código queda accesible de forma directa.
2. Permisos de ejecución de los archivos. Los scripts con extensión `.sh` conservan el bit de ejecución dentro del control de versiones, de modo que al clonarlos en Linux ya quedan listos para ejecutarse.
3. Permisos de actuación del agente. Las acciones de solo lectura, como consultar el estado o la salud de la red, se ejecutan de forma autónoma. Las acciones de escritura, como deshabilitar un enlace o bloquear tráfico, exigen una confirmación explícita del operador por Telegram antes de ejecutarse.

Los archivos con credenciales reales nunca entran al repositorio. El archivo `.gitignore` bloquea el archivo `.env`, el `config.yaml` real, las llaves SSH y los datos de sesión del agente. En el repositorio solo viajan las plantillas de ejemplo sin secretos.

## Configuración

El repositorio no incluye ninguna credencial. Para dejarlo operativo se siguen estos pasos.

1. Copiar el archivo `.env.example` a un archivo llamado `.env` y completar el token del bot de Telegram y la clave de API de NVIDIA.
2. Copiar el archivo `hermes/config.yaml.example` a un archivo llamado `config.yaml` y escribir la clave de API real en el campo correspondiente.
3. Copiar el archivo `netops/config.env.example` a un archivo llamado `config.env` y escribir las direcciones reales del controlador y de Mininet, junto con los umbrales de la red.

## Puesta en marcha

El arranque sigue cuatro bloques en orden. El documento `DOCUMENTACION.md` explica cada bloque en detalle y aquí aparecen los comandos esenciales.

Primero, en la máquina virtual del controlador, con la dirección 192.168.43.154, se entra por PuTTY con el usuario ryu y se inicia Ryu.

```bash
ryu-manager routing_engine_simple.py --observe-links
```

Segundo, en la máquina virtual de Mininet, con la dirección 192.168.43.65, se entra por PuTTY con el usuario mininet, se limpia la topología previa y se levanta la topología GEANT apuntando al controlador.

```bash
sudo mn -c
sudo mn --custom ~/mininet/mininet/geant_topo.py --topo geantlike --controller=remote,ip=192.168.43.154,port=6633 --switch ovs,protocols=OpenFlow13
```

Ya dentro de la consola de Mininet se inicia el servidor web del host h5 y se prueba la conectividad.

```bash
h5 python3 -m http.server 80 &
pingall
```

Tercero, en el portátil se abre PowerShell y se entra a WSL.

```powershell
wsl
```

Cuarto, en la terminal de Ubuntu se confirma la configuración y se deja corriendo la puerta de enlace de Hermes.

```bash
cat ~/netops/config.env
hermes gateway start
```

Para la variante en contenedor, el archivo `docker/README.md` explica cómo construir la imagen y levantar el agente con Docker.

## Provocar y revertir la falla

La falla de demostración se controla desde la terminal de Ubuntu. El modo on degrada un enlace de la ruta activa entre h1 y h8 y el modo off devuelve la red a su estado original.

```bash
bash ~/netops/simular_falla.sh on
bash ~/netops/simular_falla.sh off
```

Si la red queda en un estado inconsistente tras varios ensayos, el script de reparación la deja limpia.

```bash
bash ~/netops/reparar_red.sh
```

## Operación desde Telegram

El agente se opera escribiendo en el chat de Telegram. Estas frases recorren todas sus capacidades en el orden de una demostración completa.

1. **¿Cuál es el estado de la red?** El agente muestra switches, enlaces, hosts y rutas activas.
2. **Revisa la salud de la red, ¿hay alguna falla?** El agente reporta la incidencia real.
3. **Haz un ping de h1 a h8.** El agente mide la latencia y la pérdida reales.
4. **Diagnostica y aplica la política de enrutamiento alternativo.** El agente pide autorización y, tras responder **si,** deshabilita el enlace degradado y verifica la recuperación.
5. **¿Cómo está la red ahora?** El agente confirma que la red quedó operativa.
6. **Bloquea el tráfico entre h3 y h8.** El agente pide autorización y, tras responder **si,** bloquea el tráfico en ambos sentidos.
7. **Haz un ping de h3 a h8.** El agente reporta una pérdida del cien por cien.
8. **Desbloquea el tráfico entre h3 y h8.** El agente revierte el bloqueo.

El monitoreo proactivo no requiere escribir nada. El trabajo programado publica la alerta por sí mismo cuando detecta una incidencia.


