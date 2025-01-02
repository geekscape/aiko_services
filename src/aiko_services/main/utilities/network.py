#!/usr/bin/env python3

import psutil
import socket

__all__ = ["get_network_port_free", "get_network_ports_used"]

DYNAMIC_PORTS = [49152,65535]  # unassigned range for temporary / private ports

def get_network_port_free(port_range=DYNAMIC_PORTS, type="tcp"):
    if port_range == [0, 0]:  # default range
        port_range = DYNAMIC_PORTS
    if type not in ["tcp", "udp"]:
        raise KeyError(f'Network port type must be "tcp" or "udp": {type}')
    ports_used_type = {}
    ports_used_type["tcp"], ports_used_type["udp"] = get_network_ports_used()
    ports_used = ports_used_type[type]

    port_start, port_end = port_range
    port = port_start

    for port_used in ports_used:  # relies on "ports_used" being sorted
        if port_used > port_end:
            break      # beyond port_range
        if port < port_used:
            break      # found free port
        if port == port_used:
            port += 1  # Move to the next port if the current one is used

    return port if port <= port_end else None

def get_network_ports_used():
    all_ports = psutil.net_connections(kind="inet")
    tcp_used_ports = [conn.laddr.port for conn in all_ports  \
                         if conn.status == psutil.CONN_LISTEN]
    tcp_used_ports = list(set(tcp_used_ports))  # remove duplication
    tcp_used_ports.sort()

    udp_conns = [conn for conn in psutil.net_connections(kind="inet")  \
                    if conn.type == socket.SOCK_DGRAM]
    udp_used_ports = [conn.laddr.port for conn in udp_conns]
    udp_used_ports = list(set(udp_used_ports))  # remove duplication
    udp_used_ports.sort()

    return tcp_used_ports, udp_used_ports

def main():
    tcp_used_ports, udp_used_ports = get_network_ports_used()

    for port in tcp_used_ports:
        print(f"TCP port: {port:5d}")
    print()

    for port in udp_used_ports:
        print(f"UDP port: {port:5d}")

if __name__ == "__main__":
    main()
