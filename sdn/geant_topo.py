#!/usr/bin/python3
"""
geant_topo.py — Topología inspirada en GEANT (Europa)
======================================================
Versión ampliada: 10 switches, 8 hosts, múltiples bucles.

Mapa lógico (nodos = ciudades GEANT aproximadas):
  s1  = Amsterdam (hub principal)
  s2  = Londres
  s3  = París
  s4  = Frankfurt
  s5  = Milán
  s6  = Madrid
  s7  = Viena
  s8  = Praga
  s9  = Varsovia
  s10 = Estocolmo

Hosts (uno por switch en los 8 primeros):
  h1 → s1,  h2 → s2,  h3 → s3,  h4 → s4
  h5 → s5,  h6 → s6,  h7 → s7,  h8 → s8

Cambios respecto a la versión anterior:
  - De 6 a 10 switches: más nodos intermedios, rutas más largas.
  - De 6 a 8 hosts: más pares src/dst posibles para probar routing.
  - De 3 enlaces cruzados a 7: mayor redundancia y más caminos alternativos
    para que Dijkstra tenga opciones reales que explorar.
  - Se añaden nodos s9 y s10 sin host propio (routers de tránsito puros),
    igual que en la red GEANT real donde no todos los nodos tienen usuarios finales.

Compatibilidad con routing_engineV2.py:
  - No se cambia ninguna convención de nombres (sN, hN).
  - No se agregan parámetros a addLink ni a addHost.
  - El controlador descubre la topología dinámicamente via LLDP,
    por lo que cualquier cambio en el grafo es invisible para él
    (lo aprende solo al arrancar).
  - Los pesos de Dijkstra siguen siendo 1 por defecto (el controlador
    los asigna en update_topology, no aquí).
"""

from mininet.topo import Topo


class GeantLikeTopo(Topo):
    def build(self):

        # ----------------------------------------------------------
        # Switches (10 nodos — núcleo tipo MESH con bucles)
        # ----------------------------------------------------------
        s1  = self.addSwitch('s1')   # Amsterdam   — hub principal
        s2  = self.addSwitch('s2')   # Londres
        s3  = self.addSwitch('s3')   # París
        s4  = self.addSwitch('s4')   # Frankfurt
        s5  = self.addSwitch('s5')   # Milán
        s6  = self.addSwitch('s6')   # Madrid
        s7  = self.addSwitch('s7')   # Viena
        s8  = self.addSwitch('s8')   # Praga
        s9  = self.addSwitch('s9')   # Varsovia    — nodo de tránsito
        s10 = self.addSwitch('s10')  # Estocolmo   — nodo de tránsito

        # ----------------------------------------------------------
        # Hosts (8 hosts, uno por los primeros 8 switches)
        # s9 y s10 son routers de tránsito sin host local
        # ----------------------------------------------------------
        h1 = self.addHost('h1')   # en Amsterdam
        h2 = self.addHost('h2')   # en Londres
        h3 = self.addHost('h3')   # en París
        h4 = self.addHost('h4')   # en Frankfurt
        h5 = self.addHost('h5')   # en Milán
        h6 = self.addHost('h6')   # en Madrid
        h7 = self.addHost('h7')   # en Viena
        h8 = self.addHost('h8')   # en Praga

        # ----------------------------------------------------------
        # Hosts a sus switches de acceso
        # ----------------------------------------------------------
        self.addLink(h1, s1)
        self.addLink(h2, s2)
        self.addLink(h3, s3)
        self.addLink(h4, s4)
        self.addLink(h5, s5)
        self.addLink(h6, s6)
        self.addLink(h7, s7)
        self.addLink(h8, s8)

        # ----------------------------------------------------------
        # Enlace del anillo principal (Europa Occidental → Central → Norte)
        # s1 — s2 — s3 — s4 — s7 — s8 — s9 — s10 — s1
        # ----------------------------------------------------------
        self.addLink(s1, s2)    # Amsterdam — Londres
        self.addLink(s2, s3)    # Londres   — París
        self.addLink(s3, s4)    # París     — Frankfurt
        self.addLink(s4, s7)    # Frankfurt — Viena
        self.addLink(s7, s8)    # Viena     — Praga
        self.addLink(s8, s9)    # Praga     — Varsovia
        self.addLink(s9, s10)   # Varsovia  — Estocolmo
        self.addLink(s10, s1)   # Estocolmo — Amsterdam  (cierra el anillo)

        # ----------------------------------------------------------
        # Enlaces cruzados (diagonales GEANT — generan bucles adicionales)
        # Aumentan la redundancia y dan a Dijkstra caminos alternativos reales
        # ----------------------------------------------------------
        self.addLink(s1, s4)    # Amsterdam — Frankfurt  (eje central)
        self.addLink(s1, s6)    # Amsterdam — Madrid     (corredor ibérico)
        self.addLink(s3, s6)    # París     — Madrid
        self.addLink(s3, s5)    # París     — Milán      (corredor mediterráneo)
        self.addLink(s4, s5)    # Frankfurt — Milán
        self.addLink(s5, s8)    # Milán     — Praga      (diagonal sureste)
        self.addLink(s2, s10)   # Londres   — Estocolmo  (corredor nórdico)


topos = {'geantlike': GeantLikeTopo}
