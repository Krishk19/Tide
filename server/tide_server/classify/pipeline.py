from dataclasses import replace
from typing import Sequence

from tide_common.protocol import Signal

from .describe import cache_key, describe
from .heuristics import Verdict, classify_heuristic
from .jev import JevClassifier, JevError


class Pipeline:
    """cache -> Jev -> heuristics. Only Jev answers are cached, so a Jev outage heals itself."""

    def __init__(self, jev: JevClassifier | None) -> None:
        self.jev = jev
        self.cache: dict[str, Verdict] = {}
        self.last_error: str | None = None

    @property
    def mode(self) -> str:
        return "jev" if self.jev else "heuristics"

    async def classify(self, signal: Signal, apps: Sequence[str]) -> Verdict:
        key = cache_key(signal)
        if key in self.cache:
            return replace(self.cache[key], cached=True)
        text = describe(signal, apps)
        if self.jev is not None:
            try:
                verdict = await self.jev.classify(text)
                self.cache[key] = verdict
                self.last_error = None
                return verdict
            except JevError as e:
                self.last_error = str(e)
        return classify_heuristic(text)
