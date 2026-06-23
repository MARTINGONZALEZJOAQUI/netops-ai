# Documentación del proyecto NetOps AI

Este documento reúne la descripción completa de lo realizado en el proyecto. Cubre el objetivo, las decisiones técnicas, la arquitectura de despliegue, las máquinas involucradas, el inventario de archivos, los flujos de operación, el modo Docker, el manejo de la seguridad y el cumplimiento de cada requisito del enunciado.

## Objetivo del proyecto

El proyecto implementa un agente de inteligencia artificial que cumple el papel de un administrador de red de nivel 1 y 2. El agente se opera por completo desde Telegram. Vigila de forma permanente una red definida por software, avisa de las incidencias antes de que el operador las note y, cuando recibe la orden, diagnostica la falla y aplica una política de enrutamiento alternativo que devuelve la red a un estado sano. El proyecto corresponde a la Opción 1 del microproyecto, llamada NetOps AI, y se construye sobre el framework Hermes Agent.

## Decisión técnica sobre el modelo de lenguaje

El enunciado plantea como arquitectura ideal correr un modelo cuantizado de forma local con Ollama. Durante la implementación se comprobó que la tarjeta gráfica del portátil dispone de ocho gigabytes de memoria de video, una cantidad que no alcanza para sostener un modelo con la capacidad de razonamiento y de uso de herramientas que el agente necesita. Se probaron varios modelos locales de la familia de siete y ocho mil millones de parámetros y todos fallaban al manejar el prompt completo del framework, ya fuera quedándose sin respuesta o inventando datos.

La solución fue mover el modelo a la nube mediante NVIDIA NIM, que ofrece un punto de acceso compatible con el estándar de OpenAI y una capa gratuita suficiente para el proyecto. El modelo elegido es meta/llama-3.3-70b-instruct, que soporta el uso de herramientas de forma fiable. La arquitectura del agente no cambió. Lo único que cambió fue el lugar donde se ejecuta el modelo, que pasó del portátil a la nube. Esta decisión queda documentada de forma transparente porque respeta el espíritu del enunciado y resuelve una restricción real de hardware.

## Arquitectura de despliegue

El sistema se despliega sobre tres máquinas conectadas por la misma red local.

### Máquina uno. El portátil con WSL2

El portátil ejecuta Windows y, dentro de él, el subsistema WSL2 con Ubuntu. En ese Ubuntu corre el framework Hermes Agent, que mantiene la conexión con Telegram, razona con el modelo de la nube y ejecuta las herramientas. En el mismo entorno viven los scripts de la carpeta de trabajo del agente y el trabajo programado que revisa la red cada cinco minutos. El portátil es el cerebro del sistema y el único punto desde el que el operador interactúa, siempre a través de Telegram.

### Máquina dos. La máquina virtual del controlador Ryu

La primera máquina virtual tiene la dirección 192.168.43.154 y ejecuta el controlador Ryu. El controlador conoce la topología completa, calcula las rutas con el algoritmo de Dijkstra y programa los switches mediante OpenFlow 1.3. También expone una interfaz REST en el puerto 8080 que permite consultar la topología y las rutas activas y aplicar políticas como deshabilitar un enlace o bloquear el tráfico entre dos hosts. Los scripts del agente hablan con esta interfaz mediante peticiones HTTP.

### Máquina tres. La máquina virtual de Mininet

La segunda máquina virtual tiene la dirección 192.168.43.65 y ejecuta Mininet. Mininet emula la topología GEANT, que contiene diez switches, ocho hosts y quince enlaces. El host crítico h5 levanta un servidor web que escucha en el puerto 80 y que cumple el papel del servicio vigilado por el trabajo programado. El agente entra a esta máquina por SSH para medir la conectividad real entre hosts y para comprobar si el servidor web responde.

### Comunicación entre las máquinas

El flujo de comunicación sigue un recorrido claro. El operador escribe en Telegram y su mensaje llega al agente que corre en el portátil. El agente decide qué herramienta usar y ejecuta el script correspondiente. El script consulta al controlador Ryu por HTTP cuando necesita información de topología o aplicar una política, y entra por SSH a la máquina de Mininet cuando necesita medir conectividad real o el estado del servidor web. Los switches de Mininet, a su vez, obedecen al controlador Ryu mediante OpenFlow. La respuesta del script vuelve al agente, el agente la interpreta con el modelo de la nube y publica una respuesta en español en el chat de Telegram.

## Inventario de archivos

El repositorio organiza los archivos en cuatro carpetas según su responsabilidad.

### Carpeta netops

Esta carpeta contiene los scripts que son las herramientas del agente.

| Archivo | Función |
|---|---|
| revisar_salud.sh | Revisa el número de enlaces, mide la pérdida entre los hosts h1 y h8 y comprueba el servidor web del host h5 |
| estado_red.sh | Muestra los switches, los enlaces, los hosts conocidos y las rutas activas |
| probar_conexion.sh | Mide la conectividad y la pérdida de paquetes entre dos hosts |
| arreglar_sdn.sh | Identifica el enlace troncal degradado, aplica la política de ruta alternativa y verifica la recuperación |
| controlar_enlace.sh | Habilita o deshabilita un enlace en el controlador |
| bloquear_trafico.sh | Bloquea el tráfico entre dos hosts en ambos sentidos |
| desbloquear_trafico.sh | Revierte el bloqueo entre dos hosts |
| simular_falla.sh | Provoca o limpia la falla de demostración degradando un enlace de la ruta activa |
| reparar_red.sh | Devuelve la red a un estado limpio y operativo |
| config.env.example | Plantilla con las direcciones del controlador y de Mininet y los umbrales de la red |

### Carpeta hermes

Esta carpeta contiene la configuración del agente.

| Archivo | Función |
|---|---|
| SOUL.md | Define la personalidad, las reglas y los límites del agente |
| skills/netops/DESCRIPTION.md | Asocia cada tipo de consulta del operador con el script que la resuelve |
| cron/jobs.json | Define el trabajo programado que se ejecuta cada cinco minutos |
| cron/scripts/monitoreo_automatico.sh | Es el script que ejecuta el trabajo programado y que arma el mensaje de alerta |
| config.yaml.example | Plantilla de configuración de Hermes con el modelo y el proveedor, sin la clave real |

### Carpeta sdn

Esta carpeta contiene el software que corre dentro de las máquinas virtuales.

| Archivo | Función |
|---|---|
| routing_engine_simple.py | Controlador Ryu con enrutamiento por Dijkstra y la interfaz REST de políticas |
| geant_topo.py | Definición de la topología GEANT que levanta Mininet |

### Carpeta docker

Esta carpeta contiene los archivos para correr el agente en modo Docker.

| Archivo | Función |
|---|---|
| Dockerfile | Parte de la imagen oficial de Hermes y le añade las herramientas de red ssh, curl y nc |
| docker-compose.yml | Levanta el agente montando la configuración, los scripts y la llave SSH |
| README.md | Explica cómo instalar Docker, construir la imagen y levantar el agente |

## Flujo de monitoreo proactivo

El monitoreo proactivo cumple el requisito de revisar un servicio cada cinco minutos. El trabajo programado de Hermes ejecuta el script de monitoreo en ese intervalo. El script de monitoreo llama al script de revisión de salud, que realiza tres comprobaciones. Primero consulta al controlador el número de enlaces activos y lo compara con el número esperado de quince. Segundo entra por SSH a Mininet y mide la pérdida de paquetes entre los hosts h1 y h8 con una serie de pings. Tercero comprueba si el servidor web del host h5 responde en el puerto 80. Si cualquiera de las tres comprobaciones encuentra un problema, el script de monitoreo arma un mensaje de alerta y el agente lo publica en el chat de Telegram sin que el operador haya escrito nada.

## Flujo de diagnóstico y corrección

El flujo de corrección es la parte central del agente. Cuando el operador pide diagnosticar y aplicar la política de enrutamiento alternativo, el agente primero revisa la salud y confirma el problema. Luego solicita una autorización explícita porque va a ejecutar una acción de escritura. Cuando el operador confirma, el agente ejecuta el script de arreglo. Ese script lee el enlace exacto que quedó degradado, que el script de simulación había anotado en un archivo de estado, y lo deshabilita en el controlador mediante la interfaz REST. El controlador recalcula las rutas con Dijkstra y desvía el tráfico por un camino sano. El script verifica con una nueva medición de pérdida que la red se recuperó y el agente informa el resultado. Como evidencia cruzada, en el registro del controlador Ryu aparece la línea que indica el enlace deshabilitado por política y las líneas de recálculo de rutas.

El uso de un archivo de estado para recordar el enlace degradado resolvió un problema real. La ruta entre los hosts h1 y h8 tiene dos caminos de igual costo y el controlador alternaba entre ellos, lo que antes provocaba que la corrección deshabilitara el enlace equivocado. Al fijar el enlace degradado en un archivo, la corrección actúa siempre sobre el enlace correcto.

## Modo Docker

Se debía configurar Hermes Agent en modo Docker para aislar la ejecución de comandos. La carpeta docker cumple ese requisito. La imagen oficial de Hermes ya trae el framework instalado y monta toda la configuración del usuario en un único volumen. Como los scripts del agente necesitan las herramientas de red ssh, curl y nc, que la imagen oficial no incluye, el Dockerfile parte de la imagen oficial y las instala en una capa delgada. El archivo de composición levanta el agente usando la red del anfitrión, de modo que el contenedor alcanza las dos máquinas virtuales igual que lo hace el entorno nativo, y monta la configuración, los scripts y la llave SSH. El archivo README de la carpeta docker contiene el procedimiento paso a paso para instalar Docker en WSL, parar el gateway nativo, construir la imagen y verificar que el contenedor funciona.

## Despliegue paso a paso

El arranque del entorno completo sigue cuatro bloques en orden. Cada bloque indica la máquina, cómo se entra a ella y los comandos exactos.

### Bloque uno. Controlador Ryu en la máquina 192.168.43.154

Se entra a la máquina por PuTTY con el usuario ryu y se inicia el controlador. Esa sesión se mantiene abierta durante toda la demostración.

```bash
ryu-manager routing_engine_simple.py --observe-links
```

El controlador queda escuchando OpenFlow en el puerto 6633 y expone su interfaz REST en el puerto 8080.

### Bloque dos. Mininet en la máquina 192.168.43.65

Se entra a la máquina por PuTTY con el usuario mininet. Primero se limpia cualquier topología previa y luego se levanta la topología GEANT apuntando al controlador en su dirección actual.

```bash
sudo mn -c
sudo mn --custom ~/mininet/mininet/geant_topo.py --topo geantlike --controller=remote,ip=192.168.43.154,port=6633 --switch ovs,protocols=OpenFlow13
```

Cuando aparece el indicador de la consola de Mininet, que es `mininet>`, se inicia el servidor web del host crítico h5 y se comprueba la conectividad general.

```bash
h5 python3 -m http.server 80 &
pingall
```

El servidor web de h5 es el servicio que vigila el trabajo programado. La prueba de pings deja las rutas aprendidas en los switches.

### Bloque tres. Activación de WSL en el portátil

En el portátil se abre PowerShell y se entra al subsistema de Linux con Ubuntu.

```powershell
wsl
```

Si hay varias distribuciones instaladas se indica la deseada de forma explícita.

```powershell
wsl -d Ubuntu
```

### Bloque cuatro. Agente Hermes en WSL

Ya en la terminal de Ubuntu se confirma que el archivo de configuración tiene las direcciones actuales del controlador y de Mininet, y luego se deja corriendo la puerta de enlace de Hermes en una ventana que se mantiene abierta.

```bash
cat ~/netops/config.env
hermes gateway start
```

Desde este momento el agente ya responde por Telegram.

## Provocar y revertir la falla de demostración

La falla se controla con un único script desde la terminal de Ubuntu.

Para provocar la falla, que degrada un enlace de la ruta activa entre los hosts h1 y h8 y eleva la pérdida de paquetes por encima del umbral del quince por ciento, se usa el modo on.

```bash
bash ~/netops/simular_falla.sh on
```

Para devolver la red a su estado original, que retira la degradación, rehabilita los enlaces, quita cualquier bloqueo y vuelve a aprender las rutas, se usa el modo off.

```bash
bash ~/netops/simular_falla.sh off
```

Si tras varios ensayos la red queda en un estado inconsistente, el script de reparación la deja completamente limpia y operativa.

```bash
bash ~/netops/reparar_red.sh
```

## Preguntas para el bot de Telegram

La operación normal del agente se hace escribiendo en el chat de Telegram. Estas son las frases que recorren todas las capacidades del agente, en el orden de una demostración completa. El agente muestra primero una tarjeta con el comando que ejecuta y debajo su respuesta en español con los datos reales.

1. Para conocer el estado general se escribe la frase **¿Cuál es el estado de la red?** El agente responde con el número de switches, enlaces y hosts y con las rutas activas.
2. Para revisar la salud se escribe la frase **Revisa la salud de la red, ¿hay alguna falla?** El agente reporta la incidencia real, con la pérdida de paquetes entre h1 y h8 por encima del umbral.
3. Para medir conectividad se escribe la frase **Haz un ping de h1 a h8.** El agente responde con la latencia y la pérdida reales.
4. Para diagnosticar y reparar se escribe la frase **Diagnostica y aplica la política de enrutamiento alternativo.** El agente confirma el problema y pide autorización. Para autorizar se responde la palabra **si.** El agente deshabilita el enlace degradado, deja que Dijkstra recalcule las rutas y verifica que la pérdida baja hasta cero.
5. Para verificar la recuperación se escribe la frase **¿Cómo está la red ahora?** El agente confirma que la red quedó operativa con sus quince enlaces.
6. Para bloquear tráfico se escribe la frase **Bloquea el tráfico entre h3 y h8.** El agente pide autorización y, tras la respuesta **si,** bloquea el tráfico en ambos sentidos.
7. Para comprobar el bloqueo se escribe la frase **Haz un ping de h3 a h8.** El agente reporta una pérdida del cien por cien.
8. Para revertir el bloqueo se escribe la frase **Desbloquea el tráfico entre h3 y h8.**

Para el monitoreo proactivo no se escribe nada. Basta con esperar a que el trabajo programado se ejecute y publique la alerta por sí mismo.

## Comandos manuales de los scripts

Cada herramienta del agente también se puede ejecutar a mano desde la terminal de Ubuntu, lo que sirve para depurar sin pasar por Telegram. Todos los scripts viven en la carpeta de trabajo del agente.

```bash
bash ~/netops/estado_red.sh
bash ~/netops/revisar_salud.sh
bash ~/netops/probar_conexion.sh h1 h8
bash ~/netops/arreglar_sdn.sh
bash ~/netops/controlar_enlace.sh disable 4 7
bash ~/netops/controlar_enlace.sh enable 4 7
bash ~/netops/bloquear_trafico.sh h3 h8
bash ~/netops/desbloquear_trafico.sh h3 h8
bash ~/netops/simular_falla.sh on
bash ~/netops/simular_falla.sh off
bash ~/netops/reparar_red.sh
```

El script de control de enlace recibe la acción y los dos números de switch del enlace. El script de prueba de conectividad y los de bloqueo reciben los dos hosts, que se escriben con el formato hN o con su dirección IP.

## Variante en modo Docker

Como alternativa al arranque nativo del bloque cuatro, el agente se puede levantar en un contenedor. El procedimiento completo está en el archivo README de la carpeta docker. El resumen de comandos es el siguiente.

```bash
hermes gateway stop
cd docker
docker compose up -d --build
docker logs -f hermes
```

El primer comando para el gateway nativo para que los dos procesos no choquen contra el mismo bot de Telegram. El resto construye la imagen y levanta el agente en segundo plano.

## Seguridad y manejo de secretos

El proyecto trata las credenciales con cuidado porque el repositorio es público. El token del bot de Telegram y la clave de API de NVIDIA nunca entran al control de versiones. El repositorio solo contiene plantillas de ejemplo con los campos vacíos. El archivo de exclusión bloquea el archivo de variables de entorno real, el archivo de configuración real con la clave, las llaves SSH y los datos de sesión del agente. Antes de publicar se realizó un escaneo del contenido que confirmó la ausencia de cualquier secreto. 

## Cumplimiento de los requisitos 

El proyecto cubre cada uno de los siguientes requerimientos

1. El entorno del agente usa Hermes Agent y ofrece la variante en modo Docker para aislar la ejecución de comandos.
2. Las herramientas del agente son scripts que ejecutan comandos de red, consultan la topología y aplican políticas sobre el controlador.
3. El trabajo programado nativo de Hermes revisa el estado de un servicio, que es el servidor web del host h5, cada cinco minutos.
4. El flujo por Telegram envía una alerta proactiva cuando aparece una incidencia, como la pérdida de paquetes por encima del umbral.
5. El operador responde por Telegram y el agente diagnostica el problema, cambia el enrutamiento aplicando una política alternativa y notifica el éxito o el fracaso de la tarea.
