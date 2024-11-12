#!/usr/bin/env python3

import psutil
import socket

__all__ = ["get_network_ports_listen"]

def get_network_ports_listen():
    all_ports = psutil.net_connections(kind="inet")
    tcp_listen_ports = [conn.laddr.port for conn in all_ports  \
                           if conn.status == psutil.CONN_LISTEN]
    tcp_listen_ports = list(set(tcp_listen_ports))  # remove duplication
    tcp_listen_ports.sort()

    udp_conns = [conn for conn in psutil.net_connections(kind="inet")  \
                    if conn.type == socket.SOCK_DGRAM]
    udp_listen_ports = [conn.laddr.port for conn in udp_conns]
    udp_listen_ports = list(set(udp_listen_ports))  # remove duplication
    udp_listen_ports.sort()

    return tcp_listen_ports, udp_listen_ports

def main():
    tcp_listen_ports, udp_listen_ports = get_network_ports_listen()

    for port in tcp_listen_ports:
        print(f"TCP port: {port:5d}")
    print()

    for port in udp_listen_ports:
        print(f"UDP port: {port:5d}")

if __name__ == "__main__":
    main()
