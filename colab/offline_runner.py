"""Start the trusted CPU orchestrator with Python IP networking disabled."""

import runpy
import socket
import sys


def block_ip_network(event, args):
    if event == "socket.__new__" and args[1] in (socket.AF_INET, socket.AF_INET6):
        raise PermissionError("host IP sockets are disabled in the CPU bridge test")
    if event in ("socket.getaddrinfo", "socket.gethostbyname", "socket.gethostbyaddr", "socket.getnameinfo"):
        raise PermissionError("host name resolution is disabled in the CPU bridge test")


if __name__ == "__main__":
    # Docker subprocesses use their fixed local Unix socket. Agent, shim,
    # capture service and verifier each use Docker's no-network isolation.
    sys.addaudithook(block_ip_network)
    try:
        socket.socket(socket.AF_INET)
    except PermissionError:
        pass
    else:
        raise RuntimeError("host IP-socket guard did not take effect")
    runpy.run_module("colab.upstream_cpu", run_name="__main__")
