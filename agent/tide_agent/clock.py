import time
from dataclasses import dataclass


def compute_offset(sent: float, server_time: float, received: float) -> float:
    """server_now - local_now, assuming the server stamped its reply halfway through the round trip."""
    return server_time - (sent + received) / 2


@dataclass
class ServerClock:
    offset: float = 0.0

    def now(self) -> float:
        return time.time() + self.offset

    def to_local(self, server_ts: float) -> float:
        return server_ts - self.offset
