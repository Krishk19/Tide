import ipaddress
import re
import socket
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor

import httpx
import psutil

from tide_agent.platform import AdapterInfo, Peer

_ssid_cache: tuple[float, str | None] = (0.0, None)
_pool = ThreadPoolExecutor(max_workers=2)


def _ssid() -> str | None:
    global _ssid_cache
    if time.monotonic() - _ssid_cache[0] < 5:
        return _ssid_cache[1]
    try:
        out = subprocess.run(["netsh", "wlan", "show", "interfaces"], capture_output=True, text=True,
                             timeout=3, creationflags=subprocess.CREATE_NO_WINDOW).stdout
        m = re.search(r"^\s*SSID\s*:\s*(.+)$", out, re.M)
        ssid = m.group(1).strip() if m else None
    except Exception:
        ssid = None
    _ssid_cache = (time.monotonic(), ssid)
    return ssid


def adapters() -> dict[str, AdapterInfo]:
    out = {}
    for name, st in psutil.net_if_stats().items():
        if "loopback" in name.lower():
            continue
        wifi = any(k in name.lower() for k in ("wi-fi", "wifi", "wireless", "wlan"))
        out[name] = AdapterInfo(name, st.isup, wifi, _ssid() if wifi and st.isup else None)
    return out


def _http_probe() -> bool:
    try:
        r = httpx.get("http://www.msftconnecttest.com/connecttest.txt", timeout=1.5)
        return r.text.strip() == "Microsoft Connect Test"
    except Exception:
        return False


def _tcp_probe() -> bool:
    try:
        socket.create_connection(("1.1.1.1", 443), timeout=1.5).close()
        return True
    except OSError:
        return False


def internet() -> bool:
    futures = [_pool.submit(_http_probe), _pool.submit(_tcp_probe)]
    return any(f.result() for f in futures)


def lan_peers(server_ip: str) -> list[Peer]:
    peers = []
    for c in psutil.net_connections("inet"):
        if c.status != psutil.CONN_ESTABLISHED or not c.raddr:
            continue
        ip = c.raddr.ip
        try:
            addr = ipaddress.ip_address(ip)
        except ValueError:
            continue
        if not addr.is_private or addr.is_loopback or ip == server_ip:
            continue
        try:
            name = psutil.Process(c.pid).name() if c.pid else ""
        except psutil.Error:
            name = ""
        peers.append(Peer(ip, c.raddr.port, name))
    return peers
