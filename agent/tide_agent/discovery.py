import json
import socket


def parse_server(text: str, default_port: int = 8765) -> tuple[str, int]:
    host, _, port = text.strip().partition(":")
    return host, int(port) if port else default_port


def discover(timeout: float = 2.0, port: int = 47800,
             targets: tuple[str, ...] = ("255.255.255.255",)) -> tuple[str, int] | None:
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        s.settimeout(timeout)
        for target in targets:
            s.sendto(b"TIDE?", (target, port))
        data, addr = s.recvfrom(1024)
        return addr[0], int(json.loads(data)["port"])
    except (OSError, ValueError, KeyError):
        return None
    finally:
        s.close()
