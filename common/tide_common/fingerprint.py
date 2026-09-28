"""Winnowing fingerprints that survive renaming (MOSS-style). Used for old-code and peer similarity."""
from __future__ import annotations

import re
import zlib

KEYWORDS = frozenset("""
auto break case char const continue default do double else enum extern float for goto if int
long register return short signed sizeof static struct switch typedef union unsigned void volatile
while class public private protected new delete this template typename namespace using bool true
false include define import from def lambda yield pass raise try except finally with as in is not
and or none self print elif global nonlocal assert del async await string vector std cout cin endl
printf scanf main null boolean final extends implements interface package super throws select where
""".split())

_COMMENTS = re.compile(r"//[^\n]*|/\*.*?\*/|^[ \t]*#(?![ \t]*include)[^\n]*", re.S | re.M)
_TOKEN = re.compile(r"[A-Za-z_]\w*|\d+|\S")


def normalize_code(text: str) -> str:
    text = _COMMENTS.sub(" ", text)
    return re.sub(r"\s+", " ", text).strip()


def tokens(text: str) -> list[str]:
    out = []
    for t in _TOKEN.findall(normalize_code(text)):
        low = t.lower()
        if t[0].isalpha() or t[0] == "_":
            out.append(low if low in KEYWORDS else "v")
        else:
            out.append(t)
    return out


def fingerprints(text: str, k: int = 5, window: int = 4) -> frozenset[int]:
    toks = tokens(text)
    if len(toks) < k:
        return frozenset()
    hashes = [zlib.crc32(" ".join(toks[i:i + k]).encode()) for i in range(len(toks) - k + 1)]
    if len(hashes) <= window:
        return frozenset(hashes)
    picked = set()
    for i in range(len(hashes) - window + 1):
        picked.add(min(hashes[i:i + window]))
    return frozenset(picked)


def similarity(a: frozenset[int], b: frozenset[int]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / min(len(a), len(b))
