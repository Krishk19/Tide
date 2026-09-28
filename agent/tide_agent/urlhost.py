from urllib.parse import urlparse

LOCAL_SCHEMES = ("file:", "edge:", "chrome:", "about:", "brave:", "opera:", "view-source:")


def host_from_value(value: str) -> str:
    v = (value or "").strip()
    if not v or v.lower().startswith(LOCAL_SCHEMES):
        return ""
    if "://" not in v:
        v = "http://" + v
    return (urlparse(v).hostname or "").lower()
