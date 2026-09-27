import socket
import threading
import json
import logging
from typing import Optional

logger = logging.getLogger("tide.discovery")


def get_local_ip() -> str:
    """Attempts to find the active LAN IP for lab workstation communication."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        # Connect to public DNS or router without transmitting packets
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        try:
            return socket.gethostbyname(socket.gethostname())
        except Exception:
            return "127.0.0.1"


class UDPDiscoveryServer:
    """
    Lightweight background UDP broadcast responder.
    Allows student kiosk clients on the LAN to auto-discover the teacher server
    and connect with zero manual configuration or IP entry.
    """
    def __init__(self, port: int = 8001, http_port: int = 8000):
        self.port = port
        self.http_port = http_port
        self.running = False
        self.sock: Optional[socket.socket] = None
        self.thread: Optional[threading.Thread] = None

    def start(self):
        if self.running:
            return
        self.running = True
        self.thread = threading.Thread(target=self._run, daemon=True, name="UDPDiscoveryServer")
        self.thread.start()

    def _run(self):
        try:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.sock.bind(("", self.port))
            self.sock.settimeout(1.0)
            logger.info(f"UDP Discovery Server listening on UDP port {self.port}")
        except Exception as e:
            logger.warning(f"Could not bind UDP discovery port {self.port}: {e}")
            return

        local_ip = get_local_ip()

        while self.running:
            try:
                data, addr = self.sock.recvfrom(2048)
                msg = data.decode("utf-8", errors="ignore").strip()
                if "TIDE_DISCOVER" in msg or "discover" in msg.lower():
                    reply = {
                        "type": "TIDE_SERVER_ANNOUNCE",
                        "server_ip": local_ip,
                        "http_port": self.http_port,
                        "server_url": f"http://{local_ip}:{self.http_port}",
                        "status": "online",
                        "name": "Tide Assessment Server"
                    }
                    self.sock.sendto(json.dumps(reply).encode("utf-8"), addr)
            except socket.timeout:
                continue
            except Exception as e:
                if self.running:
                    logger.debug(f"UDP discovery receive error: {e}")

    def stop(self):
        self.running = False
        if self.sock:
            try:
                self.sock.close()
            except Exception:
                pass


discovery_server = UDPDiscoveryServer()
