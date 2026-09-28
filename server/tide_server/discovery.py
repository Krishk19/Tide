"""Answers 'TIDE?' broadcasts so agents find the teacher laptop without typing an IP."""
import asyncio
import json


class DiscoveryProtocol(asyncio.DatagramProtocol):
    def __init__(self, http_port: int) -> None:
        self.reply = json.dumps({"tide": 1, "port": http_port}).encode()
        self.transport: asyncio.DatagramTransport | None = None

    def connection_made(self, transport) -> None:
        self.transport = transport

    def datagram_received(self, data: bytes, addr) -> None:
        if data.strip() == b"TIDE?" and self.transport:
            self.transport.sendto(self.reply, addr)


async def start_discovery(host: str, discovery_port: int, http_port: int) -> asyncio.DatagramTransport:
    loop = asyncio.get_running_loop()
    transport, _ = await loop.create_datagram_endpoint(
        lambda: DiscoveryProtocol(http_port), local_addr=(host, discovery_port), allow_broadcast=True)
    return transport
