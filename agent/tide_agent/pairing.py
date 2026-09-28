from dataclasses import dataclass

import httpx


class PairError(Exception):
    pass


@dataclass(frozen=True)
class PairResult:
    token: str
    seat_id: int
    seat_no: int
    roll: str
    exam_title: str
    server_time: float


def _detail(r: httpx.Response) -> str:
    try:
        return str(r.json().get("detail") or r.text)
    except ValueError:
        return r.text or f"HTTP {r.status_code}"


async def pair(base_url: str, join_code: str, roll: str, seat_no: int, hostname: str,
               client: httpx.AsyncClient | None = None) -> PairResult:
    client = client or httpx.AsyncClient(timeout=8)
    try:
        r = await client.post(f"{base_url}/api/pair", json={"join_code": join_code, "roll": roll,
                                                               "seat_no": seat_no, "hostname": hostname})
    except httpx.HTTPError as e:
        raise PairError(f"Can't reach the teacher ({e.__class__.__name__})") from e
    if r.status_code != 200:
        raise PairError(_detail(r))
    b = r.json()
    return PairResult(b["token"], b["seat_id"], b["seat_no"], b["roll"], b["exam_title"], b["server_time"])


async def submit(base_url: str, token: str, zip_bytes: bytes, auto: bool,
                 client: httpx.AsyncClient | None = None) -> None:
    client = client or httpx.AsyncClient(timeout=30)
    try:
        r = await client.post(f"{base_url}/api/submit", data={"token": token, "auto": str(auto).lower()},
                              files={"file": ("submission.zip", zip_bytes, "application/zip")})
    except httpx.HTTPError as e:
        raise PairError(f"Submit failed ({e.__class__.__name__})") from e
    if r.status_code != 200:
        raise PairError(_detail(r))
