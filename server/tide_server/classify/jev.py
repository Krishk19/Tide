"""Jev (TypeSafe) through OpenRouter's Decisions API."""
from typing import Any

import httpx

from .heuristics import Verdict

ACTIVITY_CRITERIA = {
    "allowed_tool": "An app the exam policy allows (editor, terminal, file explorer, packet analyzer, VM), or a local file.",
    "ai_assistant": "An AI chatbot, AI coding assistant, or any AI tool that answers questions or writes code.",
    "communication": "Messaging, chat, social media, or email.",
    "web_lookup": "Searching or reading websites for answers: search engines, Q&A, tutorials, code sites.",
    "remote_or_file_share": "Remote desktop, screen sharing, cloud drives, or file transfer.",
    "other": "Anything else, such as games, media, or system utilities.",
}


class JevError(Exception):
    pass


class JevClassifier:
    def __init__(self, url: str, key: str, model: str, client: httpx.AsyncClient | None = None,
                 timeout: float = 4.0) -> None:
        self.url, self.key, self.model = url, key, model
        self.client = client or httpx.AsyncClient(timeout=timeout)

    def request_body(self, text: str) -> dict[str, Any]:
        return {
            "model": self.model,
            "state": text,
            "questions": {
                "activity": {"type": "choice", "instructions": "What is the student using right now?",
                             "criteria": ACTIVITY_CRITERIA},
                "violation": {"type": "noul", "instructions": "Does this break the exam policy?",
                              "criteria": {
                                  "true": "The student is using something the policy does not allow, or anything that could give outside help.",
                                  "false": "The student is using an allowed tool or doing ordinary local work."}},
            },
        }

    @staticmethod
    def parse(body: dict[str, Any]) -> Verdict:
        a = body["answers"]["activity"]
        choice = a["choice"]
        probs = a.get("probabilities") or {}
        confidence = float(probs.get(choice, a.get("confidence", 0.0)))
        violation = float(body["answers"]["violation"]["noul"])
        return Verdict(choice, round(confidence, 3), round(violation, 3), "jev",
                       raw={"jev_confidence": a.get("confidence"), "probabilities": probs,
                            "model": body.get("model")})

    async def classify(self, text: str) -> Verdict:
        try:
            r = await self.client.post(self.url, json=self.request_body(text),
                                       headers={"Authorization": f"Bearer {self.key}", "X-Title": "Tide"})
            r.raise_for_status()
            return self.parse(r.json())
        except (httpx.HTTPError, KeyError, ValueError, TypeError) as e:
            raise JevError(repr(e)) from e
