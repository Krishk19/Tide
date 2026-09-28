"""Keyword fallback when Jev is unavailable. Deliberately capped below the auto-act threshold."""
import re
from dataclasses import dataclass, field
from typing import Any

LABELS = ("allowed_tool", "ai_assistant", "communication", "web_lookup", "remote_or_file_share", "other")
LABEL_TEXT = {"allowed_tool": "Allowed tool", "ai_assistant": "AI assistant",
              "communication": "Messaging", "web_lookup": "Web lookup",
              "remote_or_file_share": "Remote / file share", "other": "Other app"}


@dataclass(frozen=True)
class Verdict:
    label: str
    confidence: float
    violation: float
    source: str                 # "jev" | "heuristic"
    cached: bool = False
    raw: dict[str, Any] | None = field(default=None, compare=False)


_RULES: list[tuple[str, re.Pattern]] = [
    ("ai_assistant", re.compile(r"\b(gpt|chatgpt|ai|copilot|gemini|claude|llm|assistant|chatbot|"
                                r"poe|deepseek|perplexity|mistral|grok|notegpt|bard)\b")),
    ("communication", re.compile(r"\b(whatsapp|telegram|gmail|inbox|mail|outlook|messenger|"
                                 r"discord|slack|instagram|snapchat)\b")),
    ("remote_or_file_share", re.compile(r"\b(anydesk|teamviewer|rustdesk|drive|dropbox|"
                                        r"wetransfer|onedrive|remote)\b")),
    ("web_lookup", re.compile(r"\b(stackoverflow|geeksforgeeks|w3schools|github|google|bing|"
                              r"tutorialspoint|leetcode|search)\b")),
]


def classify_heuristic(text: str) -> Verdict:
    low = text.lower()
    for label, pattern in _RULES:
        if pattern.search(low):
            return Verdict(label, 0.70, 0.70, "heuristic")
    return Verdict("other", 0.30, 0.30, "heuristic")
