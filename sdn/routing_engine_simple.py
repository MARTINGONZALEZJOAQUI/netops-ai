"""
routing_engine_simple.py - Controlador SDN SIN ML (para NetOps AI)
==================================================================
Version simplificada de routing_engineV3.py. Se elimina por completo la
parte de Machine Learning (XGBoost, captura de features, clasificacion de
trafico, votacion y re-ruteo por clase). Conserva lo que el agente NetOps AI
necesita y agrega re-ruteo automatico ante caida/recuperacion de enlaces.

QUE CONSERVA:
  - Enrutamiento L3 proactivo con Dijkstra (peso base 1 + penalizacion por carga).
  - ARP proxy (conectividad sin tormentas de broadcast en la malla GEANT).
  - Instalacion de flows bidireccionales (solo OUTPUT, sin espejo al controlador).
  - Re-ruteo AUTOMATICO cuando un enlace se cae o se recupera (via LLDP).
  - REST API Northbound (puerto 8080):
      GET  /sdn/topology    switches, enlaces, hosts, carga por enlace
      GET  /sdn/flows       pares activos (origen, destino, ruta)
      GET  /sdn/blocked     pares IP bloqueados
      POST /sdn/block       {"src_ip": "...", "dst_ip": "..."}  -> instala DROP
      POST /sdn/unblock     {"src_ip": "...", "dst_ip": "..."}  -> elimina DROP
      GET  /sdn/weights     (compatibilidad: devuelve {} )

QUE ELIMINA respecto a V3:
  - import numpy / xgboost y la carga de xgb_model.json/scaler/meta.
  - _compute_features, _classify, captura de iat/jitter/throughput.
  - Logica de re-ruteo por votacion de clase ML (PENDING, REROUTE_VOTE_*).
  - Accion dual OUTPUT(CONTROLLER) en cada flow (ya no se espeja trafico).

Arranque (VM Ryu):
  source ~/ryu-env/bin/activate
  cd ~/lastwork
  ryu-manager routing_engine_simple.py --observe-links

--observe-links es OBLIGATORIO: activa el modulo LLDP para descubrir la
topologia. Sin el, self.graph queda vacio y Dijkstra devuelve [].
"""

import json
import time

from ryu.base import app_manager
from ryu.controller import ofp_event
from ryu.controller.handler import (MAIN_DISPATCHER, DEAD_DISPATCHER,
                                     CONFIG_DISPATCHER, set_ev_cls)
from ryu.topology import event
from ryu.topology.api import get_switch, get_link
from ryu.ofproto import ofproto_v1_3
from ryu.lib.packet import packet, ethernet, ether_types, arp, ipv4

from ryu.app.wsgi import ControllerBase, WSGIApplication, route, Response

# ---------------------------------------------------------------------------
# Constantes
# ---------------------------------------------------------------------------

FLOW_PRIORITY   = 10
TABLE_MISS_PRIO = 0
DROP_PRIO       = 100
BLOCK_PRIORITY  = 50    # DROP de bloqueo: prioridad > flows de ruteo (10)

# Cookie propio de los flows de enrutamiento. Permite borrar SOLO nuestras
# rutas al reconectar (sin tocar los flows LLDP del modulo de topologia de Ryu).
ROUTING_COOKIE  = 0x1010

LINK_LOAD_ALPHA = 0.3   # penaliza enlaces con muchos flujos activos
BASE_WEIGHT     = 1     # peso base de cada enlace (sin clases ML)

_APP_NAME = 'sdn_controller_simple'


# ==============================================================================
# CONTROLADOR PRINCIPAL
# ==============================================================================

class SDNController(app_manager.RyuApp):

    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]
    _CONTEXTS = {'wsgi': WSGIApplication}

    def __init__(self, *args, **kwargs):
        super(SDNController, self).__init__(*args, **kwargs)

        # Topologia
        self.graph      = {}
        self.prev_graph = {}
        self.datapaths  = {}
        self.hosts      = {}     # mac -> (dpid, port)
        self.ip_to_mac  = {}     # ip  -> mac
        self.mac_to_ip  = {}     # mac -> ip

        # ARP proxy
        self.pending_arp = {}
        self.seen_arp    = set()

        # Rutas instaladas (granularidad par MAC)
        self.mac_pair_path = {}  # (src_mac, dst_mac) -> [dpid, ...]
        self.link_flows    = {}  # (a, b) -> nro de flujos activos

        # Bloqueo
        self.blocked_pairs = set()

        # Politica de enrutamiento: enlaces deshabilitados (frozenset({a, b}))
        self.disabled_links = set()

        wsgi = kwargs['wsgi']
        wsgi.register(SDNRestAPI, {_APP_NAME: self})

        self.logger.info("=" * 60)
        self.logger.info("[INIT] Controlador SDN SIMPLE (sin ML) iniciado")
        self.logger.info("[INIT] REST API en puerto 8080  (/sdn/*)")
        self.logger.info("=" * 60)

    # =========================================================================
    # TOPOLOGIA  (+ re-ruteo automatico ante cambios de enlace)
    # =========================================================================

    @set_ev_cls(event.EventSwitchEnter)
    @set_ev_cls(event.EventSwitchLeave)
    @set_ev_cls(event.EventLinkAdd)
    @set_ev_cls(event.EventLinkDelete)
    def update_topology_handler(self, ev):
        self.update_topology()

    def update_topology(self):
        new_graph = {}
        for sw in get_switch(self, None):
            new_graph[sw.dp.id] = {"neighbors": {}}
        for link in get_link(self, None):
            s, d = link.src, link.dst
            new_graph[s.dpid]["neighbors"][d.dpid] = {"port": s.port_no, "weight": BASE_WEIGHT}
            new_graph[d.dpid]["neighbors"][s.dpid] = {"port": d.port_no, "weight": BASE_WEIGHT}

        if new_graph != self.prev_graph:
            self.logger.info("[TOPO] %d switches, %d enlaces",
                             len(new_graph),
                             sum(len(v["neighbors"]) for v in new_graph.values()) // 2)
            changed = bool(self.prev_graph)  # no re-rutear en el arranque inicial
            self.prev_graph = new_graph
            self.graph = new_graph
            if changed and self.mac_pair_path:
                self._reroute_known_pairs()
        else:
            self.graph = new_graph

    def _reroute_known_pairs(self):
        """Recalcula la ruta de cada par MAC conocido tras un cambio de topologia.
        Esto hace que al caer un enlace, los pares afectados tomen automaticamente
        la ruta alternativa (escenario clave de la demo NetOps)."""
        self.logger.info("[REROUTE] Cambio de topologia -> recalculando rutas")
        seen = set()
        for (a, b) in list(self.mac_pair_path.keys()):
            key = tuple(sorted([a, b]))
            if key in seen:
                continue
            seen.add(key)
            self._reinstall_pair(a, b)

    def _reinstall_pair(self, src_mac, dst_mac):
        if src_mac not in self.hosts or dst_mac not in self.hosts:
            return
        src_dpid, src_port = self.hosts[src_mac]
        dst_dpid, dst_port = self.hosts[dst_mac]

        new_path = self.dijkstra(src_dpid, dst_dpid)
        old_path = self.mac_pair_path.get((src_mac, dst_mac))

        if not new_path:
            self.logger.warning("[REROUTE] Sin ruta %s -> %s (par aislado)",
                                src_mac, dst_mac)
            return
        if new_path == old_path:
            return

        if old_path:
            self._update_link_loads(old_path, delta=-1)
        self._delete_pair_flows(src_mac, dst_mac)
        self._install_bidirectional_flows(new_path, src_mac, dst_mac,
                                          src_port, dst_port)
        self._update_link_loads(new_path, delta=+1)

        self.mac_pair_path[(src_mac, dst_mac)] = new_path
        self.mac_pair_path[(dst_mac, src_mac)] = list(reversed(new_path))

        self.logger.info("[REROUTE] %s -> %s   ruta %s => %s",
                         src_mac, dst_mac, old_path, new_path)

    # =========================================================================
    # DIJKSTRA  (peso base 1 + penalizacion por carga)
    # =========================================================================

    def dijkstra(self, src, dst):
        if src == dst:
            return [src]
        if src not in self.graph or dst not in self.graph:
            return []

        unvisited = set(self.graph.keys())
        distances = {n: float('inf') for n in self.graph}
        previous  = {}
        distances[src] = 0.0

        while unvisited:
            current = min(unvisited, key=lambda n: distances[n])
            if distances[current] == float('inf'):
                break
            unvisited.remove(current)
            if current == dst:
                break
            for neighbor, data in self.graph[current]["neighbors"].items():
                if frozenset((current, neighbor)) in self.disabled_links:
                    continue   # enlace deshabilitado por politica -> Dijkstra lo evita
                load = self.link_flows.get((current, neighbor), 0)
                link_cost = data["weight"] * (1.0 + LINK_LOAD_ALPHA * load)
                alt = distances[current] + link_cost
                if alt < distances[neighbor]:
                    distances[neighbor] = alt
                    previous[neighbor]  = current

        if dst not in previous and src != dst:
            return []

        path, node = [], dst
        while node in previous:
            path.insert(0, node)
            node = previous[node]
        path.insert(0, src)
        return path

    # =========================================================================
    # DATAPATHS
    # =========================================================================

    @set_ev_cls(ofp_event.EventOFPStateChange, [MAIN_DISPATCHER, DEAD_DISPATCHER])
    def state_change_handler(self, ev):
        dp = ev.datapath
        if ev.state == MAIN_DISPATCHER:
            self.datapaths[dp.id] = dp
            self.logger.info("[DP] Switch %s conectado", dp.id)
        elif ev.state == DEAD_DISPATCHER:
            self.datapaths.pop(dp.id, None)
            self.logger.info("[DP] Switch %s desconectado", dp.id)

    @set_ev_cls(ofp_event.EventOFPSwitchFeatures, CONFIG_DISPATCHER)
    def switch_features_handler(self, ev):
        dp      = ev.msg.datapath
        parser  = dp.ofproto_parser
        ofproto = dp.ofproto

        self.logger.info("[INIT] Configurando switch %s", dp.id)

        # Limpieza al (re)conectar: borra SOLO los flows de enrutamiento
        # residuales (cookie ROUTING_COOKIE) de una ejecucion anterior del
        # controlador. Sin esto, tras reiniciar el controlador los switches
        # conservan rutas viejas que el controlador ya no tiene en memoria
        # (mac_pair_path vacio) y el re-ruteo por politica no las recalcula.
        # Filtrar por cookie evita borrar los flows LLDP que instala el modulo
        # de topologia de Ryu (--observe-links), preservando el descubrimiento.
        dp.send_msg(parser.OFPFlowMod(
            datapath=dp, command=ofproto.OFPFC_DELETE,
            cookie=ROUTING_COOKIE, cookie_mask=0xFFFFFFFFFFFFFFFF,
            out_port=ofproto.OFPP_ANY, out_group=ofproto.OFPG_ANY,
            match=parser.OFPMatch()))

        self._add_flow(dp, DROP_PRIO,
                       parser.OFPMatch(eth_type=ether_types.ETH_TYPE_LLDP), [])
        self._add_flow(dp, DROP_PRIO,
                       parser.OFPMatch(eth_type=ether_types.ETH_TYPE_IPV6), [])
        self._add_flow(dp, TABLE_MISS_PRIO,
                       parser.OFPMatch(),
                       [parser.OFPActionOutput(ofproto.OFPP_CONTROLLER,
                                               ofproto.OFPCML_NO_BUFFER)])

    # =========================================================================
    # PACKET-IN
    # =========================================================================

    @set_ev_cls(ofp_event.EventOFPPacketIn, MAIN_DISPATCHER)
    def packet_in_handler(self, ev):
        msg     = ev.msg
        dp      = msg.datapath
        dpid    = dp.id
        in_port = msg.match['in_port']

        pkt = packet.Packet(msg.data)
        eth = pkt.get_protocol(ethernet.ethernet)
        if eth is None:
            return

        eth_type = eth.ethertype
        if eth_type in (ether_types.ETH_TYPE_LLDP, ether_types.ETH_TYPE_IPV6):
            return

        src_mac = eth.src
        dst_mac = eth.dst

        if self._is_host_port(dpid, in_port):
            if src_mac not in self.hosts:
                self.logger.info("[LEARN] Host %s en sw%s p%s", src_mac, dpid, in_port)
            self.hosts[src_mac] = (dpid, in_port)

        arp_pkt = pkt.get_protocol(arp.arp)
        if arp_pkt:
            self._handle_arp(dp, in_port, eth, arp_pkt, msg)
            return

        ip_pkt = pkt.get_protocol(ipv4.ipv4)
        if ip_pkt:
            self._handle_ipv4(dp, in_port, src_mac, dst_mac, ip_pkt, msg)
            return

    # =========================================================================
    # MANEJO IPv4  (solo primer paquete: calcula ruta e instala flows)
    # =========================================================================

    def _handle_ipv4(self, dp, in_port, src_mac, dst_mac, ip_pkt, msg):
        dpid    = dp.id
        ofproto = dp.ofproto
        parser  = dp.ofproto_parser

        if dst_mac not in self.hosts:
            self.logger.warning("[IPv4] MAC destino %s desconocida", dst_mac)
            return
        if src_mac not in self.hosts:
            self.logger.warning("[IPv4] MAC origen %s desconocida", src_mac)
            return

        # Si el par ya tiene ruta, no recalcular (el flow ya esta instalado;
        # este packet-in es residual). Solo reenviar.
        if (src_mac, dst_mac) not in self.mac_pair_path:
            src_dpid, src_host_port = self.hosts[src_mac]
            dst_dpid, dst_host_port = self.hosts[dst_mac]

            path = self.dijkstra(src_dpid, dst_dpid)
            if not path:
                self.logger.warning("[IPv4] Sin ruta sw%s -> sw%s",
                                    src_dpid, dst_dpid)
                return

            self.logger.info("[ROUTE] %s -> %s   path=%s", src_mac, dst_mac, path)

            self._update_link_loads(path, delta=+1)
            self.mac_pair_path[(src_mac, dst_mac)] = path
            self.mac_pair_path[(dst_mac, src_mac)] = list(reversed(path))
            self._install_bidirectional_flows(
                path, src_mac, dst_mac, src_host_port, dst_host_port)

        path = self.mac_pair_path[(src_mac, dst_mac)]
        dst_dpid, dst_host_port = self.hosts[dst_mac]
        out_port = self._get_out_port_for_dpid(dpid, path, dst_host_port)
        if out_port is None:
            return

        actions = [parser.OFPActionOutput(out_port)]
        data    = msg.data if msg.buffer_id == ofproto.OFP_NO_BUFFER else None
        out = parser.OFPPacketOut(
            datapath=dp, buffer_id=msg.buffer_id,
            in_port=in_port, actions=actions, data=data)
        dp.send_msg(out)

    # =========================================================================
    # CARGA DE ENLACES
    # =========================================================================

    def _update_link_loads(self, path, delta):
        for i in range(len(path) - 1):
            a, b = path[i], path[i + 1]
            self.link_flows[(a, b)] = max(0, self.link_flows.get((a, b), 0) + delta)
            self.link_flows[(b, a)] = max(0, self.link_flows.get((b, a), 0) + delta)

    # =========================================================================
    # INSTALACION / BORRADO DE FLOWS
    # =========================================================================

    def _install_bidirectional_flows(self, path, src_mac, dst_mac,
                                     src_port, dst_port):
        n = len(path)
        for i, sw in enumerate(path):
            if sw not in self.datapaths:
                self.logger.warning("[FLOW] sw%s no disponible, saltando", sw)
                continue

            dp     = self.datapaths[sw]
            parser = dp.ofproto_parser

            fwd_out = dst_port if i == n - 1 else self.graph[sw]["neighbors"][path[i+1]]["port"]
            rev_out = src_port if i == 0     else self.graph[sw]["neighbors"][path[i-1]]["port"]

            self._add_flow(dp, FLOW_PRIORITY,
                           parser.OFPMatch(eth_src=src_mac, eth_dst=dst_mac),
                           [parser.OFPActionOutput(fwd_out)],
                           idle_timeout=0, hard_timeout=0, cookie=ROUTING_COOKIE)
            self._add_flow(dp, FLOW_PRIORITY,
                           parser.OFPMatch(eth_src=dst_mac, eth_dst=src_mac),
                           [parser.OFPActionOutput(rev_out)],
                           idle_timeout=0, hard_timeout=0, cookie=ROUTING_COOKIE)

            self.logger.info("[FLOW] sw%s  fwd->p%s  rev->p%s", sw, fwd_out, rev_out)

    def _delete_pair_flows(self, src_mac, dst_mac):
        for dp in self.datapaths.values():
            parser  = dp.ofproto_parser
            ofproto = dp.ofproto
            for a, b in ((src_mac, dst_mac), (dst_mac, src_mac)):
                match = parser.OFPMatch(eth_src=a, eth_dst=b)
                mod = parser.OFPFlowMod(
                    datapath=dp,
                    command=ofproto.OFPFC_DELETE,
                    priority=FLOW_PRIORITY,
                    out_port=ofproto.OFPP_ANY,
                    out_group=ofproto.OFPG_ANY,
                    match=match)
                dp.send_msg(mod)

    # =========================================================================
    # BLOQUEO / DESBLOQUEO DE PARES IP
    # =========================================================================

    def _block_host_pair(self, src_ip, dst_ip):
        src_mac = self.ip_to_mac.get(src_ip)
        if not src_mac:
            return False, "IP origen no conocida aun - ejecuta pingall primero"
        src_dpid, _ = self.hosts.get(src_mac, (None, None))
        if src_dpid is None:
            return False, "Host origen no asociado a ningun switch"
        if src_dpid not in self.datapaths:
            return False, "Switch de acceso no disponible"

        dp     = self.datapaths[src_dpid]
        parser = dp.ofproto_parser
        match  = parser.OFPMatch(eth_type=0x0800, ipv4_src=src_ip, ipv4_dst=dst_ip)
        self._add_flow(dp, BLOCK_PRIORITY, match, [])  # acciones vacias = DROP

        self.blocked_pairs.add((src_ip, dst_ip))
        self.logger.info("[BLOCK] %s -> %s bloqueado en sw%s", src_ip, dst_ip, src_dpid)
        return True, "Bloqueado en sw%d" % src_dpid

    def _unblock_host_pair(self, src_ip, dst_ip):
        src_mac = self.ip_to_mac.get(src_ip)
        if src_mac:
            src_dpid, _ = self.hosts.get(src_mac, (None, None))
            if src_dpid is not None and src_dpid in self.datapaths:
                dp      = self.datapaths[src_dpid]
                parser  = dp.ofproto_parser
                ofproto = dp.ofproto
                match = parser.OFPMatch(eth_type=0x0800, ipv4_src=src_ip, ipv4_dst=dst_ip)
                mod = parser.OFPFlowMod(
                    datapath=dp, command=ofproto.OFPFC_DELETE_STRICT,
                    priority=BLOCK_PRIORITY,
                    out_port=ofproto.OFPP_ANY, out_group=ofproto.OFPG_ANY,
                    match=match)
                dp.send_msg(mod)
        self.blocked_pairs.discard((src_ip, dst_ip))
        self.logger.info("[UNBLOCK] %s -> %s desbloqueado", src_ip, dst_ip)
        return True, "Desbloqueado"

    # =========================================================================
    # POLITICA DE ENRUTAMIENTO: DESHABILITAR / REHABILITAR ENLACES
    # =========================================================================

    def _set_link_disabled(self, a, b, disabled):
        """Deshabilita (o rehabilita) logicamente el enlace sA-sB y re-rutea.
        Equivale a poner el costo del enlace en infinito: Dijkstra lo evita y
        el trafico toma la ruta alternativa. Esto es la 'politica de
        enrutamiento alternativo' que aplica el agente."""
        key = frozenset((a, b))
        if disabled:
            self.disabled_links.add(key)
            self.logger.info("[POLICY] Enlace s%s-s%s DESHABILITADO (politica)", a, b)
        else:
            self.disabled_links.discard(key)
            self.logger.info("[POLICY] Enlace s%s-s%s REHABILITADO", a, b)
        self._reroute_known_pairs()
        return True

    # =========================================================================
    # ARP PROXY
    # =========================================================================

    def _handle_arp(self, dp, in_port, eth, arp_pkt, msg):
        dpid    = dp.id
        src_mac = arp_pkt.src_mac
        src_ip  = arp_pkt.src_ip
        dst_ip  = arp_pkt.dst_ip

        if src_ip not in self.ip_to_mac:
            self.logger.info("[ARP] Aprendido %s -> %s", src_ip, src_mac)
            # Al conocer este host, olvidamos las solicitudes "vistas" que
            # esperaban por el, para poder reencolarlas/responderlas limpio.
            self.seen_arp = {x for x in self.seen_arp if x[2] != src_ip}
        self.ip_to_mac[src_ip] = src_mac
        self.mac_to_ip[src_mac] = src_ip

        if self._is_host_port(dpid, in_port):
            self.hosts[src_mac] = (dpid, in_port)

        if arp_pkt.opcode == arp.ARP_REQUEST:
            if dst_ip in self.ip_to_mac:
                # Si conocemos el destino, SIEMPRE respondemos. Las entradas
                # ARP de los hosts expiran y vuelven a preguntar de forma
                # legitima (sobre todo tras un re-ruteo). Deduplicar aqui
                # dejaria la resolucion rota de forma permanente.
                dst_mac_known = self.ip_to_mac[dst_ip]
                self.logger.info("[ARP] Proxy reply: %s en %s", dst_ip, dst_mac_known)
                self._send_arp_reply(dp, in_port, dst_mac_known, dst_ip,
                                     src_mac, src_ip)
            else:
                # Solo deduplicamos lo que NO podemos responder todavia, para
                # no encolar mil veces la misma solicitud pendiente.
                arp_id = (src_mac, src_ip, dst_ip)
                if arp_id in self.seen_arp:
                    return
                self.seen_arp.add(arp_id)
                self.pending_arp.setdefault(dst_ip, []).append(
                    (src_mac, src_ip, dpid, in_port))

        elif arp_pkt.opcode == arp.ARP_REPLY:
            self._deliver_arp_reply_to_pending(src_ip, src_mac)

        if src_ip in self.pending_arp:
            self._resolve_pending_arp(src_ip, src_mac)

    def _send_arp_reply(self, dp, out_port, sender_mac, sender_ip,
                        target_mac, target_ip):
        parser  = dp.ofproto_parser
        ofproto = dp.ofproto
        p = packet.Packet()
        p.add_protocol(ethernet.ethernet(
            ethertype=ether_types.ETH_TYPE_ARP,
            dst=target_mac, src=sender_mac))
        p.add_protocol(arp.arp(
            opcode=arp.ARP_REPLY,
            src_mac=sender_mac, src_ip=sender_ip,
            dst_mac=target_mac, dst_ip=target_ip))
        p.serialize()
        actions = [parser.OFPActionOutput(out_port)]
        out = parser.OFPPacketOut(
            datapath=dp, buffer_id=ofproto.OFP_NO_BUFFER,
            in_port=ofproto.OFPP_CONTROLLER,
            actions=actions, data=p.data)
        dp.send_msg(out)

    def _deliver_arp_reply_to_pending(self, src_ip, src_mac):
        for (req_mac, req_ip, req_dpid, req_port) in self.pending_arp.pop(src_ip, []):
            if req_dpid in self.datapaths:
                dp = self.datapaths[req_dpid]
                self._send_arp_reply(dp, req_port, src_mac, src_ip,
                                     req_mac, req_ip)

    def _resolve_pending_arp(self, newly_known_ip, newly_known_mac):
        for (req_mac, req_ip, req_dpid, req_port) in self.pending_arp.pop(newly_known_ip, []):
            if req_dpid in self.datapaths:
                dp = self.datapaths[req_dpid]
                self._send_arp_reply(dp, req_port, newly_known_mac, newly_known_ip,
                                     req_mac, req_ip)

    # =========================================================================
    # UTILIDADES
    # =========================================================================

    def _get_out_port_for_dpid(self, dpid, path, dst_port):
        if dpid not in path:
            if path and path[0] in self.graph.get(dpid, {}).get("neighbors", {}):
                return self.graph[dpid]["neighbors"][path[0]]["port"]
            return None
        idx = path.index(dpid)
        if idx == len(path) - 1:
            return dst_port
        next_sw = path[idx + 1]
        return self.graph[dpid]["neighbors"][next_sw]["port"]

    def _add_flow(self, dp, priority, match, actions,
                  idle_timeout=0, hard_timeout=0, cookie=0):
        ofproto = dp.ofproto
        parser  = dp.ofproto_parser
        inst = [parser.OFPInstructionActions(ofproto.OFPIT_APPLY_ACTIONS, actions)]
        mod = parser.OFPFlowMod(
            datapath=dp, priority=priority, match=match, cookie=cookie,
            instructions=inst, idle_timeout=idle_timeout, hard_timeout=hard_timeout)
        dp.send_msg(mod)

    def _is_host_port(self, dpid, port):
        for data in self.graph.get(dpid, {}).get("neighbors", {}).values():
            if data["port"] == port:
                return False
        return True


# ==============================================================================
# REST API
# ==============================================================================

class SDNRestAPI(ControllerBase):
    """Expone el estado del controlador via HTTP/JSON (puerto 8080)."""

    def __init__(self, req, link, data, **config):
        super(SDNRestAPI, self).__init__(req, link, data, **config)
        self.ctrl = data[_APP_NAME]

    @staticmethod
    def _json(data, status=200):
        return Response(status=status, content_type='application/json',
                        body=json.dumps(data, default=str),
                        headers={'Access-Control-Allow-Origin': '*'})

    @route('sdn_topology', '/sdn/topology', methods=['GET'])
    def get_topology(self, req, **kwargs):
        ctrl = self.ctrl
        switches = sorted(ctrl.datapaths.keys())

        links, seen = [], set()
        for sw, info in ctrl.graph.items():
            for nb in info['neighbors']:
                pair = (min(sw, nb), max(sw, nb))
                if pair not in seen:
                    seen.add(pair)
                    links.append(list(pair))

        hosts = {}
        for ip, mac in ctrl.ip_to_mac.items():
            dpid, port = ctrl.hosts.get(mac, (None, None))
            if dpid is not None:
                hosts[ip] = {'mac': mac, 'dpid': dpid, 'port': port}

        link_loads = {}
        for (a, b), v in ctrl.link_flows.items():
            if v > 0:
                key = '%d-%d' % (min(a, b), max(a, b))
                link_loads[key] = link_loads.get(key, 0) + v

        disabled = [sorted(list(fs)) for fs in ctrl.disabled_links]

        return self._json({'switches': switches, 'links': links,
                           'hosts': hosts, 'link_loads': link_loads,
                           'disabled_links': disabled})

    @route('sdn_flows', '/sdn/flows', methods=['GET'])
    def get_flows(self, req, **kwargs):
        ctrl = self.ctrl
        flows, seen = [], set()
        for (a, b), path in list(ctrl.mac_pair_path.items()):
            key = tuple(sorted([a, b]))
            if key in seen:
                continue
            seen.add(key)
            flows.append({
                'src_ip':          ctrl.mac_to_ip.get(a, '?'),
                'dst_ip':          ctrl.mac_to_ip.get(b, '?'),
                'src_mac':         a,
                'dst_mac':         b,
                'proto_name':      '-',
                'class_name':      'ROUTED',
                'installed_class': 'ROUTED',
                'confidence':      1.0,
                'iat':             0.0,
                'jitter':          0.0,
                'throughput':      0.0,
                'path':            path,
                'pkt_count':       0,
                'probs':           {},
            })
        return self._json(flows)

    @route('sdn_weights_get', '/sdn/weights', methods=['GET'])
    def get_weights(self, req, **kwargs):
        # Sin clases ML: se conserva por compatibilidad con la pagina web.
        return self._json({})

    @route('sdn_block', '/sdn/block', methods=['POST'])
    def block_pair(self, req, **kwargs):
        try:
            body = json.loads(req.body)
            ok, msg = self.ctrl._block_host_pair(body['src_ip'], body['dst_ip'])
            return self._json({'success': ok, 'message': msg})
        except Exception as exc:
            return self._json({'success': False, 'error': str(exc)}, status=400)

    @route('sdn_unblock', '/sdn/unblock', methods=['POST'])
    def unblock_pair(self, req, **kwargs):
        try:
            body = json.loads(req.body)
            ok, msg = self.ctrl._unblock_host_pair(body['src_ip'], body['dst_ip'])
            return self._json({'success': ok, 'message': msg})
        except Exception as exc:
            return self._json({'success': False, 'error': str(exc)}, status=400)

    @route('sdn_blocked', '/sdn/blocked', methods=['GET'])
    def get_blocked(self, req, **kwargs):
        return self._json([{'src_ip': s, 'dst_ip': d}
                           for s, d in self.ctrl.blocked_pairs])

    @route('sdn_link_disable', '/sdn/link/disable', methods=['POST'])
    def link_disable(self, req, **kwargs):
        try:
            body = json.loads(req.body)
            a, b = int(body['a']), int(body['b'])
            self.ctrl._set_link_disabled(a, b, True)
            return self._json({'success': True, 'disabled': [a, b],
                               'message': 'Enlace s%d-s%d deshabilitado; trafico re-ruteado' % (a, b)})
        except Exception as exc:
            return self._json({'success': False, 'error': str(exc)}, status=400)

    @route('sdn_link_enable', '/sdn/link/enable', methods=['POST'])
    def link_enable(self, req, **kwargs):
        try:
            body = json.loads(req.body)
            a, b = int(body['a']), int(body['b'])
            self.ctrl._set_link_disabled(a, b, False)
            return self._json({'success': True, 'enabled': [a, b],
                               'message': 'Enlace s%d-s%d rehabilitado; trafico re-ruteado' % (a, b)})
        except Exception as exc:
            return self._json({'success': False, 'error': str(exc)}, status=400)
