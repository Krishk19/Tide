import io

import mss
from PIL import Image


def screenshot(max_width: int = 1280) -> bytes | None:
    try:
        with mss.mss() as sct:
            raw = sct.grab(sct.monitors[1])
        img = Image.frombytes("RGB", raw.size, raw.bgra, "raw", "BGRX")
        img.thumbnail((max_width, max_width))
        buf = io.BytesIO()
        img.save(buf, "JPEG", quality=60)
        return buf.getvalue()
    except Exception:
        return None
